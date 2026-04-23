package org.arqparse;

import android.content.Context;
import android.content.Intent;
import android.os.Build;
import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import org.kivy.android.PythonService;
import android.util.Log;

public class UpdateWorker extends Worker {
    private static final String TAG = "UpdateWorker";

    public UpdateWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        Log.d(TAG, "WorkManager trigger: Starting update service...");
        try {
            Context context = getApplicationContext();
            
            // В Android 12+ запуск обычного background service из Worker может вызвать исключение.
            // PythonService.start внутри p4a умеет обрабатывать запуск.
            // Аргумент "update" соответствует названию сервиса в buildozer.spec
            
            PythonService.start(context, "arqParse Auto-Update", "service.py", "update");
            
            return Result.success();
        } catch (Exception e) {
            Log.e(TAG, "Failed to start Python update service", e);
            // Если ошибка временная (например, система перегружена), попробуем позже
            return Result.retry();
        }
    }
}
