"""Совместимый non-interactive entrypoint для пакетного запуска."""

from __future__ import annotations

import os

from arqparse.config.settings import RESULTS_DIR, TASKS
from arqparse.core.downloader import download_all_tasks
from arqparse.core.xray_manager import ensure_xray
from arqparse.ui.cli import merge_results, run_task
from arqparse.ui.cli_ui import (
    print_banner,
    print_error,
    print_header,
    print_logo,
    print_success,
    print_summary,
)


def prompt_and_push_to_github():
    """Совместимый placeholder для старого сценария запуска."""
    return None


def stage_test_task(task: dict, skip_xray: bool = False):
    """Тестирует одну задачу в пакетном режиме."""
    return run_task(task, skip_xray=skip_xray)


def main(force_download: bool = False, skip_xray: bool = False, proxy_url: str = None, no_ui: bool = False):
    """Пакетный сценарий без интерактивного меню."""
    if proxy_url:
        os.environ["HTTPS_PROXY"] = proxy_url
        os.environ["HTTP_PROXY"] = proxy_url

    if not no_ui:
        print_banner()
        print_logo()
        print_header("ПАКЕТНЫЙ ЗАПУСК")

    download_results = download_all_tasks(TASKS, force=force_download)
    has_inputs = bool(download_results.get("downloaded") or download_results.get("skipped"))
    if not has_inputs:
        print_error("Нет доступных входных файлов для тестирования")
        raise SystemExit(1)

    if not skip_xray:
        ensure_xray()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    summary = {}
    for task in TASKS:
        summary[task["name"]] = stage_test_task(task, skip_xray=skip_xray)

    merge_results()
    if not no_ui:
        print_summary(summary)
        print_success("Пакетный запуск завершен")

    return summary
