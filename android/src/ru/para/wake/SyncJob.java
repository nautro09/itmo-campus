package ru.para.wake;

import android.app.job.*;
import android.content.*;

public class SyncJob extends JobService {
    static boolean enable(Context c){
        JobScheduler scheduler=c.getSystemService(JobScheduler.class);
        try {
            if(scheduler.getPendingJob(7)!=null)return true;
            JobInfo job=new JobInfo.Builder(7,new ComponentName(c,SyncJob.class))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPeriodic(15*60*1000L).setPersisted(true).build();
            return scheduler.schedule(job)==JobScheduler.RESULT_SUCCESS;
        } catch(SecurityException | IllegalStateException e) {
            return false;
        }
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
