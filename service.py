import os
import sys
import time

# Настройка путей для Android
if 'PYTHON_SERVICE_ARGUMENT' in os.environ:
    from android.storage import app_storage_path
    from android.runnable import run_on_ui_thread
    
    # Путь к корню приложения
    app_root = os.getcwd()
    if app_root not in sys.path:
        sys.path.append(app_root)

from arqparse.utils.settings_manager import get_tasks
from arqparse.core.downloader import download_all_tasks

def set_foreground_notification():
    """Устанавливает foreground уведомление для сервиса (Android 12+)."""
    try:
        from jnius import autoclass
        Context = autoclass('android.content.Context')
        PythonService = autoclass('org.kivy.android.PythonService')
        service = PythonService.mService
        
        # Настройка уведомления через сервис Kivy
        # Это предотвратит немедленную остановку сервиса системой
        service.setAutoStopService(True)
    except Exception as e:
        print(f"UpdateService: Notification error: {e}", flush=True)

def run_update():
    print("UpdateService: Background process started", flush=True)
    set_foreground_notification()
    
    try:
        tasks = get_tasks()
        if not tasks:
            print("UpdateService: No tasks found", flush=True)
            return

        # Небольшая пауза, чтобы система успела стабилизировать сетевое соединение
        time.sleep(2)
        
        results = download_all_tasks(
            tasks, 
            max_age_hours=20, 
            force=False, 
            log_func=lambda msg, tag: print(f"[{tag.upper()}] {msg}", flush=True)
        )
        
        print(f"UpdateService: Success. Results: {results}", flush=True)
    except Exception as e:
        print(f"UpdateService: Error: {e}", flush=True, file=sys.stderr)

if __name__ == '__main__':
    run_update()
