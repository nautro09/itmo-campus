package ru.para.wake;
import android.app.*;
import android.content.*;
import android.os.Bundle;
import android.provider.AlarmClock;
import java.time.LocalDate;
import org.json.JSONObject;

public class AlarmCheck extends Instrumentation {
    public void onCreate(Bundle args){super.onCreate(args);start();}
    public void onStart(){
        Bundle result=new Bundle();
        try{
            Context c=getTargetContext();
            android.net.Uri link=new android.net.Uri.Builder().scheme("para-clock").authority("pair")
                .appendQueryParameter("site","https://campus.example")
                .appendQueryParameter("code","abcdefghijklmnopqrstuvwx").build();
            String[] ticket=PairActivity.ticket(new Intent(Intent.ACTION_VIEW,link));
            if(!"https://campus.example".equals(ticket[0]) || !ticket[1].equals("abcdefghijklmnopqrstuvwx"))
                throw new AssertionError("QR parsing");
            try {
                PairActivity.ticket(new Intent(Intent.ACTION_VIEW,link.buildUpon().appendQueryParameter("site","https://other.example").build()));
                throw new AssertionError("duplicate site accepted");
            }catch(java.io.IOException expected){}
            if(!SyncJob.enable(c) || c.getSystemService(android.app.job.JobScheduler.class).getPendingJob(7)==null)
                throw new AssertionError("network sync job");
            Link.prefs(c).edit().putString("cipher","fake-for-offline-test").commit();
            startActivitySync(new Intent(c,Main.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            JSONObject row=new JSONObject().put("day",LocalDate.now(NativeClock.MOSCOW).plusDays(1).toString()).put("action","set").put("at",System.currentTimeMillis()/1000+3600);
            NativeClock.receive(c,new JSONObject().put("revision",new String(new char[64]).replace('\0','a')).put("proposal",row));
            if(!NativeClock.actionable(NativeClock.current(c)))throw new AssertionError("missing proposal");
            Intent clock=NativeClock.open();
            if(!AlarmClock.ACTION_SHOW_ALARMS.equals(clock.getAction()) || clock.getExtras()!=null)throw new AssertionError("unexpected mutation");
            clock.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            c.startActivity(clock);
            Link.prefs(c).edit().clear().commit();
            Activity sample=startActivitySync(new Intent(c,Main.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP));
            Thread.sleep(700);
            ClockScenario.check(this,sample);
            result.putString("result","alarm lifecycle passed");finish(Activity.RESULT_OK,result);
        }catch(Throwable e){result.putString("failure",e.toString());finish(Activity.RESULT_CANCELED,result);}
    }
}
