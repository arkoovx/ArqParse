#!/usr/bin/env python3
"""
arqParse - Единая точка входа.
Автоматически переключается между GUI и CLI режимами.
"""

import os
import sys

# ОТКЛЮЧАЕМ встроенный парсер аргументов Kivy и логи в консоли по умолчанию. 
# Это должно быть сделано ДО импорта любых модулей kivy.
os.environ["KIVY_NO_ARGS"] = "1"
if "--gui" not in sys.argv and "PYTHON_SERVICE_ARGUMENT" not in os.environ:
    os.environ["KIVY_NO_CONSOLELOG"] = "1"

import argparse

def main():
    parser = argparse.ArgumentParser(
        description="arqParse - скачивание и тестирование VPN конфигов",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--gui", action="store_true", help="Запустить графический интерфейс (Kivy/KivyMD)")
    parser.add_argument("--force", "-f", action="store_true", help="Принудительно перезагрузить все файлы")
    parser.add_argument("--skip-xray", action="store_true", help="Пропустить тестирование Xray конфигов")
    parser.add_argument("--proxy", type=str, help="Прокси для тестирования (socks5://host:port)")
    parser.add_argument("--no-ui", action="store_true", help="Отключить стильный интерфейс (простой вывод)")

    # Проверка на Android без импорта Kivy
    is_android = 'ANDROID_ARGUMENT' in os.environ or 'PYTHON_SERVICE_ARGUMENT' in os.environ
    
    if is_android:
        # На Android игнорируем системные аргументы sys.argv, так как они могут быть специфичны для p4a
        from arqparse.ui.gui import main as gui_main
        gui_main()
        return

    # Если мы не на Android, парсим аргументы командной строки
    args = parser.parse_args()

    if args.gui:
        # Включаем логи и аргументы обратно для GUI режима
        if "KIVY_NO_CONSOLELOG" in os.environ:
            del os.environ["KIVY_NO_CONSOLELOG"]
        if "KIVY_NO_ARGS" in os.environ:
            del os.environ["KIVY_NO_ARGS"]
            
        try:
            from arqparse.ui.gui import main as gui_main
            gui_main()
        except ImportError as e:
            sys.exit(f"[error] Не удалось загрузить GUI: {e}\nПопробуйте запустить без --gui или установите зависимости: pip install kivy kivymd")
    else:
        try:
            from arqparse.ui.cli import main as cli_main
            # Передаем аргументы в CLI main
            cli_main(
                force_download=args.force,
                skip_xray=args.skip_xray,
                proxy_url=args.proxy,
                no_ui=args.no_ui
            )
        except ImportError as e:
            sys.exit(f"[error] Не удалось загрузить CLI: {e}\nПроверьте целостность пакета arqparse.")

if __name__ == "__main__":
    main()
