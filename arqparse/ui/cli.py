#!/usr/bin/env python3
"""
ArcParse - утилита для скачивания и тестирования VPN конфигов.
Интерактивный консольный интерфейс (Без эмодзи).
"""

import os
import time
import subprocess
from datetime import datetime

# Импорты из нашего пакета
from arqparse.config.settings import TASKS, RESULTS_DIR
from arqparse.core.downloader import download_all_tasks
from arqparse.core.parser import read_configs_from_file, read_mtproto_from_file
from arqparse.core.testers import test_xray_configs
from arqparse.core.testers_mtproto import test_mtproto_configs_console
from arqparse.core.xray_manager import ensure_xray
from arqparse.utils.formatting import format_config_name, get_config_id
from arqparse.utils.translator import _
from arqparse.ui.cli_ui import (
    print_banner, print_header, print_subheader,
    print_success, print_error, print_warning, print_info,
    print_results_table, print_summary, print_loading, Colors
)

RESULTS_MERGED_FILENAME = "all_top_vpn.txt"


def _url_key(url: str) -> str:
    """Генерирует ключ для дедупликации URL."""
    return get_config_id(url)


def _test_xray_task(task: dict, skip_xray: bool) -> list:
    """Тестирует Xray-задачу. Возвращает список (url, ping_ms)."""
    if skip_xray:
        print_warning(_("btn_skip") + " (--skip-xray)")
        return []

    current_xray = ensure_xray()
    if not current_xray:
        print_error("Xray not found")
        return []

    raw_files = task.get('raw_files', [])
    all_working_configs = []

    for raw_file in raw_files:
        if not raw_file or not os.path.exists(raw_file):
            continue

        print(f"\n  {Colors.CYAN}Source:{Colors.RESET} {os.path.basename(raw_file)}")
        configs = read_configs_from_file(raw_file)
        if not configs:
            continue

        filtered = [c for c in configs if '127.0.0.1' not in c and 'localhost' not in c]
        remaining = task['required_count'] - len(all_working_configs)
        if remaining <= 0:
            break

        print(f"  {Colors.DIM}{_('msg_testing')} {len(filtered)} configs... (Ctrl+C to skip){Colors.RESET}")

        try:
            results = test_xray_configs(
                configs=filtered,
                target_url=task['target_url'],
                max_ping_ms=task['max_ping_ms'],
                required_count=remaining,
                xray_path=current_xray
            )

            seen_ids = {get_config_id(url) for url, _ in all_working_configs}
            for url, ping_ms in results:
                cid = get_config_id(url)
                if cid and cid not in seen_ids:
                    seen_ids.add(cid)
                    all_working_configs.append((url, ping_ms))

            if len(all_working_configs) >= task['required_count']:
                break

        except KeyboardInterrupt:
            print(f"\n  {Colors.YELLOW}[WRN] File skipped{Colors.RESET}")

    return all_working_configs[:task['required_count']]


def _test_mtproto_task(task: dict) -> list:
    """Тестирует MTProto-задачу."""
    raw_files = task.get('raw_files', [])
    if not raw_files or not os.path.exists(raw_files[0]):
        print_error(f"File not found: {raw_files}")
        return []

    configs = read_mtproto_from_file(raw_files[0])
    if not configs:
        return []

    print(f"  {Colors.DIM}{_('msg_testing')} {len(configs)} proxies...{Colors.RESET}")

    try:
        results = test_mtproto_configs_console(
            configs=configs,
            max_ping_ms=task['max_ping_ms'],
            required_count=task['required_count']
        )
        return [(url, ping_ms) for url, _, ping_ms in results]
    except KeyboardInterrupt:
        return []


def run_task(task: dict, skip_xray: bool = False):
    """Выполняет одну задачу: тест и сохранение."""
    print_subheader(f"{_('msg_testing')} {task['name']}")
    results = []
    
    if task['type'] == 'xray':
        results = _test_xray_task(task, skip_xray)
    elif task['type'] == 'mtproto':
        results = _test_mtproto_task(task)

    if results:
        save_results(task['out_file'], results, task.get('profile_title', 'arqVPN'), task['name'])
        return results
    return []


