package ru.para.wake;

import android.app.*;
import android.app.job.JobScheduler;
import android.content.*;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;

public class Main extends Activity {
    LinearLayout page,card; TextView message; boolean busy; boolean backgroundReady=true;
    int dp(int n){return Math.round(getResources().getDisplayMetrics().density*n);}
    void box(int color){
        card=new LinearLayout(this);card.setOrientation(1); card.setPadding(dp(18),dp(12),dp(18),dp(15));
        GradientDrawable bg=new GradientDrawable();bg.setColor(color);bg.setCornerRadius(dp(20));card.setBackground(bg);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(12);page.addView(card,lp);
    }
    TextView text(String value,int size,int color){
        TextView v=new TextView(this);v.setText(value);v.setTextSize(size);v.setTextColor(color);v.setPadding(0,dp(4),0,dp(6));card.addView(v);return v;
    }
    Button button(String title,Runnable action){
        Button b=new Button(this);b.setText(title);b.setAllCaps(false);b.setEnabled(!busy);card.addView(b);b.setOnClickListener(v->action.run());return b;
    }
    EditText field(String hint,int type){
        EditText f=new EditText(this);f.setSingleLine();f.setInputType(type);f.setSaveEnabled(false);f.setHint(hint);card.addView(f);return f;
    }
    static void result(Context c,String msg){Link.prefs(c).edit().putString("status",msg).apply();}
    interface Work{void run() throws Exception;}
    void perform(Work w){
        if(busy)return;busy=true;draw();
        Link.worker.execute(()->{
            try{w.run();result(this,"Данные сохранены");}
            catch(Exception e){result(this,"Связь не подтверждена. Проверь сеть. Если адрес в Telegram изменился, повтори привязку.");}
            runOnUiThread(()->{busy=false;if(!isDestroyed())draw();});
        });
    }
    public void onCreate(Bundle b){super.onCreate(b);draw();}
    public void onResume(){super.onResume();if(!busy && Link.prefs(this).contains("cipher")){
        backgroundReady=SyncJob.enable(this);
        perform(()->Link.sync(this));
    }}
    void draw(){
        int ink=0xff173b32;ScrollView scroll=new ScrollView(this);page=new LinearLayout(this);page.setOrientation(1);
        page.setBackgroundColor(0xfff1f4ec);page.setPadding(dp(16),dp(40),dp(16),dp(32));scroll.addView(page);setContentView(scroll);
        page.setOnApplyWindowInsetsListener((v,i)->{v.setPadding(dp(16),dp(16)+i.getSystemWindowInsetTop(),dp(16),dp(16)+i.getSystemWindowInsetBottom());return i;});
        SharedPreferences p=Link.prefs(this);boolean linked=p.contains("cipher");JSONObject row=NativeClock.current(this);
        String rev=p.getString("revision","");
        box(ink);text("Пара  /  Подъём",17,0xffd4e6cc);
        text("set".equals(row.optString("action"))?NativeClock.time(row):"Расписание",42,0xffddf69a).setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        text(linked?row.optString("day")+"  ·  "+(p.getBoolean("autoClock",false) && "set".equals(row.optString("action"))?"Подъём по расписанию":NativeClock.summary(row)):"Подключи расписание из личного чата",16,0xffffffff);
        box(0xffffffff);
        if(linked){
            if(!backgroundReady)text("Android отложил фоновую синхронизацию. Обновить расписание можно вручную.",14,ink);
            try{
                JSONObject settings=new JSONObject(p.getString("settings","{}"));
                if(settings.has("wake_on")){
                    text("Настройки из Telegram",21,ink);
                    text(settings.optBoolean("wake_on")?"Автобудильник включён":"Автобудильник выключен",15,ink);
                    String rules=settings.optString("wake_rules").replace("=", " → ").replace(", ", "\n");
                    text(rules.isEmpty()?"Индивидуальных правил нет":rules,16,ink);
                    text("Сборы · "+settings.optInt("wake_prep")+" мин   Онлайн · "+settings.optInt("wake_online")+" мин",14,ink);
                }
                long last=p.getLong("lastReceived",0);
                if(last>0)text("Получено "+java.text.DateFormat.getDateTimeInstance().format(new java.util.Date(last)),14,ink);
            }catch(org.json.JSONException ignored){}

            boolean automatic=p.getBoolean("autoClock",false);
            if(!automatic || !ClockAccess.ready()){
                button("Включить автоизменение будильника",()->new AlertDialog.Builder(this)
                    .setTitle("Управление штатными Часами")
                    .setMessage("Разреши службе «Пара · управление Часами» читать элементы Часов и нажимать кнопки. После 18:00 МСК она сможет изменить первый будильник в разделе «Другие будильники» при разблокированном экране. Звук и повтор выбираешь ты.")
                    .setNegativeButton("Отмена",null).setPositiveButton("Открыть настройки",(d,w)->{
                        p.edit().putBoolean("autoClock",true).remove("autoAttempt").apply();
                        if(ClockAccess.ready()){ClockAccess.refresh();draw();}
                        else startActivity(new Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS));
                    }).show());
            }
            if(automatic){
                text(ClockAccess.ready()?p.getString("autoStatus","Ожидаю план подъёма"):"Включи службу «Пара · управление Часами» в специальных возможностях",15,ink);
                if(ClockAccess.ready())button("Повторить проверку будильника",()->perform(()->{
                    p.edit().remove("autoAttempt").remove("autoApplied").remove("autoReported").apply();Link.sync(this);
                }));
                button("Выключить автоизменение",()->{
                    p.edit().putBoolean("autoClock",false).remove("autoAttempt").remove("autoApplied").remove("autoStatus").remove("autoReported").apply();
                    ClockAccess.stopLocal();draw();
                });
            }
            button("Открыть штатные Часы",()->{
                try{startActivity(NativeClock.open());
                    if(NativeClock.actionable(row)){p.edit().putString("opened",rev).commit();
                        Link.worker.execute(()->{try{Link.request(this,"opened",rev);}catch(Exception ignored){} });}
                }catch(ActivityNotFoundException | SecurityException e){result(this,"Открой приложение «Часы» вручную.");draw();}
            });
            if(!automatic)text("Выбери первый будильник сверху. Проверь дату следующего звонка. В карточке будильника выбери время, мелодию, вибрацию и повтор.",15,ink);
            if(!automatic && NativeClock.actionable(row) && rev.equals(p.getString("opened","")) && !rev.equals(p.getString("confirmed","")))
                button("Я сохранил изменение в Часах",()->perform(()->{Link.request(this,"confirmed",rev);p.edit().putString("confirmed",rev).apply();}));
            if(!rev.isEmpty() && rev.equals(p.getString("confirmed","")))text("Ты подтвердил сохранение в Часах",16,ink);
            button("Обновить расписание",()->perform(()->Link.sync(this)));
            if(Build.VERSION.SDK_INT>=33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=0)
                button("Разрешить уведомления о смене подъёма",()->requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS},1));
            button("Отключить телефон",()->new AlertDialog.Builder(this).setMessage("Удалить привязку на этом телефоне?").setNegativeButton("Назад",null)
                .setPositiveButton("Отключить",(d,w)->perform(()->{getSystemService(JobScheduler.class).cancel(7);getSystemService(NotificationManager.class).cancel(9);p.edit().clear().commit();})).show());
        }else{
            text("Привязка телефона",22,ink);
            text("Отсканируй QR-код обычной камерой телефона. QR находится в «Паре» → Профиль → Будильник и дорога. Можно также ввести адрес и код вручную.",15,ink);
            EditText host=field("HTTPS-адрес",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
            EditText code=field("Одноразовый код",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
            code.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
            button("Привязать телефон",()->{String url=host.getText().toString(),ticket=code.getText().toString().trim();perform(()->{Link.pair(this,url,ticket);Link.sync(this);});});
        }
        box(0xffffffff);
        button("Сведения о телефоне и Часах",()->{
            android.content.pm.PackageManager pm=getPackageManager();
            StringBuilder report=new StringBuilder(Build.MANUFACTURER+" "+Build.MODEL+" · Android "+Build.VERSION.RELEASE);
            for(android.content.pm.ResolveInfo handler:pm.queryIntentActivities(NativeClock.open(),0)){
                String pkg=handler.activityInfo.packageName;
                try{
                    android.content.pm.PackageInfo info=pm.getPackageInfo(pkg,0);
                    report.append("\n").append(handler.loadLabel(pm)).append(" · ").append(info.versionName).append(" · ").append(pkg);
                }catch(android.content.pm.PackageManager.NameNotFoundException ignored){}
            }
            new AlertDialog.Builder(this).setTitle("Сведения для проверки совместимости").setMessage(report.toString())
                .setNegativeButton("Закрыть",null).setPositiveButton("Скопировать",(dialog,which)->
                    getSystemService(android.content.ClipboardManager.class).setPrimaryClip(ClipData.newPlainText("Часы",report.toString()))).show();
        });
        message=text(busy?"Проверяю…":p.getString("status",""),14,ink);
    }
}
