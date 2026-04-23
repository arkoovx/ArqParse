"""Тесты для функции format_config_name из main.py."""

import os
import sys
import pytest

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from arqparse.utils.formatting import format_config_name, _is_emoji, _is_regional_indicator, _url_key
from arqparse.utils.ip_country import _code_to_flag, extract_ip_from_config_line, _is_ip


class TestIsEmoji:
    def test_regional_indicator(self):
        # Региональные индикаторы (флаги)
        assert _is_emoji('🇩') is True
        assert _is_emoji('🇪') is True
        assert _is_emoji('🇺') is True
        assert _is_emoji('🇷') is True

    def test_common_emojis(self):
        assert _is_emoji('⚡') is True
        assert _is_emoji('🚀') is True
        assert _is_emoji('✅') is True
        # ⚙️ — это два символа (базовый + variation selector), проверяем базовый
        assert _is_emoji('⚙') is True

    def test_ascii_not_emoji(self):
        assert _is_emoji('a') is False
        assert _is_emoji('Z') is False
        assert _is_emoji('0') is False
        assert _is_emoji('#') is False

    def test_cyrillic_not_emoji(self):
        assert _is_emoji('А') is False
        assert _is_emoji('Я') is False
        assert _is_emoji('р') is False

    def test_chinese_not_emoji(self):
        assert _is_emoji('中') is False
        assert _is_emoji('文') is False


class TestIsRegionalIndicator:
    def test_valid_flags(self):
        assert _is_regional_indicator('🇩') is True
        assert _is_regional_indicator('🇪') is True
        assert _is_regional_indicator('🇺') is True

    def test_non_flag(self):
        assert _is_regional_indicator('A') is False
        assert _is_regional_indicator('А') is False  # кириллица
        assert _is_regional_indicator('⚡') is False


class TestFormatConfigName:
    def test_flag_emoji(self):
        # 🇩🇪 = два региональных индикатора
        url = "vless://uuid@host:443#🇩🇪 Server"
        result = format_config_name(url, 1)
        assert result.endswith("#🇩🇪 arq-1")

    def test_no_emoji(self):
        url = "vless://uuid@host:443#Some Server"
        result = format_config_name(url, 1)
        assert result.endswith("#arq-1")

    def test_cyrillic_not_treated_as_emoji(self):
        url = "vless://uuid@host:443#Россия"
        result = format_config_name(url, 1)
        # Кириллица не должна быть эмодзи
        assert result.endswith("#arq-1")

    def test_no_fragment(self):
        url = "vless://uuid@host:443"
        assert format_config_name(url, 1) == url

    def test_fast_indicator(self):
        url = "vless://uuid@host:443#⚡ Server"
        result = format_config_name(url, 1, ping_ms=50)
        assert "⚡" in result

    def test_bypass_suffix(self):
        url = "vless://uuid@host:443#⚡ Server"
        result = format_config_name(url, 3, config_type="Bypass VPN")
        assert "arq-Обход-3" in result

    def test_mtproto_no_bypass_suffix(self):
        url = "https://t.me/proxy?server=1.2.3.4&port=443&secret=abc#🇺🇸 Proxy"
        result = format_config_name(url, 5, config_type="Telegram MTProto")
        assert "arq-5" in result
        assert "Обход" not in result

    def test_chinese_not_treated_as_emoji(self):
        url = "vless://uuid@host:443#中文服务器"
        result = format_config_name(url, 1)
        # Китайские иероглифы не эмодзи
        assert result.endswith("#arq-1")


class TestUrlKey:
    def test_removes_fragment(self):
        url = "vless://uuid@host:443?security=none#My Server"
        assert _url_key(url) == "vless://uuid@host:443?security=none"

    def test_no_fragment(self):
        url = "vless://uuid@host:443?security=none"
        assert _url_key(url) == url

    def test_strips_whitespace(self):
        url = "vless://uuid@host:443#   "
        assert _url_key(url) == "vless://uuid@host:443"

    def test_deduplication_key(self):
        url1 = "vless://uuid@host:443?security=none#Server 1"
        url2 = "vless://uuid@host:443?security=none#Server 2"
        assert _url_key(url1) == _url_key(url2)


class TestCodeToFlag:
    def test_common_countries(self):
        assert _code_to_flag("US") == "🇺🇸"
        assert _code_to_flag("DE") == "🇩🇪"
        assert _code_to_flag("RU") == "🇷🇺"
        assert _code_to_flag("GB") == "🇬🇧"
        assert _code_to_flag("JP") == "🇯🇵"
        assert _code_to_flag("CN") == "🇨🇳"
        assert _code_to_flag("FR") == "🇫🇷"

    def test_invalid_codes(self):
        assert _code_to_flag("") == ""
        assert _code_to_flag("A") == ""
        assert _code_to_flag("ABC") == ""


class TestExtractIpFromConfig:
    def test_vless_with_ip(self):
        url = "vless://abc123@8.8.8.8:443?security=tls#Server"
        assert extract_ip_from_config_line(url) == "8.8.8.8"

    def test_vless_with_domain(self):
        url = "vless://abc123@example.com:443?security=tls#Server"
        assert extract_ip_from_config_line(url) == ""

    def test_trojan_with_ip(self):
        url = "trojan://pass@1.1.1.1:443?security=tls#Server"
        assert extract_ip_from_config_line(url) == "1.1.1.1"

    def test_vmess_with_ip(self):
        import base64
        import json
        vmess_json = json.dumps({
            "add": "8.8.4.4",
            "port": "443",
            "id": "abc123",
            "aid": "0",
            "net": "tcp",
            "type": "none",
            "host": "",
            "path": "",
            "tls": "tls"
        })
        vmess_b64 = base64.b64encode(vmess_json.encode()).decode()
        url = f"vmess://{vmess_b64}"
        assert extract_ip_from_config_line(url) == "8.8.4.4"

    def test_empty_input(self):
        assert extract_ip_from_config_line("") == ""
        assert extract_ip_from_config_line(None) == ""


class TestIsIp:
    def test_valid_ipv4(self):
        assert _is_ip("8.8.8.8") is True
        assert _is_ip("192.168.1.1") is True
        assert _is_ip("1.1.1.1") is True

    def test_valid_ipv6(self):
        assert _is_ip("::1") is True
        assert _is_ip("2001:db8::1") is True

    def test_not_ip(self):
        assert _is_ip("example.com") is False
        assert _is_ip("not-an-ip") is False
        assert _is_ip("") is False
        assert _is_ip(None) is False
