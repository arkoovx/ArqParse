"""Тестирование MTProto прокси."""

import base64
import os
import socket
import threading
import time
from typing import List, Optional, Tuple

from config import MTPROTO_TIMEOUT
from parsers.mtproto_parser import parse_mtproto_url


class MTProtoTester:
    """Тестировщик MTProto прокси."""

    def __init__(self):
        self._socket_lock = threading.Lock()

    def _create_handshake(self, secret: str) -> bytes:
        """Создаёт MTProto handshake пакет."""
        random_data = os.urandom(56)

        try:
            # Пробуем декодировать secret
            if len(secret) == 32 and all(c in "0123456789abcdefABCDEF" for c in secret):
                secret_bytes = bytes.fromhex(secret)
            else:
                # Добавляем padding для base64
                padding = 4 - len(secret) % 4
                if padding != 4:
                    secret += "=" * padding
                secret_bytes = base64.b64decode(secret)
        except Exception:
            secret_bytes = secret.encode()[:16]

        return random_data[:8] + secret_bytes[:16] + random_data[24:]

    def test_single(self, server: str, port: int, secret: str, timeout: float = None) -> Tuple[bool, float]:
        """
        Тестирует один MTProto прокси.

        Returns:
            (is_working, latency_ms)
        """
        timeout = timeout or MTPROTO_TIMEOUT
        sock = None

        try:
            start_time = time.time()

            # Определяем тип сервера (IP или домен)
            try:
                # Если домен - резолвим
                if not all(c.isdigit() or c == "." for c in server):
                    server = socket.gethostbyname(server)
            except Exception:
                pass

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)

            # Коннект
            sock.connect((server, port))

            # Отправляем handshake
            handshake = self._create_handshake(secret)
            sock.settimeout(2.0)
            sock.sendall(handshake)

            # Ждём ответ
            sock.settimeout(3.0)
            response = sock.recv(64)

            # Проверяем ответ
            if not response or len(response) < 8:
                return False, 0.0

            latency = (time.time() - start_time) * 1000
            return True, latency

        except (socket.timeout, socket.error, OSError, BrokenPipeError, ConnectionResetError):
            return False, 0.0
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def test_batch(
        self,
        urls: List[str],
        required_count: int,
        max_ping_ms: float,
        timeout: float = None,
        concurrency: int = 200,
    ) -> List[Tuple[str, float]]:
        """
        Тестирует пакет MTProto прокси.

        Returns:
            Список кортежей (url, ping_ms) отсортированный по пингу
        """
        import concurrent.futures

        timeout = timeout or MTPROTO_TIMEOUT
        working = []
        stop_flag = threading.Event()

        def test_with_progress(url: str) -> Optional[Tuple[str, float]]:
            if stop_flag.is_set():
                return None

            parsed = parse_mtproto_url(url)
            if not parsed:
                return None

            is_working, latency = self.test_single(parsed["server"], parsed["port"], parsed["secret"], timeout)

            if is_working and latency <= max_ping_ms:
                with self._socket_lock:
                    working.append((url, latency))

                    if len(working) >= required_count:
                        stop_flag.set()
                        return (url, latency)

            return None

        # Тестируем параллельно
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(test_with_progress, url): url for url in urls}

            for future in concurrent.futures.as_completed(futures):
                if stop_flag.is_set():
                    for pending in futures:
                        pending.cancel()
                    break

                try:
                    future.result(timeout=timeout + 5)
                except Exception:
                    pass

        # Сортируем по пингу
        working.sort(key=lambda x: x[1])

        return working[:required_count]
