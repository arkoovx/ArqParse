"""Упрощённый тестер Xray конфигов для ArcParse.

Использует подход из rjsxrd: запуск Xray процесса на порт, тест через SOCKS.
"""

import os
import sys
import json
import base64
import subprocess
import tempfile
import time
import socket
import signal
import threading
import atexit
import itertools
from typing import List, Tuple, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from constants import XRAY_BASE_PORT, XRAY_PORT_RANGE, MAX_SAFE_CONCURRENCY
except ImportError:
    # Fallback если constants.py недоступен
    XRAY_BASE_PORT = 20000
    XRAY_PORT_RANGE = 10000
    MAX_SAFE_CONCURRENCY = 500


# Глобальный список процессов для очистки
_running_processes: List[subprocess.Popen] = []
_process_lock = threading.Lock()
# Монотонный счётчик портов (диапазон 20000-20000+XRAY_PORT_RANGE)
_port_counter = itertools.count(XRAY_BASE_PORT)
_port_counter_lock = threading.Lock()
# Семафор для ограничения реального количества одновременных Xray-процессов
_xray_semaphore = threading.Semaphore(30)  # не более 30 Xray одновременно


def _cleanup_all():
    """Очистка всех процессов при выходе."""
    with _process_lock:
        for proc in _running_processes[:]:
            try:
                if proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        try:
                            proc.kill()
                            proc.wait(timeout=1)
                        except Exception:
                            pass
            except Exception:
                pass
        _running_processes.clear()


atexit.register(_cleanup_all)


def _get_next_port() -> int:
    """
    Выдаёт следующий порт из монотонно возрастающего диапазона.
    Не делает bind-проверку (она создаёт TOCTOU race condition при 150 потоках).
    Используем большой диапазон (XRAY_PORT_RANGE) чтобы снизить вероятность коллизий.
    """
    with _port_counter_lock:
        port = next(_port_counter)
    # Оборачиваем в диапазон XRAY_BASE_PORT .. XRAY_BASE_PORT + XRAY_PORT_RANGE
    port = XRAY_BASE_PORT + (port % XRAY_PORT_RANGE)
    return port


def _wait_for_port(port: int, timeout: float = 1.0) -> bool:
    """Ждет пока SOCKS порт станет доступен. Оптимизировано для скорости."""
    start = time.time()
    check_interval = 0.01  # Проверяем каждые 10ms
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.05)  # Быстрый timeout на сокет
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            pass
        time.sleep(check_interval)
    return False


def _parse_vless_url(url: str) -> Optional[Dict]:
    """Парсит VLESS URL в outbound конфиг."""
    from urllib.parse import parse_qs, unquote

    try:
        url_part = url.replace('vless://', '', 1)
        if '#' in url_part:
            url_part, _ = url_part.split('#', 1)
        if '?' in url_part:
            base_part, query_part = url_part.split('?', 1)
        else:
            base_part = url_part
            query_part = ''
        
        if '@' not in base_part:
            return None
        
        uuid, host_port = base_part.rsplit('@', 1)
        if ':' not in host_port:
            return None
        
        hostname, port_str = host_port.rsplit(':', 1)
        port = int(port_str.strip().rstrip('/'))
        
        params = parse_qs(query_part)
        security = params.get('security', ['none'])[0]
        
        outbound = {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": hostname,
                    "port": port,
                    "users": [{
                        "id": uuid,
                        "encryption": params.get('encryption', ['none'])[0],
                        "flow": params.get('flow', [''])[0]
                    }]
                }]
            },
            "streamSettings": {
                "network": params.get('type', ['tcp'])[0],
                "security": security
            }
        }
        
        if security == 'tls':
            outbound["streamSettings"]["tlsSettings"] = {
                "serverName": params.get('sni', [hostname])[0],
                "fingerprint": params.get('fp', ['chrome'])[0]
            }
        elif security == 'reality':
            outbound["streamSettings"]["realitySettings"] = {
                "serverName": params.get('sni', [''])[0],
                "fingerprint": params.get('fp', ['chrome'])[0],
                "publicKey": params.get('pbk', [''])[0],
                "shortId": params.get('sid', [''])[0]
            }
        
        transport = params.get('type', ['tcp'])[0]
        if transport == 'ws':
            outbound["streamSettings"]["wsSettings"] = {
                "path": unquote(params.get('path', ['/'])[0]),
                "headers": {"Host": unquote(params.get('host', [hostname])[0])}
            }
        elif transport == 'grpc':
            outbound["streamSettings"]["grpcSettings"] = {
                "serviceName": unquote(params.get('serviceName', [''])[0])
            }
        
        return outbound
    except Exception:
        return None


