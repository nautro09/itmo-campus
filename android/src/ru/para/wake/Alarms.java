package ru.para.wake;

import android.app.*;
import android.content.*;
import android.os.Build;
import java.io.IOException;
import java.time.*;
import org.json.*;

final class Alarms {
    static final int FLAGS=PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT;
    static final ZoneId MOSCOW=ZoneId.of("Europe/Moscow");
    static SharedPreferences prefs(Context c){return c.createDeviceProtectedStorageContext().getSharedPreferences("times",0);}
    static AlarmManager manager(Context c){return c.getSystemService(AlarmManager.class);}
    static boolean exact(Context c){return Build.VERSION.SDK_INT<31 || manager(c).canScheduleExactAlarms();}
    static PendingIntent signal(Context c,LocalDate day){
        return PendingIntent.getBroadcast(c,(int)day.toEpochDay(),new Intent(c,Events.class).setAction("ru.para.wake.RING").putExtra("day",day.toString()),FLAGS);
    }
    static PendingIntent show(Context c){return PendingIntent.getActivity(c,0,new Intent(c,Main.class),FLAGS);}
    static void schedule(Context c,LocalDate day,long at){
        manager(c).setAlarmClock(new AlarmManager.AlarmClockInfo(at,show(c)),signal(c,day));
    }
    static synchronized void apply(Context c,JSONArray days) throws Exception {
        LocalDate today=LocalDate.now(MOSCOW);
        if(days.length()!=2) throw new IOException("Неполный план.");
        for(int i=0;i<2;i++){
            JSONObject row=days.getJSONObject(i);
            LocalDate day=today.plusDays(i);
            if(!day.toString().equals(row.getString("day"))) throw new IOException("Проверь дату телефона.");
            String action=row.getString("action");
            long at=row.optLong("at",0);
            if("set".equals(action)){
                long delta=at-System.currentTimeMillis()/1000;
                if(delta>172800 || delta<=0 || !exact(c)) throw new IOException("Проверь время и разрешение на будильники.");
                if(Build.VERSION.SDK_INT>=33 && c.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=0)
                    throw new IOException("Разреши уведомления для управления звонком.");
            } else if(!"cancel".equals(action) && !"keep".equals(action)) throw new IOException("Недействительный план.");
        }
        for(int i=0;i<2;i++){
            JSONObject row=days.getJSONObject(i);
            LocalDate day=today.plusDays(i);
            String action=row.getString("action");
            if("cancel".equals(action)){
                manager(c).cancel(signal(c,day));
                prefs(c).edit().remove(day.toString()).commit();
            } else if("set".equals(action)){
                long at=row.getLong("at")*1000;
                schedule(c,day,at);
                if(!prefs(c).edit().putLong(day.toString(),at).commit()) throw new IOException("Не удалось сохранить время подъёма.");
            }
        }
        for(String day:prefs(c).getAll().keySet()) if(LocalDate.parse(day).isBefore(today)) prefs(c).edit().remove(day).apply();
    }
    static synchronized void restore(Context c){
        if(!exact(c)) return;
        for(String day:prefs(c).getAll().keySet()){
            long at=prefs(c).getLong(day,0);
            if(at>System.currentTimeMillis()) schedule(c,LocalDate.parse(day),at);
        }
    }
    static synchronized void clear(Context c){
        for(String day:prefs(c).getAll().keySet()) manager(c).cancel(signal(c,LocalDate.parse(day)));
        prefs(c).edit().clear().commit();
    }
}
