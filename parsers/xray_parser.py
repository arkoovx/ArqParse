"""Парсер Xray конфигов (VLESS, VMess, Trojan, Shadowsocks, etc.)."""

import base64
import json
from typing import Dict, Optional
from urllib.parse import parse_qs, unquote

SUPPORTED_PROTOCOLS = ["vless", "vmess", "trojan", "ss", "ssr", "hysteria", "hysteria2", "hy2", "tuic"]


def is_valid_xray_config(url: str) -> bool:
    """Проверяет, является ли строка валидным Xray конфигом."""
    if not url or not isinstance(url, str):
        return False

    url_lower = url.lower().strip()
    for proto in SUPPORTED_PROTOCOLS:
        if url_lower.startswith(f"{proto}://"):
            return True
    return False


def parse_vless(url: str) -> Optional[Dict]:
    """Парсит VLESS URL в структуру для Xray config."""
    try:
        if not url.startswith("vless://"):
            return None

        # Удаляем префикс
        rest = url[8:]

        # Разделяем на часть до # и remark
        if "#" in rest:
            rest, remark = rest.rsplit("#", 1)
        else:
            remark = ""

        # Парсим: uuid@host:port?params
        if "@" not in rest:
            return None

        uuid_part, params_part = rest.split("?", 1) if "?" in rest else (rest, "")
        uuid, host_port = uuid_part.split("@", 1)

        # Хост и порт
        if ":" in host_port:
            # Обработка IPv6
            if host_port.startswith("["):
                bracket_end = host_port.find("]")
                host = host_port[1:bracket_end]
                port = int(host_port[bracket_end + 2 :])
            else:
                host, port = host_port.rsplit(":", 1)
                port = int(port)
        else:
            return None

        # Параметры
        params = parse_qs(params_part)

        return {
            "protocol": "vless",
            "uuid": uuid,
            "host": host,
            "port": port,
            "security": params.get("security", ["none"])[0],
            "flow": params.get("flow", [""])[0],
            "sni": params.get("sni", [host])[0],
            "fp": params.get("fp", ["chrome"])[0],
            "pbk": params.get("pbk", [""])[0],
            "sid": params.get("sid", [""])[0],
            "type": params.get("type", ["tcp"])[0],
            "encryption": params.get("encryption", ["none"])[0],
            "remark": unquote(remark),
        }
    except Exception:
        return None


def parse_vmess(url: str) -> Optional[Dict]:
    """Парсит VMess URL (base64 JSON)."""
    try:
        if not url.startswith("vmess://"):
            return None

        # Декодируем base64
        payload = url[8:]
        # Добавляем padding если нужно
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding

        decoded = base64.b64decode(payload).decode("utf-8")
        config = json.loads(decoded)

        return {
            "protocol": "vmess",
            "uuid": config.get("id", ""),
            "host": config.get("add", ""),
            "port": int(config.get("port", 0)),
            "security": config.get("scy", "auto"),
            "type": config.get("net", "tcp"),
            "sni": config.get("host", config.get("add", "")),
            "remark": config.get("ps", ""),
        }
    except Exception:
        return None


def parse_trojan(url: str) -> Optional[Dict]:
    """Парсит Trojan URL."""
    try:
        if not url.startswith("trojan://"):
            return None

        rest = url[9:]

        if "#" in rest:
            rest, remark = rest.rsplit("#", 1)
        else:
            remark = ""

        # password@host:port?params
        if "@" not in rest:
            return None

        password, host_port = rest.split("@", 1)

        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
            port = int(port.split("?")[0])
        else:
            return None

        params_part = host_port.split("?", 1)[1] if "?" in host_port else ""
        params = parse_qs(params_part)

        return {
            "protocol": "trojan",
            "password": password,
            "host": host,
            "port": port,
            "security": params.get("security", ["tls"])[0],
            "sni": params.get("sni", [host])[0],
            "type": params.get("type", ["tcp"])[0],
            "remark": unquote(remark),
        }
    except Exception:
        return None


def parse_config(url: str) -> Optional[Dict]:
    """Универсальный парсер для всех протоколов."""
    url = url.strip()

    if url.startswith("vless://"):
        return parse_vless(url)
    if url.startswith("vmess://"):
        return parse_vmess(url)
    if url.startswith("trojan://"):
        return parse_trojan(url)
    # Можно добавить ss, ssr, hysteria и т.д.

    return None


def create_xray_config(parsed: Dict, socks_port: int) -> Dict:
    """
    Создаёт config.json для Xray-core из распарсенных данных.

    Args:
        parsed: Распарсенные данные конфига
        socks_port: Локальный SOCKS порт

    Returns:
        Dict для записи в config.json
    """
    protocol = parsed["protocol"]

    # Базовая структура
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "port": socks_port,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
            }
        ],
        "outbounds": [{"protocol": protocol, "settings": {}, "streamSettings": {}}],
        "routing": {"rules": []},
    }

    # Настройка outbound в зависимости от протокола
    if protocol == "vless":
        config["outbounds"][0]["settings"] = {
            "vnext": [
                {
                    "address": parsed["host"],
                    "port": parsed["port"],
                    "users": [
                        {
                            "id": parsed["uuid"],
                            "encryption": parsed.get("encryption", "none"),
                            "flow": parsed.get("flow", ""),
                        }
                    ],
                }
            ]
        }

        # Stream settings
        stream = config["outbounds"][0]["streamSettings"]
        stream["network"] = parsed.get("type", "tcp")

        if parsed.get("security") == "reality":
            stream["security"] = "reality"
            stream["realitySettings"] = {
                "serverName": parsed.get("sni", parsed["host"]),
                "fingerprint": parsed.get("fp", "chrome"),
                "publicKey": parsed.get("pbk", ""),
                "shortId": parsed.get("sid", ""),
            }
        elif parsed.get("security") == "tls":
            stream["security"] = "tls"
            stream["tlsSettings"] = {
                "serverName": parsed.get("sni", parsed["host"]),
                "fingerprint": parsed.get("fp", "chrome"),
            }
        else:
            stream["security"] = "none"

    elif protocol == "vmess":
        config["outbounds"][0]["settings"] = {
            "vnext": [
                {
                    "address": parsed["host"],
                    "port": parsed["port"],
                    "users": [{"id": parsed["uuid"], "security": parsed.get("security", "auto")}],
                }
            ]
        }

        stream = config["outbounds"][0]["streamSettings"]
        stream["network"] = parsed.get("type", "tcp")
        if parsed.get("security") == "tls":
            stream["security"] = "tls"
            stream["tlsSettings"] = {"serverName": parsed.get("sni", parsed["host"])}

    elif protocol == "trojan":
        config["outbounds"][0]["settings"] = {
            "servers": [
                {
                    "address": parsed["host"],
                    "port": parsed["port"],
                    "password": parsed["password"],
                }
            ]
        }

        stream = config["outbounds"][0]["streamSettings"]
        stream["network"] = parsed.get("type", "tcp")
        stream["security"] = parsed.get("security", "tls")
        if stream["security"] == "tls":
            stream["tlsSettings"] = {"serverName": parsed.get("sni", parsed["host"])}

    return config