def _create_xray_config(url: str, socks_port: int) -> Optional[Dict]:
    """Создаёт конфиг Xray для одного URL."""
    protocol = url.split('://')[0].lower() if '://' in url else ''
    
    if protocol == 'vless':
        outbound = _parse_vless_url(url)
    elif protocol == 'vmess':
        # Упрощённый парсинг VMess
        try:
            encoded = url.replace('vmess://', '').strip()
            padding = 4 - len(encoded) % 4
            if padding != 4:
                encoded += '=' * padding
            decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
            data = json.loads(decoded)
            
            outbound = {
                "tag": "proxy",
                "protocol": "vmess",
                "settings": {
                    "vnext": [{
                        "address": str(data.get('add', '')),
                        "port": int(data.get('port', 443)),
                        "users": [{
                            "id": str(data.get('id', '')),
                            "alterId": int(data.get('aid', 0)),
                            "security": data.get('scy', 'auto')
                        }]
                    }]
                },
                "streamSettings": {
                    "network": data.get('net', 'tcp'),
                    "security": 'tls' if data.get('tls') == 'tls' else 'none'
                }
            }
        except Exception:
            return None
    elif protocol == 'trojan':
        try:
            url_part = url.replace('trojan://', '', 1).split('#')[0]
            if '?' in url_part:
                url_part = url_part.split('?')[0]
            password, host_port = url_part.rsplit('@', 1)
            hostname, port_str = host_port.rsplit(':', 1)
            
            outbound = {
                "tag": "proxy",
                "protocol": "trojan",
                "settings": {
                    "servers": [{
                        "address": hostname,
                        "port": int(port_str),
                        "password": password
                    }]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "tls",
                    "tlsSettings": {"serverName": hostname}
                }
            }
        except Exception:
            return None
    elif protocol == 'ss':
        try:
            url_part = url.replace('ss://', '', 1).split('#')[0]
            # Пробуем base64 decode
            try:
                padding = 4 - len(url_part) % 4
                if padding != 4:
                    url_part += '=' * padding
                decoded = base64.urlsafe_b64decode(url_part).decode('utf-8', errors='ignore')
                if '@' in decoded:
                    userinfo, server = decoded.rsplit('@', 1)
                    method, password = userinfo.split(':', 1) if ':' in userinfo else (userinfo, '')
                    hostname, port_str = server.rsplit(':', 1)
                    port = int(port_str)
                else:
                    return None
            except Exception:
                return None
            
            outbound = {
                "tag": "proxy",
                "protocol": "shadowsocks",
                "settings": {
                    "servers": [{
                        "address": hostname,
                        "port": port,
                        "password": password,
                        "method": method
                    }]
                }
            }
        except Exception:
            return None
    else:
        return None
    
    if not outbound:
        return None
    
    return {
        "log": {"loglevel": "error", "access": "", "error": ""},
        "inbounds": [{
            "tag": "socks",
            "listen": "127.0.0.1",
            "port": socks_port,
            "protocol": "mixed",
            "settings": {"auth": "noauth", "udp": True},
            "sniffing": {"enabled": True, "routeOnly": True, "destOverride": ["http", "tls", "quic"]}
        }],
        "outbounds": [
            outbound,
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"}
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [{"type": "field", "inboundTag": ["socks"], "outboundTag": "proxy"}]
        }
    }


def _test_single_config(url: str, xray_path: str, timeout: float,
                         target_url: str = "https://www.google.com/generate_204") -> Tuple[str, bool, float]:
    """Тестирует один конфиг через Xray."""
    with _xray_semaphore:  # Ждём, пока есть свободный слот
        if not os.path.exists(xray_path):
            return (url, False, 0.0)

        port = _get_next_port()
        config = _create_xray_config(url, port)

        if not config:
            return (url, False, 0.0)

        # Создаём временный файл конфига
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_path = f.name

        proc = None
        try:
            # Запускаем Xray
            proc = subprocess.Popen([xray_path, '-c', config_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with _process_lock:
                _running_processes.append(proc)

            # Ждём порт (оптимизировано - меньше timeout)
            if not _wait_for_port(port, timeout=1.0):
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                with _process_lock:
                    if proc in _running_processes:
                        _running_processes.remove(proc)
                try:
                    os.unlink(config_path)
                except Exception:
                    pass
                return (url, False, 0.0)

            try:
                os.unlink(config_path)
            except Exception:
                pass

            # Тест через SOCKS - оптимизированная конфигурация
            session = requests.Session()
            session.proxies = {'http': f'socks5h://127.0.0.1:{port}', 'https': f'socks5h://127.0.0.1:{port}'}
            # Упрощённая retry стратегия - без backoff для ускорения
            retry = Retry(total=0, status_forcelist=())  # Нет повторов
            adapter = HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=1)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            try:
                start = time.perf_counter()
                response = session.get(target_url, timeout=timeout, allow_redirects=False)
                latency = (time.perf_counter() - start) * 1000

                # Считаем успешным если статус < 500 (204, 301, 302 - OK)
                if response.status_code < 500:
                    return (url, True, latency)
                else:
                    return (url, False, 0.0)
            except Exception:
                return (url, False, 0.0)

        except Exception:
            return (url, False, 0.0)
        finally:
            if proc:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=1)
                except Exception:
                    pass
                with _process_lock:
                    if proc in _running_processes:
                        _running_processes.remove(proc)


