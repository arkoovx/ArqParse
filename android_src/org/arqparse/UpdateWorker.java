package org.arqparse;

import android.content.Context;
import android.content.Intent;
import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
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
            
            // Название класса сервиса формируется как: <package_domain>.<package_name>.Service<CapitalizedServiceName>
            // В нашем случае: org.arqparse.arqparse.ServiceUpdate
            Intent intent = new Intent();
            intent.setClassName(context.getPackageName(), "org.arqparse.arqparse.ServiceUpdate");
            intent.putExtra("serviceEntrypoint", "service.py");
            intent.putExtra("serviceTitle", "arqParse Auto-Update");
            intent.putExtra("serviceDescription", "Updating configurations...");
            intent.putExtra("pythonServiceArgument", "update");
            
            // Запускаем сервис
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                context.startForegroundService(intent);
            } else {
                context.startService(intent);
            }
            
            return Result.success();
        } catch (Exception e) {
            Log.e(TAG, "Failed to start Python update service", e);
            return Result.retry();
        }
    }
}
