package ru.para.wake;

import android.accessibilityservice.AccessibilityService;
import android.app.KeyguardManager;
import android.content.*;
import android.content.pm.*;
import android.os.*;
import android.view.accessibility.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.json.JSONObject;

public final class ClockAccess extends AccessibilityService {
    private static volatile ClockAccess connected;
    private static final Set<String> PACKAGES=new HashSet<>(Arrays.asList(
        "com.hihonor.deskclock","com.honor.deskclock","com.android.deskclock"));
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable tick=this::step;
    private final BroadcastReceiver unlock=new BroadcastReceiver(){
        public void onReceive(Context c, Intent i){begin();}
    };
    private String revision="",pkg="",target="";
    private boolean enable;
    private ClockEditor editor;
    private long deadline;
    private SharedPreferences prefs(){return Link.prefs(this);}
    static boolean ready(){return connected!=null;}
    static void refresh(){
        ClockAccess service=connected;
        if(service!=null)service.handler.post(service::begin);
    }
    static void stopLocal(){
        ClockAccess service=connected;
        if(service!=null)service.handler.post(()->{service.reset();service.disableSelf();});
    }
    @Override public void onServiceConnected(){
        connected=this;
        IntentFilter filter=new IntentFilter(Intent.ACTION_USER_PRESENT);
        if(Build.VERSION.SDK_INT>=33)registerReceiver(unlock,filter,Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(unlock,filter);
        begin();
    }
    @Override public void onDestroy(){
        if(connected==this){connected=null;unregisterReceiver(unlock);}
        reset();super.onDestroy();
    }
    public void onInterrupt(){reset();}
    private void reset(){handler.removeCallbacks(tick);revision="";editor=null;}
    private boolean unlocked(){
        return getSystemService(PowerManager.class).isInteractive() && !getSystemService(KeyguardManager.class).isKeyguardLocked();
    }
    private boolean fresh(){
        long age=System.currentTimeMillis()-prefs().getLong("lastReceived",0);
        return age>=0 && age<=30*60_000L;
    }
    private String clockPackage(){
        String only="";
        for(ResolveInfo info:getPackageManager().queryIntentActivities(NativeClock.open(),0)){
            String candidate=info.activityInfo.packageName;
            if(PACKAGES.contains(candidate) && (info.activityInfo.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM)!=0){
                if(!only.isEmpty() && !only.equals(candidate))return "";
                only=candidate;
            }
        }
        return only;
    }
    private void status(String text){prefs().edit().putString("autoStatus",text).apply();}
    private void begin(){
        if(!revision.isEmpty() || !prefs().getBoolean("autoClock",false) || !prefs().contains("cipher") || !fresh())return;
        JSONObject row=NativeClock.current(this);
        String rev=prefs().getString("revision","");
        if(rev.isEmpty() || rev.equals(prefs().getString("autoApplied","")) ||
           rev.equals(prefs().getString("autoAttempt","")) || !NativeClock.actionable(row))return;
        ZonedDateTime now=ZonedDateTime.now(NativeClock.MOSCOW);
        if(row.optString("day").equals(now.toLocalDate().plusDays(1).toString()) && now.getHour()<18){
            status("План на завтра · применение после 18:00 МСК");return;
        }
        if(!unlocked()){status("Ожидаю разблокировки телефона");return;}
        enable="set".equals(row.optString("action"));
        if(enable){
            ZonedDateTime at=Instant.ofEpochSecond(row.optLong("at")).atZone(ZoneId.systemDefault());
            ZonedDateTime local=ZonedDateTime.now(at.getZone());
            LocalDate next=at.toLocalTime().isAfter(local.toLocalTime())?local.toLocalDate():local.toLocalDate().plusDays(1);
            if(!at.toLocalDate().equals(next))return;
            target=at.format(DateTimeFormatter.ofPattern("HH:mm",Locale.ROOT));
        }
        pkg=clockPackage();
        if(pkg.isEmpty()){status("Совместимые штатные Часы не определены");return;}
        editor=new ClockEditor(enable,target);
        revision=rev;
        prefs().edit().putString("autoAttempt",rev).apply();
        deadline=SystemClock.elapsedRealtime()+60_000;
        try{startActivity(NativeClock.open().setPackage(pkg).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));}
        catch(RuntimeException e){fail("Android не открыл штатные Часы");return;}
        status("Открываю первый будильник");
        handler.postDelayed(tick,450);
    }
    private void fail(String reason){status(reason+" · проверь первый будильник");reset();}
    private void success(){
        String rev=revision;
        String detail=enable?"Первый будильник включён · "+target:"Первый будильник выключен";
        prefs().edit().putString("autoApplied",rev).putString("autoStatus",detail).commit();
        reset();
        Link.worker.execute(()->{try{Link.request(this,"applied",rev);}catch(Exception ignored){}});
    }
    public void onAccessibilityEvent(AccessibilityEvent event){
        // Poll only during our own short editing session. Ignore unrelated window events.
    }
    private void step(){
        if(revision.isEmpty())return;
        if(!prefs().getBoolean("autoClock",false) || !revision.equals(prefs().getString("revision","")) ||
            !fresh() || !NativeClock.actionable(NativeClock.current(this))){reset();return;}
        if(!unlocked()){
            if(!editor.started())prefs().edit().remove("autoAttempt").apply();
            fail("Экран заблокирован");return;
        }
        if(SystemClock.elapsedRealtime()>deadline){fail("Часы не подтвердили действие");return;}
        try{
            AccessibilityNodeInfo root=getRootInActiveWindow();
            if(root!=null && pkg.contentEquals(String.valueOf(root.getPackageName()))){
                List<AccessibilityNodeInfo> nodes=ClockUi.tree(root);
                editor.advance(nodes);
                if(editor.verified)success();
                else if(editor.failure!=null)fail(editor.failure);
            }else if(editor.started()){fail("Экран Часов закрыт");return;}
        }catch(RuntimeException e){fail("Не удалось распознать экран Часов");}
        if(!revision.isEmpty())handler.postDelayed(tick,550);
    }
}