def test_batch(
    urls: List[str],
    xray_path: str,
    concurrency: int = 90,
    timeout: float = 6.0,
    required_count: int = None,
    max_ping_ms: float = None,
    target_url: str = "https://www.google.com/generate_204",
    log_func: callable = None,
    progress_func: callable = None,
) -> List[Tuple[str, bool, float]]:
    """Тестирует батч конфигов конкурентно. Задачи подаются батчами, чтобы stop_flag реально останавливал работу.

    Args:
        urls: Список URL для тестирования
        xray_path: Путь к Xray бинарнику
        concurrency: Количество одновременных потоков (по умолчанию 90)
        timeout: Таймаут для каждого теста в секундах
        required_count: Количество рабочих конфигов с подходящим пингом, после которого остановиться.
                       Если None — тестирует все.
        max_ping_ms: Максимальный пинг. Если None — не фильтрует по пингу.
        target_url: URL для тестирования
        log_func: Функция логирования msg, tag — для GUI
        progress_func: Функция прогресса current, total — для GUI
    """
    def _log(msg, tag="info"):
        if log_func:
            log_func(msg, tag)
        else:
            print(msg)

    def _progress(current, total):
        if progress_func:
            progress_func(current, total)

    if not urls:
        return []

    results = []
    results_lock = threading.Lock()
    completed = 0
    last_batch_start = 0
    stop_flag = threading.Event()
    BATCH_SIZE = concurrency * 2  # подаём с запасом 2x от concurrency

    _log(f"Тестирование {len(urls)} конфигов (concurrency={concurrency}, timeout={timeout}s)...", "info")

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        try:
            # Разбиваем на батчи и подаём по мере необходимости
            for batch_start in range(0, len(urls), BATCH_SIZE):
                if stop_flag.is_set():
                    break

                batch = urls[batch_start:batch_start + BATCH_SIZE]
                futures = {
                    executor.submit(_test_single_config, url, xray_path, timeout, target_url): url
                    for url in batch
                    if not stop_flag.is_set()
                }

                for future in as_completed(futures):
                    if stop_flag.is_set():
                        future.cancel()
                        continue
                    try:
                        result = future.result(timeout=timeout + 5)
                        with results_lock:
                            results.append(result)
                            completed += 1
                            count = completed

                        # Обновляем прогресс
                        _progress(count, len(urls))

                        # Считаем рабочие и подходящие конфиги
                        all_working_count = sum(1 for r in results if r[1])
                        if max_ping_ms is not None:
                            suitable_count = sum(1 for r in results if r[1] and r[2] <= max_ping_ms)
                        else:
                            suitable_count = all_working_count

                        # Логируем каждый 5-й конфиг или каждые 20 (для консоли)
                        log_every = 5 if log_func else 20
                        if not stop_flag.is_set() and (count % log_every == 0 or count == len(urls)):
                            batch_results = results[last_batch_start:count]
                            batch_pings = [r[2] for r in batch_results if r[1]]
                            min_ping = min(batch_pings) if batch_pings else 0

                            if max_ping_ms is not None:
                                _log(f"Прогресс: {count}/{len(urls)} — Рабочих: {all_working_count} — Подходящих: {suitable_count} — Мин. пинг: {min_ping:.0f}мс", "info")
                            else:
                                _log(f"Прогресс: {count}/{len(urls)} — Рабочих: {all_working_count} — Мин. пинг: {min_ping:.0f}мс", "info")

                            last_batch_start = count

                        # Если найдено достаточно — останавливаем
                        if required_count and suitable_count >= required_count:
                            batch_pings = [r[2] for r in results if r[1]]
                            min_ping = min(batch_pings) if batch_pings else 0

                            if max_ping_ms is not None:
                                _log(f"Прогресс: {count}/{len(urls)} — Рабочих: {all_working_count} — Подходящих: {suitable_count} — Мин. пинг: {min_ping:.0f}мс", "info")
                            else:
                                _log(f"Прогресс: {count}/{len(urls)} — Рабочих: {all_working_count} — Мин. пинг: {min_ping:.0f}мс", "info")
                            _log(f"Найдено достаточно конфигов ({required_count}), остановка", "success")
                            stop_flag.set()
                            break

                    except Exception:
                        with results_lock:
                            results.append((futures[future], False, 0.0))

        except KeyboardInterrupt:
            _log("\n[!] Прерывание...", "warning")
            stop_flag.set()
            time.sleep(0.2)
        finally:
            stop_flag.set()
            try:
                executor.shutdown(wait=True, cancel_futures=True)
            except Exception:
                pass
            time.sleep(0.3)
            _cleanup_all()

    # Сортируем по latency (fastest first)
    working = [(url, success, latency) for url, success, latency in results if success]
    working.sort(key=lambda x: x[2])

    all_working = len(working)
    suitable = sum(1 for url, success, latency in working if latency <= max_ping_ms) if max_ping_ms else all_working

    if max_ping_ms is not None:
        _log(f"Готово: {suitable}/{all_working} подходящих из рабочих", "success")
    else:
        _log(f"Готово: {all_working}/{len(urls)} рабочих", "success")

    return working
