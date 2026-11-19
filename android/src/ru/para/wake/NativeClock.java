package ru.para.wake;

import android.app.*;
import android.content.*;
import android.provider.AlarmClock;
import java.time.*;
import java.time.format.DateTimeFormatter;
import org.json.*;

final class NativeClock {
    static final ZoneId MOSCOW=ZoneId.of("Europe/Moscow");
    static Intent open(){return new Intent(AlarmClock.ACTION_SHOW_ALARMS);}
    static String time(JSONObject row){
        return Instant.ofEpochSecond(row.optLong("at")).atZone(MOSCOW).format(DateTimeFormatter.ofPattern("HH:mm"));
    }
    static String summary(JSONObject row){
        switch(row.optString("action")){
            case "set": return "Включи первый сверху на "+time(row)+" МСК";
            case "cancel": return "Выключи первый сверху на свободный день";
            case "free": return "Свободный день · оставь будильник как есть";
            case "off": return "Связь с расписанием выключена";
            default: return "Нет свежего решения · оставь будильник как есть";
        }
    }
    static boolean actionable(JSONObject row){
        return row.optString("day").compareTo(LocalDate.now(MOSCOW).toString())>=0 &&
            ("cancel".equals(row.optString("action")) || ("set".equals(row.optString("action")) && row.optLong("at")>System.currentTimeMillis()/1000));
    }
    static JSONObject current(Context c){
        try{return new JSONObject(Link.prefs(c).getString("proposal","{}"));}catch(JSONException e){return new JSONObject();}
    }
    static void receive(Context c,JSONObject plan) throws Exception {
        JSONObject row=plan.getJSONObject("proposal");
        LocalDate day=LocalDate.parse(row.getString("day")), today=LocalDate.now(MOSCOW);
        if(day.isBefore(today)||day.isAfter(today.plusDays(1)))throw new JSONException("date");
        String revision=plan.getString("revision");
        if(!revision.matches("[a-f0-9]{64}"))throw new JSONException("revision");
        android.content.SharedPreferences p=Link.prefs(c);
        boolean changed=!revision.equals(p.getString("revision",""));
        android.content.SharedPreferences.Editor edit=p.edit().putString("proposal",row.toString()).putString("revision",revision);
        if(plan.has("settings")) edit.putString("settings",plan.getJSONObject("settings").toString());
        edit.putLong("lastReceived",System.currentTimeMillis());
        if(changed)edit.remove("opened").remove("confirmed");
        if(!edit.commit())throw new java.io.IOException("storage");
        NotificationManager nm=c.getSystemService(NotificationManager.class);
        if(!actionable(row)){nm.cancel(9);return;}
        if(!changed || !nm.areNotificationsEnabled())return;
        nm.createNotificationChannel(new NotificationChannel("plan","Изменения подъёма",NotificationManager.IMPORTANCE_DEFAULT));
        PendingIntent show=PendingIntent.getActivity(c,0,new Intent(c,Main.class),PendingIntent.FLAG_IMMUTABLE);
        nm.notify(9,new Notification.Builder(c,"plan").setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle("Расписание · "+day).setContentText(summary(row)).setContentIntent(show).setAutoCancel(true).build());
    }
}
