"""Потокобезопасное логирование."""

import threading
from datetime import datetime

LOGS = []
_lock = threading.Lock()


def log(message: str):
    """Добавляет сообщение в лог и выводит в консоль."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {message}"

    with _lock:
        LOGS.append(formatted)

    print(formatted, flush=True)


def get_logs():
    """Возвращает все логи."""
    with _lock:
        return LOGS.copy()


def clear_logs():
    """Очищает логи."""
    with _lock:
        LOGS.clear()
