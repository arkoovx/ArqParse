"""Модуль тестирования VPN конфигов для ArcParse.

Использует упрощённый xray_tester_simple.py основанный на подходе rjsxrd.
"""

import os
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xray_tester_simple import test_batch as xray_test_batch


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
    config_type: str = None
) -> Tuple[int, int, int]:
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
    
    Returns:
        Для консоли: List[Tuple[str, float]] отсортированный по пингу
        Для GUI: Tuple[working, passed, failed]
    """
    def _log(msg, tag="info"):
        if log_func:
            log_func(msg, tag)
    
    def _progress(current, total):
        if progress_func:
            progress_func(current, total)
    
    if not xray_path:
        xray_path = os.path.join(os.path.dirname(__file__), "bin", "xray")
    
    if not os.path.exists(xray_path):
        _log(f"Xray не найден: {xray_path}", "error")
        if out_file is not None:
            return (0, 0, 0)  # работающих, успешных, ошибок
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
    _progress(len(results), len(configs))
    
    # Сортируем по пингу
    working_configs.sort(key=lambda x: x[1])
    
    # Возвращаем результаты в зависимости от контекста
    if out_file is not None:
        # GUI режим - сохраняем и возвращаем статистику
        passed = len(working_configs[:required_count])
        failed = len([x for x in results if not x[1] or x[2] > max_ping_ms])
        working = len([x for x in results if x[1]])
        
        # Сохраняем результаты
        if working_configs:
            os.makedirs(os.path.dirname(out_file), exist_ok=True)
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(f"#profile-title: {profile_title or 'arqVPN'}\n")
                f.write("#profile-update-interval: 48\n")
                f.write("#support-url: https://t.me/arqhub\n")
                f.write("\n")
                for url, ping_ms in working_configs[:required_count]:
                    f.write(f"{url}\n")
            _log(f"✓ Сохранено {len(working_configs[:required_count])} конфигов", "success")
        else:
            _log(f"⚠ Рабочих конфигов не найдено", "warning")
        
        return working, passed, failed
    else:
        # Консольный режим
        return working_configs[:required_count]
