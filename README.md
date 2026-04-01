# ArcParse

Легковесный парсер и тестировщик VPN/Proxy-конфигов с модульной архитектурой:

- `downloader.py` — скачивает raw-файлы с конфигами;
- `parsers/` — парсит Xray и MTProto форматы;
- `testers/` — тестирует конфиги (через Xray-core и TCP);
- `utils/` — вспомогательные модули;
- `main.py` — оркестрация полного пайплайна.

## Структура

```text
ArcParse/
├── main.py
├── config.py
├── downloader.py
├── parsers/
│   ├── __init__.py
│   ├── xray_parser.py
│   └── mtproto_parser.py
├── testers/
│   ├── __init__.py
│   ├── xray_tester.py
│   └── mtproto_tester.py
├── utils/
│   ├── __init__.py
│   ├── logger.py
│   └── file_utils.py
├── rawconfigs/
├── results/
├── bin/
└── requirements.txt
```

## Установка

```bash
pip install -r requirements.txt
```

## Подготовка Xray-core

Linux:

```bash
wget https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip -O bin/xray.zip
unzip bin/xray.zip -d bin/
chmod +x bin/xray
```

Windows:

1. Скачайте `Xray-windows-64.zip` с https://github.com/XTLS/Xray-core/releases.
2. Распакуйте `xray.exe` в `bin/`.

## Запуск

```bash
python main.py
```