def save_results(filepath: str, results: list, profile_title: str, config_type: str):
    """Сохраняет результаты."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"#profile-title: {profile_title}\n")
        f.write("#profile-update-interval: 48\n\n")
        for idx, (url, ping_ms) in enumerate(results, 1):
            f.write(f"{format_config_name(url, idx, config_type, ping_ms)}\n")
    print_success(f"{_('msg_saved')}: {len(results)} -> {os.path.basename(filepath)}")


def merge_results():
    """Объединяет всё в один файл с дедупликацией по ID."""
    all_top_vpn_file = os.path.join(RESULTS_DIR, RESULTS_MERGED_FILENAME)
    seen_ids = set()
    configs = []
    
    # Порядок важен
    for task in TASKS:
        if task['type'] == 'xray' and os.path.exists(task['out_file']):
            with open(task['out_file'], 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        cfg_id = get_config_id(line)
                        if cfg_id and cfg_id not in seen_ids:
                            seen_ids.add(cfg_id)
                            configs.append(line)
                            
    if configs:
        with open(all_top_vpn_file, 'w', encoding='utf-8') as f:
            f.write("#profile-title: arqVPN Free | All\n")
            f.write("#profile-update-interval: 48\n")
            f.write("#support-url: https://t.me/arqhub\n\n")
            for c in configs:
                f.write(f"{c}\n")
        print_success(f"{_('msg_merging')} OK")


def show_menu():
    """Отрисовка главного меню."""
    print(f"\n{Colors.WHITE}{Colors.BOLD} {_('cli_menu_title')}{Colors.RESET}")
    print(f" {Colors.CYAN}1.{Colors.RESET} {_('cli_menu_full')}")
    print(f" {Colors.CYAN}2.{Colors.RESET} {_('cli_menu_download')}")
    print(f" {Colors.CYAN}3.{Colors.RESET} {_('cli_menu_test_all')}")
    print(f" {Colors.CYAN}4.{Colors.RESET} {_('cli_menu_select_cat')}")
    print(f" {Colors.CYAN}5.{Colors.RESET} {_('cli_menu_github')}")
    print(f" {Colors.CYAN}0.{Colors.RESET} {_('cli_menu_exit')}")
    print(f"{Colors.DIM}{'-' * 40}{Colors.RESET}")
    return input(f"{Colors.BOLD}{_('cli_choice')}{Colors.RESET}").strip()


def main(force_download: bool = False, skip_xray: bool = False, proxy_url: str = None, no_ui: bool = False):
    """Точка входа интерактивного CLI."""
    if proxy_url:
        os.environ['HTTPS_PROXY'] = proxy_url
        os.environ['HTTP_PROXY'] = proxy_url

    while True:
        print_banner()
        choice = show_menu()

        if choice == '1':
            print_header(_('cli_menu_full').upper())
            download_all_tasks(TASKS, force=force_download)
            all_res = {}
            for task in TASKS:
                all_res[task['name']] = run_task(task, skip_xray)
            merge_results()
            print_summary(all_res)
            input(f"\n{Colors.DIM}{_('cli_press_enter')}{Colors.RESET}")

        elif choice == '2':
            print_header(_('cli_menu_download').upper())
            download_all_tasks(TASKS, force=force_download)
            input(f"\n{Colors.DIM}{_('cli_press_enter')}{Colors.RESET}")

        elif choice == '3':
            print_header(_('cli_menu_test_all').upper())
            all_res = {}
            for task in TASKS:
                all_res[task['name']] = run_task(task, skip_xray)
            merge_results()
            print_summary(all_res)
            input(f"\n{Colors.DIM}{_('cli_press_enter')}{Colors.RESET}")

        elif choice == '4':
            print_header(_('cli_menu_select_cat').upper())
            for i, task in enumerate(TASKS, 1):
                print(f" {Colors.CYAN}{i}.{Colors.RESET} {task['name']}")
            idx = input(f"\n{Colors.BOLD}{_('cli_choice')}{Colors.RESET}")
            if idx.isdigit() and 0 < int(idx) <= len(TASKS):
                task = TASKS[int(idx)-1]
                res = run_task(task, skip_xray)
                if res:
                    print_results_table(res, task['name'])
                input(f"\n{Colors.DIM}{_('cli_press_enter')}{Colors.RESET}")

        elif choice == '5':
            prompt_and_push_to_github()
            input(f"\n{Colors.DIM}{_('cli_press_enter')}{Colors.RESET}")

        elif choice == '0':
            print_info(_('cli_menu_exit'))
            break
        else:
            print_error(_('msg_auth_error'))
            time.sleep(1)


def prompt_and_push_to_github():
    """Запрашивает пользователя об обновлении результатов на GitHub."""
    print_header(_('cli_menu_github').upper())
    response = input(f"{Colors.CYAN}{_('cli_github_confirm')}{Colors.RESET}").strip().lower()
    if response == 'y':
        try:
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            subprocess.run(["git", "add", RESULTS_DIR], cwd=project_dir)
            commit_msg = f"Update VPN configs - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=project_dir, capture_output=True)
            print_loading(_('status_uploading'))
            res = subprocess.run(["git", "push"], cwd=project_dir, capture_output=True, text=True)
            if res.returncode == 0:
                print_success(_('cli_success'))
            else:
                print_error(f"Error: {res.stderr}")
        except Exception as e:
            print_error(f"Git Error: {e}")
