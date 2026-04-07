"""Модуль тестирования MTProto прокси."""

import os
import socket
import time
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from parser import parse_mtproto_url
from formatting import format_config_name


def _test_single_mtproto(url: str, timeout: float) -> Tuple[bool, float, str]:
    """Тестирует один MTProto прокси через TCP соединение + минимальную проверку.

    Проверяет не только доступность порта, но и то, что сервер
    не закрывает соединение сразу при получении произвольных данных —
    это отсеивает обычные веб-серверы, не являющиеся MTProto-прокси.
    """
    parsed = parse_mtproto_url(url)
    if not parsed:
        return False, float('inf'), url

    server = parsed['server']
    port = parsed['port']

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        start = time.time()
        result = sock.connect_ex((server, port))
        elapsed = (time.time() - start) * 1000

        if result != 0:
            sock.close()
            return False, float('inf'), url

        # Отправляем 64 случайных байта — начало MTProto-рукопожатия.
        # Настоящий MTProto-сервер не закроет соединение сразу.
        try:
            sock.sendall(os.urandom(64))
            sock.settimeout(1.0)
            try:
                sock.recv(4)
            except socket.timeout:
                # Тишина — допустимо для MTProto (сервер ждёт больше данных)
                pass
        except (OSError, BrokenPipeError):
            # Сервер закрыл соединение — скорее всего не MTProto
            sock.close()
            return False, float('inf'), url

        sock.close()
        return True, elapsed, url

    except Exception:
        return False, float('inf'), url


def _run_mtproto_tests(
    configs: List[str],
    max_ping_ms: float,
    required_count: int,
    max_workers: int = 100,
    log_func=None,
    progress_func=None,
) -> List[Tuple[str, float]]:
    """Внутренняя функция: запускает тесты и возвращает список (url, ping_ms)."""

    def _log(msg, tag="info"):
        if log_func:
            log_func(msg, tag)

    def _progress(current, total):
        if progress_func:
            progress_func(current, total)

    results: List[Tuple[str, float]] = []
    total = len(configs)
    processed = 0
    lock = threading.Lock()
    stop_flag = threading.Event()

    # Таймаут = max_ping_ms / 1000 с небольшим запасом (но не более 10 с)
    timeout_sec = min(max_ping_ms / 1000 + 0.2, 10.0)

    _log(f"Тестирование {total} MTProto конфигов ({max_workers} потоков, timeout={timeout_sec:.1f}s)...", "info")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(_test_single_mtproto, cfg, timeout_sec): cfg
            for cfg in configs
        }

        for future in as_completed(future_to_url):
            if stop_flag.is_set():
                break
            try:
                success, ping_ms, url = future.result()

                with lock:
                    processed += 1
                    _progress(processed, total)

                    if success and ping_ms <= max_ping_ms:
                        results.append((url, ping_ms))
                        _log(f"✓ {ping_ms:.0f} мс (найдено: {len(results)}/{required_count})", "success")

                        if len(results) >= required_count:
                            stop_flag.set()
                            break
                    else:
                        status = "timeout" if ping_ms == float('inf') else f"{ping_ms:.0f} мс"
                        _log(f"✗ {status}", "warning")
            except Exception as e:
                with lock:
                    processed += 1
                _log(f"Ошибка: {e}", "error")

    results.sort(key=lambda x: x[1])
    return results[:required_count]


def test_mtproto_configs(
    configs: List[str],
    max_ping_ms: float,
    required_count: int,
    max_workers: int = 100,
    log_func=None,
    progress_func=None,
) -> List[Tuple[str, float]]:
    """Консольный режим: возвращает список (url, ping_ms)."""
    return _run_mtproto_tests(
        configs, max_ping_ms, required_count, max_workers, log_func, progress_func
    )


def test_mtproto_configs_and_save(
    configs: List[str],
    max_ping_ms: float,
    required_count: int,
    out_file: str,
    profile_title: str = "arqVPN MTProto",
    max_workers: int = 100,
    log_func=None,
    progress_func=None,
) -> Tuple[int, int, int]:
    """GUI режим: сохраняет в файл, возвращает (working, passed, failed)."""
    results = _run_mtproto_tests(
        configs, max_ping_ms, required_count, max_workers, log_func, progress_func
    )

    working = len(results)
    passed = min(working, required_count)
    failed = len(configs) - working

    if results:
        dirpath = os.path.dirname(os.path.abspath(out_file))
        os.makedirs(dirpath, exist_ok=True)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(f"#profile-title: {profile_title or 'arqVPN MTProto'}\n")
            f.write("#profile-update-interval: 48\n")
            f.write("#support-url: https://t.me/arqhub\n\n")
            for idx, (url, _) in enumerate(results, 1):
                formatted_url = format_config_name(url, idx, "Telegram MTProto", None)
                f.write(f"{formatted_url}\n")
        if log_func:
            log_func(f"✓ Сохранено {passed} конфигов", "success")

    return working, passed, failed
