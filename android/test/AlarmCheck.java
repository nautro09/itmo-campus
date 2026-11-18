package ru.para.wake;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import java.time.LocalDate;
import org.json.JSONArray;
import org.json.JSONObject;

public class AlarmCheck extends Instrumentation {
    public void onCreate(Bundle args){super.onCreate(args);start();}
    public void onStart(){
        Bundle result=new Bundle();
        Context c=getTargetContext();
        try{
            LocalDate today=LocalDate.now(Alarms.MOSCOW);
            JSONArray days=new JSONArray();
            JSONObject first=new JSONObject().put("day",today.toString()).put("action","set");
            days.put(first.put("at",System.currentTimeMillis()/1000+120));
            days.put(new JSONObject().put("day",today.plusDays(1).toString()).put("action","keep"));
            Alarms.apply(c,days);
            long scheduled=Alarms.prefs(c).getLong(today.toString(),0);
            if(scheduled<=0 || Alarms.manager(c).getNextAlarmClock()==null) throw new AssertionError("set");
            first.put("action","keep");
            Alarms.apply(c,days);
            if(Alarms.prefs(c).getLong(today.toString(),0)!=scheduled) throw new AssertionError("keep");
            first.put("action","cancel");
            Alarms.apply(c,days);
            if(Alarms.prefs(c).contains(today.toString())) throw new AssertionError("cancel");
            first.put("action","set").put("at",System.currentTimeMillis()/1000+6);
            Alarms.apply(c,days);
            for(int i=0;i<25 && Alarms.prefs(c).contains(today.toString());i++) Thread.sleep(1000);
            if(Alarms.prefs(c).contains(today.toString())) throw new AssertionError("delivery");
            result.putString("result","alarm lifecycle passed");
            finish(Activity.RESULT_OK,result);
        }catch(Throwable e){
            result.putString("failure",e.toString());finish(Activity.RESULT_CANCELED,result);
        }finally{c.stopService(new Intent(c,Ring.class));Alarms.clear(c);}
    }
}
