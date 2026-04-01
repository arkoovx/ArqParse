"""Загрузка raw-файлов конфигов."""

import os

import requests

from config import TASKS
from utils.logger import log


def download_file(url: str, filepath: str, force: bool = False) -> bool:
    """
    Скачивает файл по URL.

    Args:
        url: URL для скачивания
        filepath: Путь для сохранения
        force: принудительная перезапись, если файл существует

    Returns:
        True если успешно, False иначе
    """
    # Проверка существующего файла
    if os.path.exists(filepath) and not force:
        log(f"Файл уже существует: {filepath}")
        return True

    try:
        log(f"Скачивание: {url[:80]}...")

        response = requests.get(url, timeout=30, allow_redirects=True)
        response.raise_for_status()

        # Сохраняем
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(response.text)

        # Считаем строки
        lines = [l.strip() for l in response.text.split("\n") if l.strip() and not l.startswith("#")]
        log(f"✓ Скачано: {filepath} ({len(lines)} конфигов)")

        return True

    except Exception as e:
        log(f"✗ Ошибка скачивания {url}: {e}")
        return False


def download_all(force: bool = False) -> dict:
    """
    Скачивает все файлы из TASKS.

    Returns:
        dict: {task_name: success_bool}
    """
    results = {}

    for task in TASKS:
        success = download_file(task["url"], task["raw_file"], force)
        results[task["name"]] = success

    return results
