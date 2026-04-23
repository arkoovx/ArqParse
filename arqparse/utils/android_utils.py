"""Утилиты для работы с фоновым обновлением на Android."""

from arqparse.config.settings import PLATFORM

def schedule_auto_update():
    """
    Планирует автоматическое обновление через WorkManager.
    Условия: Зарядка + Wi-Fi (UNMETERED).
    Интервал: 24 часа.
    """
    if PLATFORM != "android":
        return

    try:
        from jnius import autoclass
        
        ConstraintsBuilder = autoclass('androidx.work.Constraints$Builder')
        NetworkType = autoclass('androidx.work.NetworkType')
        PeriodicWorkRequestBuilder = autoclass('androidx.work.PeriodicWorkRequestBuilder')
        TimeUnit = autoclass('java.util.concurrent.TimeUnit')
        WorkManager = autoclass('androidx.work.WorkManager')
        ExistingPeriodicWorkPolicy = autoclass('androidx.work.ExistingPeriodicWorkPolicy')
        
        # Получаем класс UpdateWorker правильно
        UpdateWorker = autoclass('org.arqparse.UpdateWorker')
        
        constraints = ConstraintsBuilder() \
            .setRequiresCharging(True) \
            .setRequiredNetworkType(NetworkType.UNMETERED) \
            .build()
            
        hours_enum = TimeUnit.valueOf("HOURS")
        
        # Передаем объект класса напрямую
        work_request = PeriodicWorkRequestBuilder(UpdateWorker, 24, hours_enum) \
            .setConstraints(constraints) \
            .addTag("auto_update_configs") \
            .build()
            
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        context = PythonActivity.mActivity
        
        if context:
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "auto_update_configs",
                ExistingPeriodicWorkPolicy.REPLACE,
                work_request
            )
            print("AndroidUtils: Auto-update successfully synchronized with WorkManager", flush=True)
        
    except Exception as e:
        print(f"AndroidUtils: Failed to schedule auto-update: {e}", flush=True)

def cancel_auto_update():
    """Отменяет запланированное обновление."""
    if PLATFORM != "android":
        return
        
    try:
        from jnius import autoclass
        WorkManager = autoclass('androidx.work.WorkManager')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        context = PythonActivity.mActivity
        if context:
            WorkManager.getInstance(context).cancelUniqueWork("auto_update_configs")
            print("AndroidUtils: Auto-update successfully removed from WorkManager", flush=True)
    except Exception as e:
        print(f"AndroidUtils: Failed to cancel auto-update: {e}", flush=True)
