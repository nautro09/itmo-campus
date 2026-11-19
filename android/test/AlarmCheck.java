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
            startActivitySync(new Intent(c,Main.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            JSONObject row=new JSONObject().put("day",LocalDate.now(NativeClock.MOSCOW).plusDays(1).toString()).put("action","set").put("at",System.currentTimeMillis()/1000+3600);
            NativeClock.receive(c,new JSONObject().put("revision",new String(new char[64]).replace('\0','a')).put("proposal",row));
            if(!NativeClock.actionable(NativeClock.current(c)))throw new AssertionError("missing proposal");
            Intent clock=NativeClock.open();
            if(!AlarmClock.ACTION_SHOW_ALARMS.equals(clock.getAction()) || clock.getExtras()!=null)throw new AssertionError("unexpected mutation");
            clock.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            c.startActivity(clock);
            result.putString("result","alarm lifecycle passed");finish(Activity.RESULT_OK,result);
        }catch(Throwable e){result.putString("failure",e.toString());finish(Activity.RESULT_CANCELED,result);}
    }
}
