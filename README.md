# arqParse

Мультиплатформенная утилита (Python 3.10+) для скачивания, парсинга и проверки VPN (VLESS, VMess, Trojan, Shadowsocks) и MTProto конфигов. Поддерживает работу через CLI и графический интерфейс (KivyMD), работает на Linux, Windows и Android.

## Быстрый старт

Установка зависимостей:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Запуск:
- **CLI (по умолчанию):** `python main.py`
- **GUI:** `python main.py --gui`
- **Дополнительные флаги:**
  - `--force` — принудительно перекачать списки
  - `--skip-xray` — пропустить проверку VPN (только MTProto)
  - `--proxy "socks5://127.0.0.1:1080"` — использовать прокси для тестирования

Также доступны скрипты для быстрого запуска: `./run_cli.sh`, `./run_gui.sh` и `run_gui.bat`.

## Результаты работы

После завершения тестов проверенные и отсортированные по пингу конфиги сохраняются в папке `results/`:
- `top_base_vpn.txt`, `top_bypass_vpn.txt` (VPN)
- `top_telegram_mtproto.txt` (MTProto)
- `all_top_vpn.txt` (Объединённый список VPN)

Сырые скачанные данные кэшируются в папке `rawconfigs/`.
