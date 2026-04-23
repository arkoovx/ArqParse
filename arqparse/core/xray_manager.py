"""
Автоопределение ОС/архитектуры и установка правильного Xray бинарника.
Поддерживает разделение по папкам: bin/linux, bin/windows, bin/android.
"""

import os
import sys
import platform
import zipfile
import shutil
import tempfile
import requests

from arqparse.config.settings import BIN_DIR, BASE_DIR

# Последний релиз Xray-core
XRAY_RELEASE_API = "https://api.github.com/repos/XTLS/Xray-core/releases/latest"

# Маппинг платформы -> имя файла в релизе
PLATFORM_MAP = {
    ("win32", "AMD64"): ("windows", "Xray-windows-64.zip", "xray.exe"),
    ("win32", "ARM64"): ("windows", "Xray-windows-arm64-v8a.zip", "xray.exe"),
    ("linux", "x86_64"): ("linux", "Xray-linux-64.zip", "xray"),
    ("linux", "aarch64"): ("android", "Xray-linux-arm64-v8a.zip", "xray"), # Используем для Android
    ("linux", "armv7l"): ("android", "Xray-linux-arm32-v7a.zip", "xray"),
    ("darwin", "x86_64"): ("macosx", "Xray-macos-64.zip", "xray"),
    ("darwin", "arm64"): ("macosx", "Xray-macos-arm64-v8a.zip", "xray"),
}


def get_platform_info() -> tuple:
    """Возвращает (sys_platform, machine) кортеж."""
    return (sys.platform, platform.machine())


def get_xray_download_info() -> tuple:
    """Возвращает (folder_name, zip_name, binary_name) для текущей платформы."""
    plat = get_platform_info()
    
    # Спец-обработка для Android через Kivy
    try:
        from kivy.utils import platform as kivy_plat
        if kivy_plat == "android":
            # На Android чаще всего arm64-v8a (aarch64)
            return ("android", "Xray-linux-arm64-v8a.zip", "xray")
    except ImportError:
        pass

    if plat in PLATFORM_MAP:
        return PLATFORM_MAP[plat]
    
    # Fallback
    if sys.platform == "win32": return ("windows", "Xray-windows-64.zip", "xray.exe")
    return ("linux", "Xray-linux-64.zip", "xray")


def is_binary_valid(binary_path: str) -> bool:
    """Проверяет, что бинарник Xray является рабочим."""
    if not os.path.exists(binary_path):
        return False

    # На Android мы не можем просто запустить бинарник без установки прав и правильного окружения
    try:
        from kivy.utils import platform as kivy_plat
        if kivy_plat == "android":
            return os.path.getsize(binary_path) > 1000000 # Просто проверка размера (>1MB)
    except ImportError:
        pass

    try:
        import subprocess
        result = subprocess.run(
            [binary_path, "version"],
            capture_output=True,
            timeout=5,
            text=True
        )
        return result.returncode == 0 and "Xray" in result.stdout
    except Exception:
        return False


