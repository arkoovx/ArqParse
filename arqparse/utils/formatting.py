"""Форматирование названий конфигов и утилиты."""

import base64
import json
from urllib.parse import urlparse, parse_qs
from arqparse.utils.ip_country import get_flag_for_config


def _url_key(url: str) -> str:
    """Ключ для дедупликации — URL без фрагмента (#названия)."""
    return url.split('#')[0].strip()


def get_config_id(url: str) -> str:
    """
    Создаёт уникальный ID для конфига на основе его технических параметров.
    Игнорирует название (#) и параметры отображения.
    Помогает найти дубликаты, даже если они в разных форматах или с разными именами.
    """
    url = url.strip()
    if not url:
        return ""
    
    # Очищаем от пробелов внутри (бывает в vmess base64)
    # Но сохраняем оригинал для fallback
    
    try:
        # Убираем фрагмент
        base_url = url.split('#', 1)[0].strip()
        
        if base_url.startswith('vmess://'):
            # VMess дедуплицируем по add, port и id
            try:
                encoded = base_url.replace('vmess://', '', 1).strip()
                # Удаляем возможные пробелы/переносы внутри b64
                encoded = "".join(encoded.split())
                
                # Fix padding
                padding = 4 - len(encoded) % 4
                if padding != 4:
                    encoded += '=' * padding
                
                decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
                data = json.loads(decoded)
                return f"vmess:{data.get('add')}:{data.get('port')}:{data.get('id')}"
            except Exception:
                return base_url

        # Для остальных протоколов (vless, trojan, ss, tuic, hysteria2, hy2)
        # Формат обычно: protocol://[uuid/user:pass@]host:port?params
        if '://' not in base_url:
            return base_url

        protocol = base_url.split('://', 1)[0].lower()
        
        # Специальная обработка для MTProto
        if protocol in ('https', 'tg') and ('t.me/proxy' in base_url or 'proxy?' in base_url):
            parsed = urlparse(base_url.replace('tg://', 'http://').replace('https://', 'http://'))
            qs = parse_qs(parsed.query)
            server = qs.get('server', [''])[0]
            port = qs.get('port', [''])[0]
            secret = qs.get('secret', [''])[0]
            return f"mtproto:{server}:{port}:{secret}"

        # Стандартные VPN протоколы
        # Извлекаем адрес и порт с помощью упрощенного парсинга
        clean_url = base_url.replace(f"{protocol}://", "", 1)
        
        # Извлекаем часть до параметров (?)
        auth_addr_port = clean_url.split('?', 1)[0]
        
        user_info = ""
        addr_port = auth_addr_port
        if '@' in auth_addr_port:
            user_info, addr_port = auth_addr_port.rsplit('@', 1)
        
        return f"{protocol}:{addr_port.lower()}:{user_info}"

    except Exception:
        # Если не распарсилось — возвращаем URL без фрагмента как fallback
        return url.split('#', 1)[0].strip()


def _is_emoji(char: str) -> bool:
    """Проверяет, является ли символ эмодзи (по Unicode диапазонам)."""
    cp = ord(char)
    return (
        0x1F300 <= cp <= 0x1FAFF  # Misc symbols, emoticons, transport, etc.
        or 0x2600 <= cp <= 0x27BF  # Misc symbols & dingbats
        or 0xFE00 <= cp <= 0xFE0F  # Variation selectors
        or 0x1F1E0 <= cp <= 0x1F1FF  # Regional indicators
    )


def _is_regional_indicator(char: str) -> bool:
    """Проверяет, является ли символ региональным индикатором (для флагов)."""
    cp = ord(char)
    return 0x1F1E0 <= cp <= 0x1F1FF


def format_config_name(url: str, index: int, config_type: str = "Base VPN", ping_ms: int = None) -> str:
    """Форматирует название конфига: оставляет только эмодзи + arqVPN с номером.

    Args:
        url: URL конфига
        index: порядковый номер (1-based)
        config_type: тип конфига ("Base VPN", "Bypass VPN", "Telegram MTProto")
        ping_ms: пинг в миллисекундах (для отметки молнии если < 100 мс)
    """
    # Если есть фрагмент (#) - это название
    if '#' not in url:
        return url

    base_url, fragment = url.rsplit('#', 1)
    fragment = fragment.strip()

    emoji = None

    # Флаг = два региональных индикатора подряд
    if len(fragment) >= 2 and _is_regional_indicator(fragment[0]) and _is_regional_indicator(fragment[1]):
        emoji = fragment[:2]
    # Одиночный эмодзи
    elif fragment and _is_emoji(fragment[0]):
        emoji = fragment[0]
    # Если эмодзи нет во фрагменте — пытаемся получить флаг страны по IP
    elif not emoji:
        emoji = get_flag_for_config(url)

    # Формируем название с номером
    # Определяем "Обход" по названию задачи или типу
    is_bypass = (
        config_type and (
            "bypass" in config_type.lower() or
            "обход" in config_type.lower()
        )
    )
    if is_bypass:
        name_suffix = f"arq-Обход-{index}"
    else:
        name_suffix = f"arq-{index}"

    # Добавляем молнию если пинг < 100 мс
    fast_indicator = "⚡ " if ping_ms is not None and ping_ms < 100 else ""

    # Возвращаем результат с эмодзи
    if emoji:
        return f"{base_url}#{fast_indicator}{emoji} {name_suffix}"
    else:
        return f"{base_url}#{fast_indicator}{name_suffix}"
