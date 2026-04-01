# ArcParse

**ArcParse** — утилита для автоматического перескачивания и тестирования VPN-конфигов.

---

## Готовые протестированные подписки

Ниже — файлы, которые обновляются GitHub Actions автоматически раз в 24 часа:

- **Base VPN**: [`results/top_vpn.txt`](results/top_vpn.txt)
- **Bypass VPN**: [`results/top_bypass.txt`](results/top_bypass.txt)
- **Telegram MTProto**: [`results/top_MTProto.txt`](results/top_MTProto.txt)

Если нужен прямой subscription-URL для клиента, используйте raw-ссылку вашего форка:

```text
https://raw.githubusercontent.com/<username>/<repo>/<branch>/results/top_vpn.txt
https://raw.githubusercontent.com/<username>/<repo>/<branch>/results/top_bypass.txt
https://raw.githubusercontent.com/<username>/<repo>/<branch>/results/top_MTProto.txt
```

---

## Как это работает

- Каждые 24 часа workflow `.github/workflows/refresh-vpn-configs.yml` запускает:
  1. перескачивание исходников конфигов,
  2. ретест доступности и пинга,
  3. обновление файлов в `results/`.
- Также запуск можно сделать вручную через **Actions → Refresh and retest VPN configs → Run workflow**.

---

## Для разработчиков

### Локальный запуск

```bash
# Перейдите в директорию проекта
cd ArcParse

# Установите зависимости
python -m pip install -r requirements.txt

# Полный запуск
python main.py

# Принудительное обновление и ретест
python main.py --force --no-ui
```

### Требования

- Python 3.8+
- Xray-core (бинарник `bin/xray` для Linux/macOS или `bin/xray.exe` для Windows)

### Настройка источников и задач

Изменяется в `config.py` через список `TASKS`:

- `urls` — источники (проверяются по порядку),
- `raw_files` — куда сохранить сырые файлы,
- `out_file` — итоговый файл подписки,
- `type` — `xray` или `mtproto`,
- `target_url`, `max_ping_ms`, `required_count` — параметры тестирования.

---

## Структура проекта

```text
ArcParse/
├── .github/workflows/refresh-vpn-configs.yml
├── config.py
├── downloader.py
├── parser.py
├── testers.py
├── testers_mtproto.py
├── main.py
├── rawconfigs/
└── results/
```

---

## Лицензия

MIT

---

## Примечание об авторстве

Код написан нейронкой с использованием кода из проекта: https://github.com/whoahaow/rjsxrd

## ДИСКЛЕЙМЕР

Автор не является владельцем/разработчиком/поставщиком перечисленных VPN-конфигураций. Это независимый информационный обзор и результаты тестирования.

Данный пост не является рекламой VPN. Материал предназначен исключительно в информационных целях, и только для граждан тех стран, где эта информация легальна, как минимум - в научных целях. Автор не имеет никаких намерений, не побуждает, не поощряет и не оправдывает использование VPN ни при каких обстоятельствах. Ответственность за любое применение данных VPN-конфигураций — на их пользователе. Отказ от ответственности: автор не несёт ответственность за действия третьих лиц и не поощряет противоправное использование VPN. Используйте в соответствии с местным законодательством.

Используйте VPN только в законных целях: в частности - для обеспечения вашей безопасности в сети и защищённого удалённого доступа, и ни в коем случае не применяйте данную технологию для обхода блокировок.
