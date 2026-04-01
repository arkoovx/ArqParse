"""Парсер MTProto прокси для Telegram."""

from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse


def parse_mtproto_url(url: str) -> Optional[Dict]:
    """
    Парсит MTProto proxy URL.

    Форматы:
    - https://t.me/proxy?server=host&port=port&secret=secret
    - tg://proxy?server=host&port=port&secret=secret

    Returns:
        Dict с ключами: server, port, secret, type
        или None если невалидный
    """
    try:
        url = url.strip()

        # Конвертируем tg:// в https://t.me
        if url.startswith("tg://"):
            url = "https://t.me" + url[4:]

        if not url.startswith("https://t.me/proxy"):
            return None

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        server = params.get("server", [None])[0]
        port_str = params.get("port", ["0"])[0]
        secret = params.get("secret", [""])[0]

        if not server or not port_str:
            return None

        port = int(port_str)

        # Валидация порта
        if port < 1 or port > 65535:
            return None

        return {
            "type": "mtproto",
            "server": server,
            "port": port,
            "secret": secret,
            "original_url": url,
        }

    except Exception:
        return None


def is_valid_mtproto(url: str) -> bool:
    """Проверяет валидность MTProto URL."""
    return parse_mtproto_url(url) is not None
