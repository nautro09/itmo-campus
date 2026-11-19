package ru.para.wake;

import android.app.*;
import android.app.job.JobScheduler;
import android.content.*;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.*;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import org.json.JSONObject;
import static ru.para.wake.ClockLayout.*;

public class Main extends Activity {
    private static final Locale RU=Locale.forLanguageTag("ru");
    private static final DateTimeFormatter DATE=DateTimeFormatter.ofPattern("d MMMM",RU);
    private static final DateTimeFormatter STAMP=DateTimeFormatter.ofPattern("d MMM, HH:mm",RU);
    private enum Page { HOME, SETTINGS, PAIR }
    private Page screen=Page.HOME;
    private ClockLayout ui;
    private SharedPreferences prefs;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private boolean busy,visible,backgroundReady=true;
    private String operationIssue="";
    private final Runnable redraw=()->{if(visible && screen!=Page.PAIR)draw(true);};
    private final SharedPreferences.OnSharedPreferenceChangeListener listener=(p,k)->{
        if(!visible || screen==Page.PAIR)return;
        handler.removeCallbacks(redraw);handler.postDelayed(redraw,90);
    };
    @Override public void onCreate(Bundle state){
        super.onCreate(state);prefs=Link.prefs(this);
        if(state!=null)screen=Page.valueOf(state.getString("page","HOME"));
        getWindow().setStatusBarColor(android.graphics.Color.TRANSPARENT);
        getWindow().setNavigationBarColor(android.graphics.Color.TRANSPARENT);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE |
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION |
            View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        draw(false);
    }
    @Override public void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);state.putString("page",screen.name());}
    @Override public void onStart(){super.onStart();visible=true;prefs.registerOnSharedPreferenceChangeListener(listener);}
    @Override public void onResume(){
        super.onResume();
        if(screen!=Page.PAIR)draw(true);
        if(prefs.contains("cipher") && !busy && screen!=Page.PAIR){
            backgroundReady=SyncJob.enable(this);
            Link.worker.execute(()->{try{Link.syncIfDue(this);}catch(Exception ignored){}});
        }
    }
    @Override public void onStop(){
        visible=false;handler.removeCallbacks(redraw);prefs.unregisterOnSharedPreferenceChangeListener(listener);super.onStop();
    }
    @Override public void onBackPressed(){if(screen!=Page.HOME)show(Page.HOME);else super.onBackPressed();}
    private void show(Page next){operationIssue="";screen=next;draw(false);}
    private void draw(boolean keepPosition){
        int y=keepPosition && ui!=null?ui.scroll.getScrollY():0;
        ui=new ClockLayout(this);
        boolean linked=prefs.contains("cipher");
        if(screen==Page.PAIR){pairForm();return;}
        if(screen==Page.SETTINGS){settings(linked);}
        else{
            ui.header("Пара","Настройки",()->show(Page.SETTINGS));
            if(linked){dashboard();}else{welcome();}
        }
        if(!operationIssue.isEmpty())ui.line(ui.page,operationIssue,15,MUTED,false,12);
        if(y>0){ScrollView scroll=ui.scroll;scroll.post(()->scroll.scrollTo(0,y));}
    }
    private void welcome(){
        LinearLayout hero=ui.card(NIGHT);
        ui.line(hero,"Подъём к паре",32,WHITE,true,0);
        ui.line(hero,"Время из твоего расписания в первом будильнике штатных Часов.",16,LILAC,false,10);
        LinearLayout box=ui.card(WHITE);
        ui.line(box,"Подключи телефон",20,INK,true,0);
        ui.line(box,"В Telegram открой Пара → Профиль → Будильник и дорога. Нажми «Привязать будильник телефона к расписанию» и открой ссылку на этом телефоне или отсканируй QR камерой.",15,MUTED,false,8);
        ui.action(box,"Ввести код вручную",false,()->show(Page.PAIR));
    }
    private String stamp(long ms){return ms>0?Instant.ofEpochMilli(ms).atZone(NativeClock.MOSCOW).format(STAMP)+" МСК":"пока нет";}
    private static String day(JSONObject row){
        try{
            LocalDate d=LocalDate.parse(row.getString("day"));
            LocalDate today=LocalDate.now(NativeClock.MOSCOW);
            String prefix=d.equals(today)?"Сегодня":d.equals(today.plusDays(1))?"Завтра":"Дата";
            return prefix+", "+d.format(DATE);
        }catch(Exception e){return "Расписание";}
    }
    private static String basis(JSONObject row){
        switch(row.optString("basis")){
            case "rule":return "Твоё правило";
            case "travel":return "Сборы и дорога";
            case "online":return "Время до онлайн-пары";
            default:return "";
        }
    }
    private void dashboard(){
        JSONObject row=NativeClock.current(this);
        String rev=prefs.getString("revision","");
        boolean applied=!rev.isEmpty() && rev.equals(prefs.getString("autoApplied",""));
        boolean automatic=prefs.getBoolean("autoClock",false);
        boolean set="set".equals(row.optString("action"));
        boolean showTime=set && row.has("basis") && NativeClock.actionable(row) &&
            (NativeClock.usable(prefs,row,Instant.now()) || applied);
        LinearLayout hero=ui.card(NIGHT);
        ui.line(hero,day(row),16,LILAC,false,0);
        if(showTime){
            LinearLayout clock=ui.row();
            TextView hhmm=ui.label(NativeClock.time(row),54,LIME,true);hhmm.setFontFeatureSettings("tnum");
            hhmm.setLetterSpacing(-0.045f);ui.flex(clock,hhmm);
            if(getResources().getConfiguration().fontScale<1.3f)ui.dial(clock,LocalTime.parse(NativeClock.time(row)));
            hero.addView(clock);ui.line(hero,"Подъём по Москве",16,WHITE,true,0);
            ui.line(hero,"Пара в "+row.optString("start")+"  ·  "+basis(row),15,LILAC,false,12);
        }else{
            String title=set?"Нужен свежий план":("free".equals(row.optString("action")) || "cancel".equals(row.optString("action")))?"Свободный день":"Расписание";
            ui.line(hero,title,28,WHITE,true,8);
            ui.line(hero,set?"Обнови связь, чтобы получить актуальное время подъёма.":NativeClock.summary(row),15,LILAC,false,10);
        }
        LinearLayout clock=ui.card(WHITE);
        ui.line(clock,"Штатный будильник",20,INK,true,0);
        String state;
        if(applied)state=prefs.getString("autoStatus","Проверен в Часах");
        else if(!automatic)state="Автоизменение выключено на телефоне";
        else if(!ClockAccess.ready())state="Служба управления Часами выключена";
        else if(!NativeClock.actionable(row))state="Для этого плана изменение не требуется";
        else if(!NativeClock.usable(prefs,row,Instant.now()))state="Жду актуальный план для Часов";
        else state=prefs.getString("autoStatus","План получен · ожидаю проверки первой строки");
        ui.line(clock,state,16,applied?GREEN:INK,true,8);
        if(applied)ui.line(clock,"Проверено "+stamp(prefs.getLong("appliedAt",0)),14,MUTED,false,6);
        if(!prefs.getString("ackIssue","").isEmpty())ui.line(clock,prefs.getString("ackIssue",""),14,MUTED,false,6);
        if(!applied && !automatic && !rev.isEmpty() && rev.equals(prefs.getString("confirmed","")))
            ui.line(clock,"Время отмечено тобой вручную",14,MUTED,false,6);
        if(!automatic || !ClockAccess.ready())ui.action(clock,"Разрешить автоизменение",true,this::enableClock);
        else if(!applied && rev.equals(prefs.getString("blockedRev","!")))
            ui.action(clock,"Повторить проверку",true,this::retry);
        ui.action(clock,"Открыть штатные Часы",false,this::openClock);
        if(!automatic && NativeClock.actionable(row) && rev.equals(prefs.getString("opened","")) && !rev.equals(prefs.getString("confirmed","")))
            ui.action(clock,"Я проверил время в Часах",false,()->perform(()->{
                Link.request(this,"confirmed",rev);prefs.edit().putString("confirmed",rev).apply();
            }));
        connection(false);
        rules(row,showTime);
    }
    private void rules(JSONObject row,boolean current){
        JSONObject settings;
        try{settings=new JSONObject(prefs.getString("settings","{}"));}catch(Exception e){return;}
        if(!settings.has("wake_rules"))return;
        LinearLayout box=ui.card(WHITE);
        ui.line(box,"Время по парам",20,INK,true,0);
        String entries=settings.optString("wake_rules");
        if(!entries.isEmpty()){
            ui.rule(box,"Начало пары","Подъём",false,true);
            for(String rule:entries.split(",")){
                String[] parts=rule.trim().split("=");
                if(parts.length==2)ui.rule(box,parts[0],parts[1],current && "rule".equals(row.optString("basis")) && parts[0].equals(row.optString("start")),false);
            }
        }
        ui.line(box,"Без личного правила · сборы "+settings.optInt("wake_prep")+" мин и дорога, онлайн за "+settings.optInt("wake_online")+" мин.",14,MUTED,false,8);
        if(!prefs.getString("bot","").isEmpty())ui.action(box,"Настроить в Telegram",false,()->openBot(false));
    }
    private void connection(boolean details){
        LinearLayout box=ui.card(WHITE);
        ui.line(box,"Связь с ботом",20,INK,true,0);
        String issue=prefs.getString("syncIssue","");
        ui.line(box,"Последний план · "+stamp(prefs.getLong("lastReceived",0)),15,MUTED,false,8);
        if(!issue.isEmpty())ui.line(box,issue,15,INK,false,8);
        if(!backgroundReady)ui.line(box,"Android отложил фоновую проверку.",14,MUTED,false,6);
        if(details){
            ui.line(box,"Последний запрос · "+stamp(prefs.getLong("lastAttempt",0)),14,MUTED,false,6);
            ui.line(box,"Адрес · "+Uri.parse(prefs.getString("site","")).getHost(),14,MUTED,false,6);
        }
        Button sync=ui.action(box,busy?"Синхронизация…":"Синхронизировать",true,()->perform(()->Link.sync(this)));
        sync.setEnabled(!busy);sync.setAlpha(busy?0.65f:1f);
        if(details || !issue.isEmpty())ui.action(box,"Обновить привязку",false,()->openBot(true));
    }
    private void settings(boolean linked){
        ui.header("Настройки","Назад",()->show(Page.HOME));
        if(linked){
            connection(true);
            LinearLayout box=ui.card(WHITE);
            ui.line(box,"Управление Часами",20,INK,true,0);
            boolean auto=prefs.getBoolean("autoClock",false);
            ui.line(box,auto&&ClockAccess.ready()?"Служба включена":"Служба выключена",15,MUTED,false,8);
            if(auto && ClockAccess.ready()){
                ui.action(box,"Повторить проверку",false,this::retry);
                ui.action(box,"Выключить автоизменение",false,()->{
                    prefs.edit().putBoolean("autoClock",false).remove("autoStatus").apply();ClockAccess.stopLocal();draw(true);
                });
            }else ui.action(box,"Разрешить автоизменение",false,this::enableClock);
            if(Build.VERSION.SDK_INT>=33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=0)
                ui.action(box,"Разрешить уведомления",false,()->requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS},1));
        }
        LinearLayout device=ui.card(WHITE);
        ui.line(device,"Телефон и диагностика",20,INK,true,0);
        ui.line(device,Build.MANUFACTURER+" "+Build.MODEL+" · Android "+Build.VERSION.RELEASE,15,MUTED,false,8);
        ui.action(device,"Сведения о проверке",false,this::diagnostics);
        ui.action(device,"Ввести код привязки",false,()->show(Page.PAIR));
        if(linked)ui.action(device,"Отключить телефон",false,this::disconnect);
    }
    private void pairForm(){
        ui.header("Привязка","Назад",()->show(Page.HOME));
        LinearLayout box=ui.card(WHITE);
        ui.line(box,"Код из Telegram",22,INK,true,0);
        ui.line(box,"Скопируй адрес и одноразовый код из своего бота. Код действует пять минут.",15,MUTED,false,8);
        EditText site=input(box,"HTTPS-адрес",InputType.TYPE_TEXT_VARIATION_URI);
        EditText code=input(box,"Одноразовый код",InputType.TYPE_TEXT_VARIATION_PASSWORD);
        TextView notice=ui.line(box,operationIssue,14,MUTED,false,6);
        Button connect=ui.action(box,"Привязать телефон",true,()->{
            if(busy)return;
            String url=site.getText().toString().trim(),ticket=code.getText().toString().trim();
            busy=true;notice.setText("Соединяюсь…");
            Link.worker.execute(()->{
                try{
                    Link.pair(this,url,ticket);
                    runOnUiThread(()->{busy=false;if(!isDestroyed()){show(Page.HOME);perform(()->Link.sync(this));}});
                }catch(Exception e){runOnUiThread(()->{busy=false;notice.setText("Проверь адрес и свежий код из Telegram. "+Link.explain(this,e));});}
            });
        });connect.setEnabled(!busy);
    }
    private EditText input(LinearLayout box,String hint,int variation){
        EditText e=new EditText(this);e.setHint(hint);e.setSingleLine(true);e.setSaveEnabled(false);
        e.setInputType(InputType.TYPE_CLASS_TEXT|variation);e.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);box.addView(e);return e;
    }
    private void openBot(boolean pairing){
        String name=prefs.getString("bot","");
        if(name.matches("[A-Za-z0-9_]{5,32}")){
            Intent open=new Intent(Intent.ACTION_VIEW,Uri.parse("https://t.me/"+name+(pairing?"?start=clock":"")));
            try{startActivity(open);return;}catch(ActivityNotFoundException ignored){}
        }
        new AlertDialog.Builder(this).setTitle("Открой свой бот в Telegram")
            .setMessage("Пара → Профиль → Будильник и дорога. Выбери «Привязать будильник телефона к расписанию» и открой новую ссылку на этом телефоне.")
            .setPositiveButton("Готово",null).setNeutralButton("Ввести код",(d,w)->show(Page.PAIR)).show();
    }
    private void enableClock(){
        new AlertDialog.Builder(this).setTitle("Разрешить управление Часами?")
            .setMessage("Пара сможет открывать штатные Часы при разблокированном экране, менять время и включать первый обычный будильник. Выбери в нём «Один раз» и свою мелодию.")
            .setNegativeButton("Отмена",null).setPositiveButton("Включить",(d,w)->{
                prefs.edit().putBoolean("autoClock",true).remove("blockedRev").remove("retryAfter").apply();
                if(ClockAccess.ready())perform(()->Link.sync(this));
                else try{startActivity(new Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS));}
                catch(ActivityNotFoundException e){operationIssue="Открой настройки Android → Специальные возможности → Пара.";draw(true);}
            }).show();
    }
    private void retry(){
        prefs.edit().remove("blockedRev").remove("retryAfter").remove("attempts").apply();
        perform(()->Link.sync(this));
    }
    private void openClock(){
        try{
            Intent open=ClockAccess.systemClock(this);
            startActivity(open!=null?open:NativeClock.open());
            String rev=prefs.getString("revision","");
            if(!prefs.getBoolean("autoClock",false) && NativeClock.actionable(NativeClock.current(this))){
                prefs.edit().putString("opened",rev).apply();
                Link.worker.execute(()->{try{Link.request(this,"opened",rev);}catch(Exception ignored){}});
            }
        }catch(ActivityNotFoundException|SecurityException e){operationIssue="Открой штатные Часы с домашнего экрана.";draw(true);}
    }
    private void diagnostics(){
        StringBuilder text=new StringBuilder(Build.MANUFACTURER+" "+Build.MODEL+" · Android "+Build.VERSION.RELEASE);
        Intent clock=ClockAccess.systemClock(this);
        if(clock!=null){
            try{text.append("\nЧасы ").append(getPackageManager().getPackageInfo(clock.getPackage(),0).versionName).append(" · ").append(clock.getPackage());}
            catch(android.content.pm.PackageManager.NameNotFoundException ignored){}
        }else text.append("\nШтатные Часы не определены");
        text.append("\nПлан получен · ").append(stamp(prefs.getLong("lastReceived",0)));
        for(String key:new String[]{"syncIssue","autoStatus","clockTrace"}){
            String value=prefs.getString(key,"");if(!value.isEmpty())text.append("\n").append(value);
        }
        new AlertDialog.Builder(this).setTitle("Сведения о проверке").setMessage(text.toString()).setNegativeButton("Закрыть",null)
            .setPositiveButton("Скопировать",(d,w)->getSystemService(android.content.ClipboardManager.class)
                .setPrimaryClip(ClipData.newPlainText("Проверка будильника",text.toString()))).show();
    }
    private void disconnect(){
        new AlertDialog.Builder(this).setMessage("Удалить ключ привязки с этого телефона и выключить автоизменение?")
            .setNegativeButton("Назад",null).setPositiveButton("Отключить",(d,w)->perform(()->{
                getSystemService(JobScheduler.class).cancel(7);getSystemService(NotificationManager.class).cancel(9);
                prefs.edit().clear().commit();ClockAccess.stopLocal();runOnUiThread(()->show(Page.HOME));
            })).show();
    }
    interface Work{void run() throws Exception;}
    private void perform(Work w){
        if(busy)return;
        busy=true;operationIssue="";draw(true);
        Link.worker.execute(()->{
            try{w.run();}
            catch(Exception e){runOnUiThread(()->operationIssue=prefs.getString("syncIssue","").isEmpty()?Link.explain(this,e):"");}
            finally{runOnUiThread(()->{busy=false;if(visible && !isDestroyed() && screen!=Page.PAIR)draw(true);});}
        });
    }
}
