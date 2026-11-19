package ru.para.wake;

import android.app.*;
import android.content.Context;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.*;
import java.util.Locale;

/** Exercise the production editor using actual Android widgets and accessibility actions. */
final class ClockScenario {
    final Activity activity;
    boolean enabled;
    String time="09:50";
    LinearLayout page;
    ClockScenario(Activity activity){this.activity=activity;}
    void page(){
        page=new LinearLayout(activity);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(20,100,20,20);
        activity.setContentView(page);
    }
    TextView label(String text){
        TextView v=new TextView(activity);v.setText(text);page.addView(v);return v;
    }
    void list(){
        page();
        label("Сон | Подъем");label("Другие будильники");
        LinearLayout row=new LinearLayout(activity);page.addView(row);
        Button edit=new Button(activity);edit.setText(time);row.addView(edit);
        edit.setOnClickListener(v->edit());
        Switch toggle=new Switch(activity);toggle.setChecked(enabled);row.addView(toggle);
        toggle.setOnCheckedChangeListener((v,on)->enabled=on);
    }
    NumberPicker picker(LinearLayout row,int max,int value){
        NumberPicker n=new NumberPicker(activity);n.setMinValue(0);n.setMaxValue(max);n.setValue(value);
        row.addView(n,new LinearLayout.LayoutParams(150,260));return n;
    }
    void edit(){
        page();label("Изменить будильник");
        LinearLayout wheels=new LinearLayout(activity);page.addView(wheels);
        NumberPicker h=picker(wheels,23,9),m=picker(wheels,59,50);
        label("Один раз");label("Звук · Нет");
        Button save=new Button(activity);save.setText("Готово");page.addView(save);
        save.setOnClickListener(v->{time=String.format(Locale.ROOT,"%02d:%02d",h.getValue(),m.getValue());list();});
    }
    static void check(Instrumentation test, Activity a)throws Exception{
        ClockScenario fixture=new ClockScenario(a);
        test.runOnMainSync(fixture::list);
        UiAutomation access=test.getUiAutomation();
        for(boolean on:new boolean[]{true,false}){
            ClockEditor editor=new ClockEditor(on,"08:48");
            for(int attempt=0;attempt<32 && !editor.verified;attempt++){
                Thread.sleep(600);
                AccessibilityNodeInfo root=access.getRootInActiveWindow();
                if(root!=null)editor.advance(ClockUi.tree(root));
                if(editor.failure!=null)throw new AssertionError(editor.failure);
            }
            if(!editor.verified || fixture.enabled!=on || !"08:48".equals(fixture.time))
                throw new AssertionError("Clock editor verification: "+fixture.time+" "+fixture.enabled);
        }
    }
}