def _safe_extract_zip(zip_path: str, target_dir: str):
    """Безопасно распаковывает zip без path traversal."""
    abs_target_dir = os.path.abspath(target_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_path = os.path.abspath(os.path.join(target_dir, member.filename))
            if not member_path.startswith(abs_target_dir + os.sep) and member_path != abs_target_dir:
                raise ValueError(f"Небезопасный путь в архиве: {member.filename}")
        zf.extractall(target_dir)


def download_xray_for_platform(platform_key: tuple, target_bin_dir: str = None, log_func=None) -> bool:
    """Скачивает Xray для конкретной платформы (например, ('linux', 'aarch64') для Android)."""
    def _log(msg, tag="info"):
        if log_func: log_func(msg, tag)
        else: print(msg)

    if platform_key not in PLATFORM_MAP:
        return False
    
    folder_name, zip_name, binary_name = PLATFORM_MAP[platform_key]
    
    # Если папка не указана, используем стандартную структуру в корне проекта
    if target_bin_dir is None:
        target_bin_dir = os.path.join(BASE_DIR, "bin", folder_name)

    os.makedirs(target_bin_dir, exist_ok=True)
    dst_binary = os.path.join(target_bin_dir, binary_name)

    # Проверяем, может уже есть
    if os.path.exists(dst_binary) and os.path.getsize(dst_binary) > 1000000:
        _log(f"Бинарник для {folder_name} уже на месте: {dst_binary}")
        return True

    _log(f"Загрузка Xray для {folder_name} ({zip_name})...")
    
    session = requests.Session()
    headers = {"User-Agent": "arqParse", "Accept": "application/vnd.github.v3+json"}
    
    try:
        # 1. Получаем инфо о релизе
        resp = session.get(XRAY_RELEASE_API, headers=headers, timeout=15)
        resp.raise_for_status()
        assets = resp.json().get("assets", [])
        
        asset_url = next((a["browser_download_url"] for a in assets if a["name"] == zip_name), None)
        if not asset_url:
            _log(f"Не найден ассет {zip_name}", "error")
            return False

        # 2. Скачиваем
        with session.get(asset_url, headers=headers, stream=True, timeout=300) as r:
            r.raise_for_status()
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = os.path.join(tmpdir, "xray.zip")
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

                _safe_extract_zip(zip_path, tmpdir)

                # 3. Ищем бинарник
                src_binary = None
                for root, _, files in os.walk(tmpdir):
                    if binary_name in files:
                        src_binary = os.path.join(root, binary_name)
                        break

                if not src_binary:
                    _log("Бинарник не найден в архиве", "error")
                    return False

                shutil.copy2(src_binary, dst_binary)
                if sys.platform != "win32":
                    os.chmod(dst_binary, 0o755)
                
                _log(f"✓ Успешно установлен в {dst_binary}", "success")
                return True

    except Exception as e:
        _log(f"✗ Ошибка скачивания для {folder_name}: {e}", "error")
        return False


def download_xray_binary(log_func=None) -> bool:
    """Скачивает бинарник для ТЕКУЩЕЙ платформы."""
    plat = get_platform_info()
    return download_xray_for_platform(plat, BIN_DIR, log_func)


def download_all_binaries(log_func=None):
    """Скачивает бинарники для всех основных платформ (для подготовки дистрибутива)."""
    platforms = [
        ("win32", "AMD64"),   # Windows 64
        ("linux", "x86_64"),  # Linux 64
        ("linux", "aarch64"), # Android / ARM64
    ]
    for p in platforms:
        download_xray_for_platform(p, None, log_func)


def get_android_xray_path():
    """Достает системный путь к нашему libxray.so на Android"""
    try:
        from jnius import autoclass
        # Получаем контекст приложения через Kivy
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        context = PythonActivity.mActivity.getApplicationContext()
        
        # Получаем системную директорию с библиотеками (.so)
        native_lib_dir = context.getApplicationInfo().nativeLibraryDir
        xray_path = os.path.join(native_lib_dir, "libxray.so")
        
        if os.path.exists(xray_path):
            return xray_path
            
    except Exception as e:
        print(f"Ошибка при поиске libxray.so: {e}")
        
    return None


def ensure_xray(log_func=None) -> str:
    """Возвращает путь к бинарнику Xray. На Android берет из системной папки."""
    try:
        from kivy.utils import platform as kivy_plat
    except ImportError:
        kivy_plat = "unknown"

    # 1. Логика для Android
    if kivy_plat == "android":
        android_path = get_android_xray_path()
        if android_path:
            return android_path
        else:
            if log_func:
                log_func("Критическая ошибка: libxray.so не найден в системе!", "error")
            return ""

    # 2. Логика для ПК (Windows/Linux) - оставляем как было (со скачиванием)
    from arqparse.config.settings import XRAY_BIN
    
    if is_binary_valid(XRAY_BIN):
        return XRAY_BIN

    if download_xray_binary(log_func):
        return XRAY_BIN
    
    return ""
