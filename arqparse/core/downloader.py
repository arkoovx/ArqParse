"""Модуль для скачивания конфигов."""

import html
import os
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from arqparse.config.settings import CHROME_UA
from arqparse.core.parser import _split_glued_entries_gen, _CONFIG_START_PATTERN

MAX_DOWNLOAD_SIZE_BYTES = int(os.environ.get("ARQPARSE_MAX_DOWNLOAD_BYTES", str(10 * 1024 * 1024)))
_ALLOWED_TEXT_CONTENT_TYPES = (
    "text/plain",
    "text/html",
    "application/octet-stream",
    "application/text",
    "binary/octet-stream",
)


def _is_private_hostname(hostname: str) -> bool:
    """Проверяет, указывает ли host на локальный/private адрес."""
    if not hostname:
        return True
    lowered = hostname.lower()
    if lowered in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        import ipaddress
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    except ValueError:
        return False


def validate_download_url(url: str):
    """Проверяет, что URL источника выглядит безопасно для скачивания конфигов."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"https"}:
        raise ValueError("Разрешены только HTTPS-источники")
    if not parsed.hostname:
        raise ValueError("У URL источника отсутствует host")
    if _is_private_hostname(parsed.hostname):
        raise ValueError("Скачивание с локальных и private-адресов запрещено")


def get_file_age_hours(filepath: str) -> float:
    """Возвращает возраст файла в часах."""
    if not os.path.exists(filepath):
        return float('inf')
    
    mtime = os.path.getmtime(filepath)
    age = time.time() - mtime
    return age / 3600


def clean_config_content(content: str) -> str:
    """
    Очищает контент конфигов:
    - Заменяет HTML-сущности (&amp; -> &, &lt; -> <, и т.д.)
    - Склеивает разорванные строки конфигов
    - Разделяет склеенные конфиги (когда несколько URL соединены без переноса)
    """
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    content = html.unescape(content)
    # Используем обновленный генератор, преобразуя в список для склейки
    lines = list(_split_glued_entries_gen(content.split('\n'), _CONFIG_START_PATTERN))
    return '\n'.join(lines)


def _download_text_response(session: requests.Session, url: str) -> str:
    """Скачивает текстовый ответ с ограничением по размеру."""
    # Таймаут (connect, read). 2с на соединение достаточно для большинства CDN.
    with session.get(url, timeout=(2, 5), headers={"User-Agent": CHROME_UA}, stream=True) as response:
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type and content_type not in _ALLOWED_TEXT_CONTENT_TYPES:
            raise requests.exceptions.RequestException(f"Неподдерживаемый Content-Type: {content_type}")

        chunks = []
        total_size = 0
        for chunk in response.iter_content(chunk_size=65536, decode_unicode=False):
            if not chunk:
                continue
            total_size += len(chunk)
            if total_size > MAX_DOWNLOAD_SIZE_BYTES:
                raise requests.exceptions.RequestException(
                    f"Файл слишком большой ({total_size} байт), лимит {MAX_DOWNLOAD_SIZE_BYTES}"
                )
            chunks.append(chunk)

    return b"".join(chunks).decode("utf-8", errors="replace")


def _create_session_with_retries() -> requests.Session:
    """Создает сессию requests с автоматическими повторениями при сбоях."""
    session = requests.Session()
    # Уменьшаем количество попыток и время ожидания для быстрой реакции на отсутствие сети
    retry_strategy = Retry(
        total=1,  # 1 повтор (всего 2 попытки). Достаточно для случайных сбоев.
        backoff_factor=0.5,  # 0.5s задержка
        status_forcelist=[429, 500, 502, 503, 504],  # Повторять на эти коды
        allowed_methods=["GET", "HEAD"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)

    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def download_file(url: str, filepath: str, max_age_hours: int = 24, force: bool = False, log_func=None) -> bool:
    """
    Скачивает файл по URL, если он устарел или не существует.
    """
    def _log(msg, tag="info"):
        if log_func:
            log_func(msg, tag)
        else:
            print(msg)

    # Проверяем возраст файла
    if not force:
        age_hours = get_file_age_hours(filepath)
        if age_hours <= max_age_hours:
            _log(f"⏭ {os.path.basename(filepath)} актуален ({age_hours:.1f} ч)", "info")
            return True

    # Создаем директорию если не существует
    dir_name = os.path.dirname(filepath)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    try:
        validate_download_url(url)
        _log(f"Скачивание {os.path.basename(filepath)}...", "info")

        # Используем контекстный менеджер, чтобы сокеты корректно закрывались
        # даже в случае исключений/таймаутов.
        with _create_session_with_retries() as session:
            response_text = _download_text_response(session, url)

        # Очищаем контент
        cleaned_content = clean_config_content(response_text)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(cleaned_content)

        _log(f"✓ Скачано {os.path.basename(filepath)} ({len(cleaned_content)} байт)", "success")
        return True

    except (requests.exceptions.RequestException, ValueError) as e:
        if os.path.exists(filepath):
            _log(f"⚠ Ошибка скачивания (используем старый): {e}", "warning")
            return True
        else:
            _log(f"✗ Ошибка скачивания {os.path.basename(filepath)}: {e}", "error")
            return False


from concurrent.futures import ThreadPoolExecutor


def download_all_tasks(tasks: list, max_age_hours: int = 24, force: bool = False, log_func=None) -> dict:
    """
    Скачивает все файлы для задач параллельно.
    Поддерживает несколько URL для каждой задачи.

    Returns:
        dict с результатами: {'downloaded': [...], 'skipped': [...], 'failed': [...]}
    """
    results = {'downloaded': [], 'skipped': [], 'failed': []}
    download_queue = []

    for task in tasks:
        # Поддержка как одного URL, так и списка URL
        urls = task.get('urls', [task.get('url')])
        raw_files = task.get('raw_files', [task.get('raw_file')])
        pair_count = min(len(urls), len(raw_files))

        if len(urls) != len(raw_files) and log_func:
            log_func(
                f"⚠ {task.get('name', 'Unknown task')}: mismatch urls/raw_files "
                f"({len(urls)} vs {len(raw_files)}), будет обработано пар: {pair_count}",
                "warning",
            )

        for url, filepath in zip(urls[:pair_count], raw_files[:pair_count]):
            if not (url and filepath):
                continue
                
            # Проверяем нужно ли скачивать
            if not force:
                age_hours = get_file_age_hours(filepath)
                if age_hours <= max_age_hours:
                    results['skipped'].append(f"{task['name']}: {os.path.basename(filepath)}")
                    if log_func:
                        log_func(f"⏭ {task['name']}: {os.path.basename(filepath)} актуален", "info")
                    continue
            
            download_queue.append((url, filepath, task['name']))

    if not download_queue:
        return results

    # Скачиваем параллельно
    def _worker(item):
        url, filepath, task_name = item
        success = download_file(
            url=url,
            filepath=filepath,
            max_age_hours=max_age_hours,
            force=force,
            log_func=log_func,
        )
        return success, f"{task_name}: {os.path.basename(filepath)}"

    max_workers = min(len(download_queue), 10)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        worker_results = list(executor.map(_worker, download_queue))

    for success, info in worker_results:
        if success:
            results['downloaded'].append(info)
        else:
            results['failed'].append(info)

    return results
