package ru.para.wake;

import android.app.job.*;
import android.content.*;

public class SyncJob extends JobService {
    static void enable(Context c){
        JobScheduler scheduler=c.getSystemService(JobScheduler.class);
        if(scheduler.getPendingJob(7)!=null)return;
        JobInfo job=new JobInfo.Builder(7,new ComponentName(c,SyncJob.class))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPeriodic(15*60*1000L).setPersisted(true).build();
        scheduler.schedule(job);
    }
    public boolean onStartJob(JobParameters params){
        Link.worker.execute(()->{
            try{Link.sync(this);Main.result(this,"Синхронизация выполнена");}
            catch(Exception e){Main.result(this,"Ошибка синхронизации. Проверь сеть и адрес сервера.");}
            jobFinished(params,false);
        });
        return true;
    }
    public boolean onStopJob(JobParameters params){return true;}
}
