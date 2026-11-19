package ru.para.wake;

import android.app.job.*;
import android.content.*;

public class SyncJob extends JobService {
    static void enable(Context c){
        JobInfo job=new JobInfo.Builder(7,new ComponentName(c,SyncJob.class))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPeriodic(15*60*1000L).setPersisted(true).build();
        c.getSystemService(JobScheduler.class).schedule(job);
    }
    public boolean onStartJob(JobParameters params){
        Link.worker.execute(()->{
            try{Link.sync(this);Main.result(this,"Синхронизация выполнена");}
            catch(Exception e){Main.result(this,"Проверка отложена. Проверь время в системных Часах.");}
            jobFinished(params,false);
        });
        return true;
    }
    public boolean onStopJob(JobParameters params){return true;}
}
