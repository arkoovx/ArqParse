"""Определение страны по IP с кэшированием и конвертацией в флаг-эмодзи."""

import os
import json
import urllib.request
import urllib.error
from functools import lru_cache

# Путь к файлу конфигурации
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# API endpoint (бесплатный, без регистрации, HTTP — без SSL проблем)
# Лимит: 45 запросов/мин с одного IP
COUNTRY_API = "http://ip-api.com/json/{ip}?fields=status,countryCode"


def _code_to_flag(code: str) -> str:
    """Конвертирует двухбуквенный код страны (ISO 3166-1) в эмодзи-флаг.
    
    Формула: каждая буква смещается от базовой точки 0x1F1E6 ('A')
    Например: 'DE' -> chr(0x1F1E6+3) + chr(0x1F1E6+4) = 🇩🇪
    """
    if not code or len(code) != 2:
        return ""
    try:
        a = chr(0x1F1E6 + ord(code[0].upper()) - ord('A'))
        b = chr(0x1F1E6 + ord(code[1].upper()) - ord('A'))
        return a + b
    except (ValueError, TypeError):
        return ""


# Предзаполненный кэш для популярных стран (чтобы не делать запросы)
_PRELOADED = {
    # Google DNS
    "8.8.8.8": "🇺🇸",
    "8.8.4.4": "🇺🇸",
    # Cloudflare DNS
    "1.1.1.1": "🇦🇺",
    "1.0.0.1": "🇦🇺",
}


@lru_cache(maxsize=4096)
def get_country_code(ip: str) -> str:
    """Возвращает двухбуквенный код страны для данного IP.
    
    Args:
        ip: IP-адрес (например, "8.8.8.8")
        
    Returns:
        Код страны ISO 3166-1 alpha-2 (например, "US") или пустая строка
    """
    if not ip:
        return ""
    
    try:
        url = COUNTRY_API.format(ip=ip)
        req = urllib.request.Request(url, headers={"User-Agent": "arqParse"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success":
                return data.get("countryCode", "")
    except Exception:
        pass
    return ""


@lru_cache(maxsize=4096)
def get_country_flag(ip: str) -> str:
    """Возвращает эмодзи-флаг для данного IP.
    
    Args:
        ip: IP-адрес
        
    Returns:
        Эмодзи-флаг (например, "🇩🇪") или пустая строка
    """
    if not ip:
        return ""
    
    # Проверяем предзаполненный кэш
    if ip in _PRELOADED:
        return _PRELOADED[ip]
    
    code = get_country_code(ip)
    if code:
        return _code_to_flag(code)
    return ""


def extract_ip_from_config_line(line: str) -> str:
    """Извлекает IP-адрес из строки конфига.
    
    Поддерживаемые форматы:
    - vmess://... (JSON с полем 'add')
    - vless://uuid@host:port...
    - trojan://pass@host:port...
    - ss://...@host:port...
    """
    import re
    import base64
    
    if not line:
        return ""
    
    # vmess — декодируем base64 JSON
    if line.startswith("vmess://"):
        try:
            payload = line[8:]
            rem = len(payload) % 4
            if rem:
                payload += '=' * (4 - rem)
            decoded = base64.b64decode(payload).decode('utf-8', errors='ignore')
            if decoded.startswith('{'):
                j = json.loads(decoded)
                host = j.get('add', '')
                # Проверяем, что это IP, а не домен
                if _is_ip(host):
                    return host
        except Exception:
            pass
        return ""
    
    # Остальные протоколы: ищем host:port после @ или //
    match = re.search(r'(?:@|//)([\w\.\-]+):(\d{1,5})', line)
    if match:
        host = match.group(1)
        if _is_ip(host):
            return host
    
    return ""


def _is_ip(s: str) -> bool:
    """Проверяет, является ли строка IP-адресом (v4 или v6)."""
    import ipaddress
    try:
        ipaddress.ip_address(s)
        return True
    except (ValueError, TypeError):
        return False


def get_flag_for_config(line: str) -> str:
    """Возвращает эмодзи-флаг для конфига по его IP.
    
    Args:
        line: Строка конфига (vless://, vmess://, и т.д.)
        
    Returns:
        Эмодзи-флаг или пустая строка
    """
    ip = extract_ip_from_config_line(line)
    if ip:
        return get_country_flag(ip)
    return ""
