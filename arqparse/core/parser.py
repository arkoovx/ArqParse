"""Модуль для парсинга VPN ссылок и MTProto прокси."""

from __future__ import annotations

import html
import os
import re
from urllib.parse import parse_qs
from typing import Callable, Dict, List, Optional, Pattern

from arqparse.utils.formatting import get_config_id

# Предкомпилированные паттерны ускоряют повторные вызовы парсеров.
# Важно: более "длинные" протоколы должны идти раньше коротких,
# чтобы избежать частичных совпадений (например, hysteria2 до hysteria, ssr до ss).
_CONFIG_START_PATTERN = re.compile(r"(vless|vmess|trojan|ssr|ss|hysteria2|hy2|hysteria|tuic)://")
_MTPROTO_START_PATTERN = re.compile(r"(https://t\.me/proxy|tg://proxy)")
_MTPROTO_EXTRACT_PATTERN = re.compile(r"(https://t\.me/proxy\?[^\s]+|tg://proxy[^\s]+)")
_MTPROTO_REQUIRED_KEYS = ("server", "port", "secret")


def _has_required_mtproto_params(candidate: str) -> bool:
    """Быстрая проверка наличия обязательных параметров внутри URL-строки."""
    return all(f"{key}=" in candidate for key in _MTPROTO_REQUIRED_KEYS)


def parse_mtproto_url(url: str) -> Optional[Dict]:
    """
    Парсит MTProto прокси URL (https://t.me/proxy?server=...&port=...&secret=...).
    """
    if 't.me/proxy' not in url and 'tg://proxy' not in url:
        return None

    # Извлекаем query-параметры
    if '?' not in url:
        return None

    query = url.split('?', 1)[1]
    params = parse_qs(query)

    # Проверяем обязательные параметры
    if not all(key in params for key in _MTPROTO_REQUIRED_KEYS):
        return None

    try:
        server = params['server'][0]
        port = int(params['port'][0])
        secret = params['secret'][0]
    except (ValueError, TypeError, IndexError):
        return None

    # Валидация диапазона порта
    if port < 1 or port > 65535:
        return None

    return {
        'server': server,
        'port': port,
        'secret': secret,
        'url': url
    }


def _read_text_lines(filepath: str):
    """Построчное чтение файла с нормализацией."""
    if not os.path.exists(filepath):
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            yield line.replace("\r\n", "\n").replace("\r", "\n")


def _split_glued_entries_gen(lines_gen, start_pattern: Pattern[str]):
    """Генератор для разделения склеенных URL построчно."""
    current_line = ""

    for raw_line in lines_gen:
        stripped = raw_line.strip()
        if not stripped:
            continue

        matches = list(start_pattern.finditer(stripped))
        if len(matches) > 1:
            if current_line:
                yield current_line
                current_line = ""
            for index, match in enumerate(matches):
                start = match.start()
                if index + 1 < len(matches):
                    end = matches[index + 1].start()
                    yield stripped[start:end]
                else:
                    current_line = stripped[start:]
            continue

        if len(matches) == 1:
            match = matches[0]
            if match.start() == 0:
                if current_line:
                    yield current_line
                current_line = stripped
            else:
                current_line += stripped[: match.start()]
                if current_line.strip():
                    yield current_line.strip()
                current_line = stripped[match.start() :]
            continue

        current_line += stripped

    if current_line:
        yield current_line


def _extract_items_gen(lines_gen, validator: Callable[[str], bool]):
    """Генератор фильтрации строк с дедупликацией."""
    seen_ids = set()
    for line in lines_gen:
        candidate = line.strip()
        if candidate and validator(candidate):
            config_id = get_config_id(candidate)
            if config_id and config_id not in seen_ids:
                seen_ids.add(config_id)
                yield candidate


def read_configs_from_file(filepath: str) -> List[str]:
    """
    Читает конфиги из файла, используя генераторы для экономии памяти.
    """
    if not os.path.exists(filepath):
        return []

    lines = _read_text_lines(filepath)
    # html.unescape для каждой строки отдельно (чуть медленнее, но меньше памяти)
    unescaped_lines = (html.unescape(line) for line in lines)
    split_lines = _split_glued_entries_gen(unescaped_lines, _CONFIG_START_PATTERN)
    
    return list(_extract_items_gen(
        split_lines,
        lambda item: not item.startswith("#") and not item.startswith("profile-"),
    ))


def read_mtproto_from_file(filepath: str) -> List[str]:
    """
    Читает MTProto прокси из файла, используя генераторы.
    """
    if not os.path.exists(filepath):
        return []

    lines = _read_text_lines(filepath)
    unescaped_lines = (html.unescape(line) for line in lines)
    split_lines = _split_glued_entries_gen(unescaped_lines, _MTPROTO_START_PATTERN)

    proxies: List[str] = []
    seen_ids = set()
    
    for line in split_lines:
        for proxy in _MTPROTO_EXTRACT_PATTERN.findall(line):
            candidate = proxy.strip()
            if not candidate or not _has_required_mtproto_params(candidate):
                continue
            
            config_id = get_config_id(candidate)
            if config_id and config_id not in seen_ids:
                seen_ids.add(config_id)
                proxies.append(candidate)
    return proxies
