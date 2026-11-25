package ru.para.wake;

import android.Manifest;
import android.app.Activity;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.provider.Settings;
import android.view.accessibility.AccessibilityManager;
import android.view.accessibility.AccessibilityNodeInfo;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.function.BooleanSupplier;
import org.json.JSONObject;

/** On the disposable emulator, bind the production service and leave the app for the system Clock. */
final class BackgroundClockScenario {
    private static void waitFor(BooleanSupplier condition,String reason)throws Exception{
        for(int i=0;i<60;i++){if(condition.getAsBoolean())return;Thread.sleep(160);}
        throw new AssertionError(reason);
    }
    static void run(Instrumentation test,Context c,Activity main)throws Exception{
        PlanScenario.check(Build.HARDWARE.equals("ranchu") || Build.HARDWARE.equals("goldfish"),"requires a disposable Android emulator");
        UiAutomation access=test.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        SharedPreferences prefs=Link.prefs(c);
        String setting=Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES;
        String old=Settings.Secure.getString(c.getContentResolver(),setting);
        int oldEnabled=Settings.Secure.getInt(c.getContentResolver(),Settings.Secure.ACCESSIBILITY_ENABLED,0);
        String service="ru.para.wake/ru.para.wake.ClockAccess";
        Intent clock=ClockAccess.systemClock(c);
        PlanScenario.check(clock!=null,"stock Clock intent on emulator");
        String pkg=clock.getPackage();
        ZonedDateTime when=ZonedDateTime.now(NativeClock.MOSCOW).plusHours(1).truncatedTo(ChronoUnit.MINUTES);
        String rev=new String(new char[64]).replace('\0','c');
        JSONObject row=new JSONObject().put("day",when.toLocalDate().toString()).put("action","set")
            .put("at",when.toEpochSecond()).put("start","09:50").put("basis","rule");
        prefs.edit().putBoolean("autoClock",true).putLong("lastAttempt",System.currentTimeMillis()).commit();
        NativeClock.receive(c,new JSONObject().put("proposal",row).put("revision",rev).put("checked_at",System.currentTimeMillis()/1000));
        access.adoptShellPermissionIdentity(Manifest.permission.WRITE_SECURE_SETTINGS);
        try{
            Settings.Secure.putString(c.getContentResolver(),setting,old==null || old.isEmpty()?service:old+":"+service);
            Settings.Secure.putInt(c.getContentResolver(),Settings.Secure.ACCESSIBILITY_ENABLED,1);
            waitFor(ClockAccess::ready,"system failed to bind real accessibility service");
            ClockAccess.refresh();
            waitFor(()->{
                AccessibilityNodeInfo root=access.getRootInActiveWindow();
                return root!=null && pkg.contentEquals(String.valueOf(root.getPackageName())) &&
                    prefs.getString("clockTrace","").contains("Переключателей");
            },"background service did not read the external stock Clock");
            test.runOnMainSync(main::finish);
            c.getSystemService(AccessibilityManager.class).interrupt();
            Thread.sleep(800);
            PlanScenario.check(ClockAccess.ready() && rev.equals(prefs.getString("clockInProgress","")),
                "finishing the activity or interrupting accessibility feedback cancelled the transaction");
            // The fixture server still serves the real signed 08:30 plan. Nobody opens
            // Main, requests a manual sync or fires the periodic job during this wait.
            long until=android.os.SystemClock.elapsedRealtime()+80_000;
            while(rev.equals(prefs.getString("revision","")) && android.os.SystemClock.elapsedRealtime()<until)
                Thread.sleep(250);
            PlanScenario.check(!rev.equals(prefs.getString("revision","")) &&
                "08:30".equals(NativeClock.time(NativeClock.current(c))),
                "the closed dashboard did not receive the signed plan in the background");
        }finally{
            prefs.edit().putBoolean("autoClock",false).commit();
            Settings.Secure.putString(c.getContentResolver(),setting,old);
            Settings.Secure.putInt(c.getContentResolver(),Settings.Secure.ACCESSIBILITY_ENABLED,oldEnabled);
            access.dropShellPermissionIdentity();
        }
        Link.sync(c);
    }
}
