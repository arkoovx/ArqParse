"""Модуль тестирования VPN конфигов для ArcParse.

Использует упрощённый xray_tester_simple.py основанный на подходе rjsxrd.
"""

import os
import sys
from typing import List, Tuple, Union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arqparse.core.xray_tester_simple import test_batch as xray_test_batch
from arqparse.utils.formatting import format_config_name
from arqparse.core.xray_manager import ensure_xray


def save_xray_results(
    filepath: str,
    working_configs: List[Tuple[str, float]],
    profile_title: str = "arqVPN",
    config_type: str = "VPN",
    required_count: int = 10
) -> bool:
    """Сохраняет результаты тестирования Xray в файл."""
    if not working_configs:
        return False
        
    dir_name = os.path.dirname(filepath)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"#profile-title: {profile_title or 'arqVPN'}\n")
        f.write("#profile-update-interval: 48\n")
        f.write("#support-url: https://t.me/arqhub\n")
        f.write("\n")
        for idx, (url, ping_ms) in enumerate(working_configs[:required_count], 1):
            formatted_url = format_config_name(url, idx, config_type, ping_ms)
            f.write(f"{formatted_url}\n")
    return True


def test_xray_configs(
    configs: List[str],
    target_url: str,
    max_ping_ms: float,
    required_count: int,
    xray_path: str = None,
    concurrency: int = None,
    log_func: callable = None,
    progress_func: callable = None,
    out_file: str = None,
    profile_title: str = None,
    config_type: str = None,
    stop_flag=None,
    skip_flag=None,
) -> Union[Tuple[int, int, int], List[Tuple[str, float]]]:
    """
    Тестирует список Xray конфигов.
    
    Args:
        configs: Список URL конфигов
        target_url: URL для тестирования
        max_ping_ms: Максимальный пинг
        required_count: Сколько рабочих конфигов нужно найти
        xray_path: Путь к Xray бинарнику
        concurrency: Количество потоков
        log_func: Функция для логирования (принимает строку и опциональный тег)
        progress_func: Функция для обновления прогресса (принимает current, total)
        out_file: Файл для сохранения результатов (для GUI)
        profile_title: Название профиля (для GUI)
        config_type: Тип конфига (для GUI)
        stop_flag: threading.Event для полной остановки
        skip_flag: threading.Event для пропуска текущего файла

    Returns:
        Для консоли: List[Tuple[str, float]] отсортированный по пингу
        Для GUI (если out_file задан): Tuple[working, passed, failed]
    """
    def _log(msg, tag="info"):
        if log_func:
            log_func(msg, tag)
    
    def _progress(current, total, suitable=0, required=0):
        if progress_func:
            progress_func(current, total, suitable, required)
    
    # Резолвим путь к Xray если не передан
    if not xray_path:
        xray_path = ensure_xray(log_func=_log)
    
    if not xray_path or not os.path.exists(xray_path):
        _log("Xray не найден или недоступен", "error")
        if out_file is not None:
            return (0, 0, 0)
        else:
            return []
    
    _log(f"Тестирую {len(configs)} конфигов...", "info")

    # Таймаут чуть больше max_ping_ms, чтобы успеть поймать ответ (но не более 15 секунд)
    timeout_sec = min((max_ping_ms / 1000) + 0.5, 15.0)

    # Тестируем конфиги
    try:
        results = xray_test_batch(
            urls=configs,
            xray_path=xray_path,
            concurrency=concurrency or 90,
            timeout=timeout_sec,
            required_count=required_count,
            max_ping_ms=max_ping_ms,
            target_url=target_url,
            log_func=log_func,
            progress_func=progress_func,
            stop_flag=stop_flag,
            skip_flag=skip_flag,
        )
    except Exception as e:
        _log(f"Ошибка при тестировании: {str(e)}", "error")
        if out_file is not None:
            return (0, 0, len(configs))
        else:
            return []
    
    # Если результатов нет
    if not results:
        if out_file is not None:
            return (0, 0, len(configs))
        else:
            return []
    
    # Фильтруем только рабочие конфиги с подходящим пингом
    working_configs = [(url, latency) for url, success, latency in results if success and latency <= max_ping_ms]
    
    # Обновляем прогресс
    _progress(len(results), len(configs), len(working_configs), required_count or 0)
    
    # Сортируем по пингу
    working_configs.sort(key=lambda x: x[1])
    
    # Возвращаем результаты в зависимости от контекста
    if out_file is not None:
        # GUI режим - сохраняем и возвращаем статистику
        working = len(results)
        final_configs = working_configs[:required_count]
        passed = len(final_configs)
        failed = len(configs) - working
        
        if final_configs:
            save_xray_results(out_file, working_configs, profile_title, config_type, required_count)
            _log(f"✓ Сохранено {passed} конфигов", "success")
        else:
            _log("⚠ Рабочих конфигов не найдено. Предыдущий файл сохранен без изменений.", "warning")
        
        return working, passed, failed
    else:
        # Консольный режим
        return working_configs[:required_count]
