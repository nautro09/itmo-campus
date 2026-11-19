package ru.para.wake;

import android.app.*;
import android.content.*;
import android.provider.AlarmClock;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import org.json.*;

final class NativeClock {
    static final ZoneId MOSCOW = ZoneId.of("Europe/Moscow");
    static final DateTimeFormatter HM = DateTimeFormatter.ofPattern("HH:mm", Locale.ROOT);
    static final long MINUTE = 60_000L;

    static Intent open(){return new Intent(AlarmClock.ACTION_SHOW_ALARMS);}
    static String time(JSONObject row){
        return Instant.ofEpochSecond(row.optLong("at")).atZone(MOSCOW).format(HM);
    }
    static String summary(JSONObject row){
        switch(row.optString("action")){
            case "set": return "Подъём в "+time(row)+" МСК";
            case "cancel": return "Выключить первый будильник в свободный день";
            case "free": return "Свободный день · сохранить будильник";
            case "off": return "Автобудильник выключен в Telegram";
            default: return "Ждём актуальное расписание из ИСУ";
        }
    }
    static boolean actionable(JSONObject row){return actionable(row, Instant.now());}
    static boolean actionable(JSONObject row, Instant now){
        LocalDate today = now.atZone(MOSCOW).toLocalDate();
        String day = row.optString("day");
        if (!today.toString().equals(day) && !today.plusDays(1).toString().equals(day)) return false;
        return "cancel".equals(row.optString("action")) ||
            ("set".equals(row.optString("action")) && row.optLong("at") > now.getEpochSecond());
    }

    // A one-shot system clock takes only HH:mm. Its next occurrence must be the signed instant.
    static boolean nextRingMatches(Instant now, Instant alarm, ZoneId phoneZone){
        ZonedDateTime localNow = now.atZone(phoneZone);
        LocalTime time = alarm.atZone(phoneZone).toLocalTime();
        LocalDate day = localNow.toLocalDate();
        if (!time.isAfter(localNow.toLocalTime())) day = day.plusDays(1);
        return day.atTime(time).atZone(phoneZone).toInstant().equals(alarm);
    }

    static boolean usable(SharedPreferences p, JSONObject row, Instant now){
        if (!actionable(row, now) || p.getBoolean("syncBlocked", false)) return false;
        long sinceReceipt = now.toEpochMilli() - p.getLong("lastReceived", 0);
        long sinceSource = now.getEpochSecond() - p.getLong("checkedAt", 0);
        if (sinceReceipt < 0 || sinceSource < -120) return false;
        // 4.0 cached the online offset ahead of the student's explicit rule.
        // Only a signed response from the corrected calculator contains the source time.
        if ("set".equals(row.optString("action"))) {
            return row.has("basis") && row.has("start") && sinceSource <= 12 * 3600;
        }
        return sinceReceipt <= 30 * MINUTE && sinceSource <= 2 * 3600 + 1800
            && p.getString("syncIssue", "").isEmpty();
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
        SharedPreferences p=Link.prefs(c);
        boolean changed=!revision.equals(p.getString("revision",""));
        SharedPreferences.Editor edit=p.edit().putString("proposal",row.toString()).putString("revision",revision)
            .putLong("lastReceived",System.currentTimeMillis()).putLong("checkedAt",plan.optLong("checked_at"))
            .remove("syncIssue").remove("syncBlocked").remove("ackIssue");
        if(plan.has("settings")) edit.putString("settings",plan.getJSONObject("settings").toString());
        String bot=plan.optString("bot");
        if(bot.matches("[A-Za-z0-9_]{5,32}"))edit.putString("bot",bot);
        if(changed)edit.remove("opened").remove("confirmed").remove("autoStatus").remove("blockedRev")
            .remove("autoAttempt").remove("autoApplied").remove("autoReported").remove("retryAfter")
            .remove("attempts").remove("originalTime").remove("savePending").remove("clockTrace");
        if(!edit.commit())throw new java.io.IOException("storage");
        NotificationManager nm=c.getSystemService(NotificationManager.class);
        if(!actionable(row) || p.getBoolean("autoClock",false)){nm.cancel(9);return;}
        if(!changed || !nm.areNotificationsEnabled())return;
        nm.createNotificationChannel(new NotificationChannel("plan","Изменения подъёма",NotificationManager.IMPORTANCE_DEFAULT));
        PendingIntent show=PendingIntent.getActivity(c,0,new Intent(c,Main.class),PendingIntent.FLAG_IMMUTABLE);
        nm.notify(9,new Notification.Builder(c,"plan").setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle("Расписание · "+day).setContentText(summary(row)).setContentIntent(show).setAutoCancel(true).build());
    }
}
