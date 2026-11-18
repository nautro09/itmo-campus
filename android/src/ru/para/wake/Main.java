package ru.para.wake;

import android.app.*;
import android.app.job.JobScheduler;
import android.os.*;
import android.content.*;
import android.graphics.*;
import android.net.Uri;
import android.provider.Settings;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;

public class Main extends Activity {
    private LinearLayout panel;
    private EditText host, code;
    private TextView status;
    private Button pair, sync;
    private boolean busy;
    int dp(int n){return Math.round(getResources().getDisplayMetrics().density*n);}
    TextView label(String value,int size){
        TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(Color.rgb(29,42,37));
        t.setPadding(0,dp(8),0,dp(6));panel.addView(t);return t;
    }
    Button button(String text,Runnable action){
        Button b=new Button(this);b.setText(text);b.setAllCaps(false);b.setOnClickListener(v->action.run());panel.addView(b);return b;
    }
    EditText input(String hint,int type){
        EditText e=new EditText(this);e.setHint(hint);e.setInputType(type);e.setSingleLine();e.setSaveEnabled(false);panel.addView(e);return e;
    }
    public void onCreate(Bundle saved){
        super.onCreate(saved);
        ScrollView scroll=new ScrollView(this);panel=new LinearLayout(this);panel.setOrientation(LinearLayout.VERTICAL);
        panel.setBackgroundColor(Color.rgb(243,248,242));panel.setPadding(dp(22),dp(36),dp(22),dp(40));
        scroll.addView(panel);setContentView(scroll);
        panel.setOnApplyWindowInsetsListener((v,insets)->{
            panel.setPadding(dp(22),dp(20)+insets.getSystemWindowInsetTop(),dp(22),dp(28)+insets.getSystemWindowInsetBottom());
            return insets;
        });
        label("Учебный будильник",30).setTypeface(Typeface.DEFAULT,Typeface.BOLD);
        status=label("",17);
        sync=button("Проверить расписание",()->run(false));
        button("Проверить звук · 10 секунд",()->{
            if(!notifications()){permission();return;}
            startForegroundService(new Intent(this,Ring.class).setAction("TEST"));
        });
        button("Выключить звонок",()->stopService(new Intent(this,Ring.class)));
        button("Разрешения будильника",this::permission);
        label("Привязка к «Паре»",21);
        label("В личном чате открой Настройки → Будильник → Привязать Honor. Адрес и код вводятся один раз.",15);
        host=input("https://…",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        host.setText(Link.prefs(this).getString("site",""));
        code=input("Одноразовый код",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        code.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        pair=button("Привязать и проверить",()->run(true));
        button("Отключить этот телефон",()->new AlertDialog.Builder(this).setMessage("Удалить локальную привязку и будильники «Пары»?")
            .setNegativeButton("Назад",null).setPositiveButton("Отключить",(d,w)->Link.worker.execute(()->{
                getSystemService(JobScheduler.class).cancel(7);Alarms.clear(this);Link.prefs(this).edit().clear().commit();
                stopService(new Intent(this,Ring.class));runOnUiThread(this::refresh);
            })).show());
        refresh();
    }
    static void result(Context c,String message){
        String time=LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"));
        Link.prefs(c).edit().putString("status",time+" · "+message).apply();
    }
    boolean notifications(){return getSystemService(NotificationManager.class).areNotificationsEnabled();}
    void permission(){
        if(Build.VERSION.SDK_INT>=33 && !notifications()){requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS},1);return;}
        if(Build.VERSION.SDK_INT>=31 && !Alarms.exact(this)){
            try{startActivity(new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,Uri.parse("package:"+getPackageName())));}
            catch(ActivityNotFoundException e){startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:"+getPackageName())));}
        } else if(!notifications()){
            startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE,getPackageName()));
        } else Toast.makeText(this,"Разрешения включены",Toast.LENGTH_SHORT).show();
    }
    void run(boolean pairing){
        if(busy)return;
        if(!notifications() || !Alarms.exact(this)){permission();return;}
        final String site=host.getText().toString(), ticket=code.getText().toString().trim();
        busy=true;refresh();status.setText("Проверяю связь…");
        Link.worker.execute(()->{
            try{
                if(pairing)Link.pair(this,site,ticket);
                Link.sync(this);result(this,"Расписание проверено");
            } catch(Exception e){result(this,"Проверка не завершена. Проверь адрес, код, сеть и разрешения.");}
            runOnUiThread(()->{if(isDestroyed())return;busy=false;code.setText("");refresh();});
        });
    }
    protected void onResume(){super.onResume();if(status!=null)refresh();}
    void refresh(){
        boolean linked=Link.prefs(this).contains("cipher");
        StringBuilder s=new StringBuilder(linked?"Телефон привязан":"Телефон не привязан");
        for(String day:new TreeSet<>(Alarms.prefs(this).getAll().keySet())){
            long at=Alarms.prefs(this).getLong(day,0);
            if(at>System.currentTimeMillis())s.append("\n").append(Instant.ofEpochMilli(at).atZone(Alarms.MOSCOW).format(DateTimeFormatter.ofPattern("dd.MM · HH:mm 'МСК'")));
        }
        s.append("\n").append(Link.prefs(this).getString("status",""));
        status.setText(s);sync.setEnabled(linked && !busy);pair.setEnabled(!busy);
    }
}
