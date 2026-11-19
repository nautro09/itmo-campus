package ru.para.wake;

import android.accessibilityservice.AccessibilityService;
import android.app.KeyguardManager;
import android.content.*;
import android.content.pm.*;
import android.net.*;
import android.os.*;
import android.view.accessibility.*;
import java.time.*;
import java.util.*;
import org.json.JSONObject;

public final class ClockAccess extends AccessibilityService {
    private static volatile ClockAccess connected;
    private static final List<String> PACKAGES=Arrays.asList(
        "com.hihonor.deskclock","com.honor.deskclock","com.huawei.deskclock","com.android.deskclock");
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable tick=this::step;
    private final Runnable check=this::onAvailable;
    private final BroadcastReceiver unlock=new BroadcastReceiver(){
        public void onReceive(Context c,Intent i){onAvailable();}
    };
    private final ConnectivityManager.NetworkCallback network=new ConnectivityManager.NetworkCallback(){
        public void onCapabilitiesChanged(Network n,NetworkCapabilities caps){
            if(caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED))handler.post(check);
        }
    };
    private String revision="",pkg="",target="";
    private boolean enable,networkRegistered,unlockRegistered,synchronizing;
    private ClockEditor editor;
    private long deadline;
    private SharedPreferences prefs(){return Link.prefs(this);}
    static boolean ready(){return connected!=null;}
    static void refresh(){
        ClockAccess s=connected;
        if(s!=null)s.handler.post(s::begin);
    }
    static void stopLocal(){
        ClockAccess s=connected;
        if(s!=null)s.handler.post(()->{s.reset();s.disableSelf();});
    }
    @Override public void onServiceConnected(){
        connected=this;
        if(!unlockRegistered){
            IntentFilter filter=new IntentFilter(Intent.ACTION_USER_PRESENT);
            if(Build.VERSION.SDK_INT>=33)registerReceiver(unlock,filter,Context.RECEIVER_NOT_EXPORTED);
            else registerReceiver(unlock,filter);
            unlockRegistered=true;
        }
        if(!networkRegistered){
            getSystemService(ConnectivityManager.class).registerDefaultNetworkCallback(network);
            networkRegistered=true;
        }
        onAvailable();
    }
    private void onAvailable(){
        if(connected!=this || !prefs().getBoolean("autoClock",false) || !prefs().contains("cipher") || synchronizing)return;
        synchronizing=true;
        Link.worker.execute(()->{
            try{Link.syncIfDue(this);}
            catch(Exception ignored){ /* Link stores the cause and schedules a cached-plan check. */ }
            finally{handler.post(()->synchronizing=false);}
        });
    }
    @Override public void onDestroy(){
        if(connected==this)connected=null;
        if(unlockRegistered)unregisterReceiver(unlock);
        if(networkRegistered)getSystemService(ConnectivityManager.class).unregisterNetworkCallback(network);
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }
    public void onInterrupt(){reset();}
    private void reset(){handler.removeCallbacks(tick);revision="";editor=null;}
    private boolean unlocked(){
        return getSystemService(PowerManager.class).isInteractive() && !getSystemService(KeyguardManager.class).isKeyguardLocked();
    }
    private static boolean trusted(PackageManager pm,String pkg){
        if(!PACKAGES.contains(pkg))return false;
        try{return (pm.getApplicationInfo(pkg,0).flags & ApplicationInfo.FLAG_SYSTEM)!=0;}
        catch(PackageManager.NameNotFoundException unavailable){return false;}
    }
    static Intent systemClock(Context c){
        PackageManager pm=c.getPackageManager();
        Intent show=NativeClock.open();
        ResolveInfo preferred=pm.resolveActivity(show,PackageManager.MATCH_DEFAULT_ONLY);
        if(preferred!=null && trusted(pm,preferred.activityInfo.packageName))return show.setPackage(preferred.activityInfo.packageName);
        Set<String> candidates=new HashSet<>();
        for(ResolveInfo info:pm.queryIntentActivities(show,0)){
            if(trusted(pm,info.activityInfo.packageName))candidates.add(info.activityInfo.packageName);
        }
        if(candidates.size()==1)return show.setPackage(candidates.iterator().next());
        if(!candidates.isEmpty())return null;
        // Some stock clocks expose a launcher entry only. The editor still requires the alarm list.
        Intent only=null;
        for(String name:PACKAGES){
            if(!trusted(pm,name))continue;
            Intent launcher=pm.getLaunchIntentForPackage(name);
            if(launcher==null)continue;
            if(only!=null)return null;
            only=launcher.setPackage(name);
        }
        return only;
    }
    private void status(String text){
        if(!text.equals(prefs().getString("autoStatus","")))prefs().edit().putString("autoStatus",text).apply();
    }
    private void later(long ms){
        handler.removeCallbacks(check);
        handler.postDelayed(check,Math.max(2_000,ms));
    }
    private void begin(){
        if(connected!=this || !prefs().getBoolean("autoClock",false) || !prefs().contains("cipher"))return;
        String rev=prefs().getString("revision","");
        if(!revision.isEmpty()){
            if(revision.equals(rev))return;
            reset();
        }
        if(rev.isEmpty() || rev.equals(prefs().getString("autoApplied","")) || rev.equals(prefs().getString("blockedRev","")))return;
        JSONObject row=NativeClock.current(this);
        Instant now=Instant.now();
        if(!NativeClock.usable(prefs(),row,now))return;
        enable="set".equals(row.optString("action"));
        ZonedDateTime moscow=now.atZone(NativeClock.MOSCOW);
        if(enable){
            Instant alarm=Instant.ofEpochSecond(row.optLong("at"));
            ZoneId zone=ZoneId.systemDefault();
            if(!NativeClock.nextRingMatches(now,alarm,zone)){
                status("Жду, когда ближайший звонок в Часах придётся на нужную дату");
                long wait=Duration.between(now,alarm.atZone(zone).minusDays(1).toInstant()).toMillis();
                if(wait>0)later(wait+1000);
                return;
            }
            target=alarm.atZone(zone).format(NativeClock.HM);
        }else if(row.optString("day").equals(moscow.toLocalDate().plusDays(1).toString()) && moscow.getHour()<18){
            status("Свободный день завтра · проверю выключение после 18:00 МСК");
            later(Duration.between(now,moscow.toLocalDate().atTime(18,0).atZone(NativeClock.MOSCOW)).toMillis());
            return;
        }
        if(!unlocked()){status("План получен · применю при разблокировке");return;}
        long remaining=prefs().getLong("retryAfter",0)-now.toEpochMilli();
        if(remaining>0){later(Math.min(remaining,15*NativeClock.MINUTE));return;}
        Intent clock=systemClock(this);
        if(clock==null){status("Не удалось однозначно определить штатные Часы. Подробности в настройках.");return;}
        pkg=clock.getPackage();
        revision=rev;
        editor=new ClockEditor(enable,target,prefs().getString("originalTime",""),prefs().getBoolean("savePending",false),
            (original,saving)->prefs().edit().putString("originalTime",original).putBoolean("savePending",saving).commit());
        int attempts=prefs().getInt("attempts",0)+1;
        prefs().edit().putInt("attempts",attempts).putLong("retryAfter",now.toEpochMilli()+5*NativeClock.MINUTE).apply();
        deadline=SystemClock.elapsedRealtime()+65_000;
        try{startActivity(clock.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));}
        catch(RuntimeException e){fail("Android не открыл штатные Часы",true);return;}
        status("Открываю штатные Часы");
        handler.postDelayed(tick,450);
    }
    private void fail(String reason,boolean retryable){
        boolean retry=retryable && prefs().getInt("attempts",0)<3;
        SharedPreferences.Editor edit=prefs().edit().putString("clockTrace",editor.trace);
        if(!retry)edit.putString("blockedRev",revision);
        edit.apply();
        status(reason+(retry?" · повторю автоматически":" · подробности в настройках"));
        reset();
        if(retry)later(5*NativeClock.MINUTE);
    }
    private void success(){
        String rev=revision;
        String detail=enable?"В штатных Часах включён на "+target:"Штатный будильник выключен";
        prefs().edit().putString("autoApplied",rev).putString("autoStatus",detail)
            .putLong("appliedAt",System.currentTimeMillis()).remove("retryAfter").remove("originalTime").remove("savePending")
            .remove("blockedRev").remove("clockTrace").commit();
        reset();
        Link.worker.execute(()->{
            try{
                if(!rev.equals(prefs().getString("revision","")))return;
                Link.request(this,"applied",rev);
                prefs().edit().putString("autoReported",rev).remove("ackIssue").apply();
            }catch(Exception unavailable){
                prefs().edit().putString("ackIssue","Подтверждение ждёт связи с Telegram").apply();
            }
        });
    }
    public void onAccessibilityEvent(AccessibilityEvent event){ /* Only inspect the clock during our own bounded edit. */ }
    private void step(){
        if(revision.isEmpty())return;
        if(!prefs().getBoolean("autoClock",false) || !revision.equals(prefs().getString("revision","")) ||
            !NativeClock.usable(prefs(),NativeClock.current(this),Instant.now())){reset();begin();return;}
        if(!unlocked()){
            prefs().edit().remove("retryAfter").apply();
            status("Экран заблокирован · продолжу при разблокировке");reset();return;
        }
        if(SystemClock.elapsedRealtime()>deadline){fail(editor.trace+" · превышено время ожидания",true);return;}
        try{
            AccessibilityNodeInfo root=getRootInActiveWindow();
            if(root!=null && pkg.contentEquals(String.valueOf(root.getPackageName()))){
                editor.advance(ClockUi.tree(root));
                if(editor.verified)success();
                else if(editor.failure!=null)fail(editor.failure,false);
            }else if(editor.started() && root!=null){fail("Экран Часов закрыт",true);return;}
        }catch(RuntimeException e){fail("Не удалось прочитать элементы Часов",true);}
        if(!revision.isEmpty())handler.postDelayed(tick,500);
    }
}
