package ru.para.wake;

import android.content.*;

public class Events extends BroadcastReceiver {
    public void onReceive(Context c,Intent i){
        if("ru.para.wake.RING".equals(i.getAction())){
            String day=i.getStringExtra("day");
            if(day==null) return;
            long at=Alarms.prefs(c).getLong(day,0);
            long late=System.currentTimeMillis()-at;
            if(at==0 || late< -2000 || late>15*60*1000) return;
            Alarms.prefs(c).edit().remove(day).commit();
            c.startForegroundService(new Intent(c,Ring.class));
        } else {Alarms.restore(c);}
    }
}
