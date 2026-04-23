"""Конфигурация и настройки задач для arqParse."""

import os
import sys

# Находим корень проекта (на два уровня выше от arqparse/config/)
_current_file = os.path.abspath(__file__)
# .../arqparse/config/settings.py -> .../arqparse/config -> .../arqparse -> ...
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_current_file)))

# Папки данных в корне проекта
RAW_CONFIGS_DIR = os.path.join(BASE_DIR, "rawconfigs")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# Определение платформы
try:
    from kivy.utils import platform as kivy_plat
    PLATFORM = kivy_plat
except ImportError:
    import platform as py_plat
    machine = py_plat.machine().lower()
    if sys.platform == "win32":
        PLATFORM = "win"
    elif "arm" in machine or "aarch64" in machine:
        PLATFORM = "android"
    elif sys.platform == "darwin":
        PLATFORM = "macosx"
    else:
        PLATFORM = "linux"

# Пути к бинарникам (теперь с разделением по папкам)
if PLATFORM == "android":
    try:
        from android.storage import app_storage_path
        BASE_DIR = app_storage_path()
    except ImportError:
        pass
    
    RAW_CONFIGS_DIR = os.path.join(BASE_DIR, "rawconfigs")
    RESULTS_DIR = os.path.join(BASE_DIR, "results")
    BIN_DIR = os.path.join(BASE_DIR, "bin", "android")
    _xray_name = "xray"
elif PLATFORM == "win":
    BIN_DIR = os.path.join(BASE_DIR, "bin", "windows")
    _xray_name = "xray.exe"
else:
    # Linux или MacOS
    BIN_DIR = os.path.join(BASE_DIR, "bin", PLATFORM if PLATFORM in ["linux", "macosx"] else "linux")
    _xray_name = "xray"

# Создаем директории при импорте
os.makedirs(RAW_CONFIGS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(BIN_DIR, exist_ok=True)

XRAY_BIN = os.path.join(BIN_DIR, _xray_name)

# Задачи для скачивания и тестирования
TASKS = [
    {
        "name": "Base VPN",
        "urls": [
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/default/22.txt",
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/default/23.txt",
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/default/24.txt",
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/default/25.txt",
        ],
        "raw_files": [
            os.path.join(RAW_CONFIGS_DIR, "22.txt"),
            os.path.join(RAW_CONFIGS_DIR, "23.txt"),
            os.path.join(RAW_CONFIGS_DIR, "24.txt"),
            os.path.join(RAW_CONFIGS_DIR, "25.txt"),
        ],
        "out_file": os.path.join(RESULTS_DIR, "top_base_vpn.txt"),
        "profile_title": "arqVPN Free | Обычный",
        "type": "xray",
        "target_url": "https://www.google.com/generate_204",
        "max_ping_ms": 9000,
        "required_count": 10
    },
    {
        "name": "Bypass VPN",
        "urls": [
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/bypass/bypass-all.txt",
        ],
        "raw_files": [
            os.path.join(RAW_CONFIGS_DIR, "bypass-all.txt"),
        ],
        "out_file": os.path.join(RESULTS_DIR, "top_bypass_vpn.txt"),
        "profile_title": "arqVPN Free | Обход",
        "type": "xray",
        "target_url": "https://www.google.com/generate_204",
        "max_ping_ms": 12000,
        "required_count": 10
    },
    {
        "name": "Telegram MTProto",
        "urls": [
            "https://raw.githubusercontent.com/whoahaow/rjsxrd/refs/heads/main/githubmirror/tg-proxy/MTProto.txt",
        ],
        "raw_files": [
            os.path.join(RAW_CONFIGS_DIR, "MTProto.txt"),
        ],
        "out_file": os.path.join(RESULTS_DIR, "top_telegram_mtproto.txt"),
        "profile_title": "arqVPN Free | Telegram",
        "type": "mtproto",
        "target_url": "https://core.telegram.org",
        "max_ping_ms": 1500,
        "required_count": 10
    }
]

# User-Agent для запросов
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)

# Список доменов для фильтрации SNI (можно дополнить)
SNI_DOMAINS = []
