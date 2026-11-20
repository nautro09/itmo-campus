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
    private final Runnable checkList=this::resumeFromList;
    private final BroadcastReceiver unlock=new BroadcastReceiver(){
        public void onReceive(Context c,Intent i){onAvailable();}
    };
    private final ConnectivityManager.NetworkCallback network=new ConnectivityManager.NetworkCallback(){
        private Network online;
        public void onCapabilitiesChanged(Network n,NetworkCapabilities caps){
            if(caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)){
                if(!n.equals(online)){online=n;handler.post(()->ClockAccess.this.onAvailable(true));}
            }else if(n.equals(online))online=null;
        }
        public void onLost(Network n){if(n.equals(online))online=null;}
    };
    private String revision="",pkg="",target="";
    private boolean enable,networkRegistered,unlockRegistered,synchronizing;
    private ClockEditor editor;
    private long deadline,startLimit;
    private boolean sawClock;
    private String controls="";
    private SharedPreferences prefs(){return Link.prefs(this);}
    static boolean ready(){return connected!=null;}
    static void refresh(){
        ClockAccess s=connected;
        if(s!=null)s.handler.post(s::begin);
    }
    // Called on the UI thread. A deliberate recheck selects today's first visible ordinary row anew.
    static void restartCheck(Context context){
        ClockAccess service=connected;
        if(service!=null){service.reset();service.handler.removeCallbacks(service.checkList);}
        Link.prefs(context).edit().remove("originalTime").remove("savePending").remove("awaitClock")
            .remove("blockedRev").remove("retryAfter").remove("attempts").remove("clockTrace")
            .remove("autoApplied").remove("autoReported").remove("appliedAt").remove("ackIssue")
            .putString("autoStatus","Запрашиваю план для повторной проверки").apply();
    }
    static void discardLegacySelection(SharedPreferences p,String rev){
        if(!p.contains("originalTime") || p.getBoolean("savePending",false))return;
        // 4.1 recorded the highlighted row even when no change had been sent to Clock.
        SharedPreferences.Editor edit=p.edit().remove("originalTime").remove("savePending");
        if(rev.equals(p.getString("blockedRev","")) &&
            p.getString("autoStatus","").startsWith("Порядок будильников изменился во время проверки")){
            edit.remove("blockedRev").remove("retryAfter").remove("attempts").remove("autoStatus").remove("clockTrace");
        }
        edit.apply();
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
            try{
                getSystemService(ConnectivityManager.class).registerDefaultNetworkCallback(network);
                networkRegistered=true;
            }catch(RuntimeException unavailable){ /* Unlock and the periodic job can still synchronize. */ }
        }
        onAvailable();
    }
    private void onAvailable(){onAvailable(false);}
    private void onAvailable(boolean networkRestored){
        if(connected!=this || !prefs().getBoolean("autoClock",false) || !prefs().contains("cipher") || synchronizing)return;
        synchronizing=true;
        Link.worker.execute(()->{
            try{
                if(networkRestored && !prefs().getString("syncIssue","").isEmpty())Link.sync(this);
                else Link.syncIfDue(this);
            }
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
        discardLegacySelection(prefs(),rev);
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
        Intent clock;
        try{clock=systemClock(this);}catch(SecurityException denied){clock=null;}
        if(clock==null){status("Не удалось однозначно определить штатные Часы. Подробности в настройках.");return;}
        pkg=clock.getPackage();
        revision=rev;
        editor=new ClockEditor(enable,target,prefs().getString("originalTime",""),prefs().getBoolean("savePending",false),
            (original,saving)->rev.equals(prefs().getString("revision","")) && prefs().getBoolean("autoClock",false)
                && !prefs().getBoolean("syncBlocked",false) && unlocked()
                && (!saving || prefs().edit().putString("originalTime",original).putBoolean("savePending",true).commit()),
            time->NativeClock.ringsOnPlanDay(time,row.optString("day"),Instant.now(),ZoneId.systemDefault()));
        int attempts=prefs().getInt("attempts",0)+1;
        prefs().edit().putInt("attempts",attempts).putLong("retryAfter",now.toEpochMilli()+5*NativeClock.MINUTE).apply();
        deadline=SystemClock.elapsedRealtime()+65_000;startLimit=SystemClock.elapsedRealtime()+12_000;
        sawClock=false;controls="";
        try{
            AccessibilityNodeInfo active=getRootInActiveWindow();
            boolean onList=false;
            if(active!=null && pkg.contentEquals(String.valueOf(active.getPackageName()))){
                List<AccessibilityNodeInfo> visible=ClockUi.tree(active);
                onList=ClockUi.label(visible,"Другие будильники")!=null;
                if(!onList && (ClockUi.label(visible,"Изменить будильник")!=null || ClockUi.label(visible,"Добавить будильник")!=null)){
                    waitForList();return;
                }
            }
            if(!onList)startActivity(clock.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        }
        catch(RuntimeException e){fail("Android не открыл штатные Часы",true);return;}
        status("Открываю штатные Часы");
        handler.postDelayed(tick,450);
    }
    private void waitForList(){
        prefs().edit().putString("awaitClock",revision).remove("retryAfter").apply();
        status("Открыт редактор Часов · продолжу после возврата к списку");reset();
    }
    private void fail(String reason,boolean retryable){
        boolean retry=retryable && prefs().getInt("attempts",0)<3;
        SharedPreferences.Editor edit=prefs().edit().putString("clockTrace",editor.trace+(controls.isEmpty()?"":"\n"+controls));
        if(!sawClock)edit.putString("awaitClock",revision);
        if(!retry)edit.putString("blockedRev",revision);
        edit.apply();
        status(reason+(retry?" · повторю автоматически":" · подробности в настройках"));
        reset();
        if(retry)later(5*NativeClock.MINUTE);
    }
    private void success(){
        String rev=revision;
        boolean confirmed=NativeClock.verified(this,rev,enable,target);
        reset();
        if(!confirmed){begin();return;}
        Link.worker.execute(()->{
            try{
                if(!rev.equals(prefs().getString("autoApplied","")))return;
                Link.request(this,"applied",rev);
                if(rev.equals(prefs().getString("autoApplied","")))prefs().edit().putString("autoReported",rev).remove("ackIssue").apply();
            }catch(Exception unavailable){
                prefs().edit().putString("ackIssue","Подтверждение ждёт связи с Telegram").apply();
            }
        });
    }
    public void onAccessibilityEvent(AccessibilityEvent event){
        if(!revision.isEmpty() || !prefs().contains("awaitClock") || !prefs().getBoolean("autoClock",false)
            || !PACKAGES.contains(String.valueOf(event.getPackageName())) || handler.hasCallbacks(checkList))return;
        handler.postDelayed(checkList,200);
    }
    private void resumeFromList(){
        String rev=prefs().getString("awaitClock","");
        if(connected!=this || !revision.isEmpty() || rev.isEmpty() || !rev.equals(prefs().getString("revision","")))return;
        Intent expected;
        try{expected=systemClock(this);}catch(SecurityException denied){return;}
        AccessibilityNodeInfo active=getRootInActiveWindow();
        if(expected==null || active==null || !expected.getPackage().equals(String.valueOf(active.getPackageName())))return;
        try{if(ClockUi.label(ClockUi.tree(active),"Другие будильники")==null)return;}
        catch(RuntimeException transitioning){return;}
        prefs().edit().remove("awaitClock").remove("retryAfter").remove("blockedRev").apply();
        handler.post(check);
    }
    private void step(){
        if(revision.isEmpty())return;
        if(!prefs().getBoolean("autoClock",false) || !revision.equals(prefs().getString("revision","")) ||
            !NativeClock.usable(prefs(),NativeClock.current(this),Instant.now())){reset();begin();return;}
        if(!unlocked()){
            prefs().edit().remove("retryAfter").apply();
            status("Экран заблокирован · продолжу при разблокировке");reset();return;
        }
        if(!sawClock && SystemClock.elapsedRealtime()>startLimit){fail("Android не открыл Часы в фоне",true);return;}
        if(SystemClock.elapsedRealtime()>deadline){fail(editor.trace+" · превышено время ожидания",true);return;}
        try{
            AccessibilityNodeInfo root=getRootInActiveWindow();
            if(root!=null && pkg.contentEquals(String.valueOf(root.getPackageName()))){
                List<AccessibilityNodeInfo> nodes=ClockUi.tree(root);
                if(!editor.started() && ClockUi.label(nodes,"Другие будильники")==null &&
                    (ClockUi.label(nodes,"Изменить будильник")!=null || ClockUi.label(nodes,"Добавить будильник")!=null)){
                    waitForList();return;
                }
                String phase=editor.trace;
                editor.advance(nodes);
                if(!sawClock || !phase.equals(editor.trace) || editor.failure!=null)controls=ClockUi.describe(nodes);
                sawClock=true;
                if(editor.verified)success();
                else if(editor.failure!=null)fail(editor.failure,false);
                else if(editor.deferTime!=null){
                    ZonedDateTime local=ZonedDateTime.now();
                    ZonedDateTime next=local.toLocalDate().atTime(LocalTime.parse(editor.deferTime)).atZone(local.getZone());
                    if(!next.isAfter(local))next=next.plusDays(1);
                    long retry=next.toInstant().toEpochMilli()+NativeClock.MINUTE;
                    prefs().edit().putLong("retryAfter",retry).remove("originalTime").remove("savePending").apply();
                    status("У первого будильника другой день звонка · сохраняю его");
                    reset();later(retry-System.currentTimeMillis());
                }
            }else if(editor.started() && root!=null){fail("Экран Часов закрыт",true);return;}
        }catch(RuntimeException e){fail("Не удалось прочитать элементы Часов",true);}
        if(!revision.isEmpty())handler.postDelayed(tick,500);
    }
}
