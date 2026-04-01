"""Файловые утилиты."""

import os
from typing import List, Tuple


def read_lines(filepath: str) -> List[str]:
    """Читает файл построчно, пропускает пустые строки и комментарии."""
    if not os.path.exists(filepath):
        return []

    lines = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
    return lines


def write_lines(filepath: str, lines: List[str], header: str = ""):
    """Записывает строки в файл."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        if header:
            f.write(header + "\n")
        f.write("\n".join(lines))


def write_results(filepath: str, results: List[Tuple[str, float]]):
    """
    Записывает результаты с пингами.
    results: список кортежей (config_url, ping_ms)
    Сортировка: чем меньше пинг, тем выше в списке.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Сортируем по пингу (возрастание - лучшие первыми)
    sorted_results = sorted(results, key=lambda x: x[1])

    with open(filepath, "w", encoding="utf-8") as f:
        for config, ping in sorted_results:
            # Формат: config_url # ping_ms
            f.write(f"{config} # {ping:.0f}ms\n")
