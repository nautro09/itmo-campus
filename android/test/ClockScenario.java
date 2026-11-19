package ru.para.wake;

import android.app.*;
import java.util.List;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.*;
import java.util.Locale;

/** Exercise the production editor using actual Android widgets and accessibility actions. */
final class ClockScenario {
    final Activity activity;
    boolean enabled;
    boolean secondEnabled=true;
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
        LinearLayout row=new LinearLayout(activity);row.setImportantForAccessibility(android.view.View.IMPORTANT_FOR_ACCESSIBILITY_YES);page.addView(row);
        Button edit=new Button(activity);edit.setContentDescription(time+", Будильник, Без повтора");edit.setText(time);row.addView(edit);
        edit.setOnClickListener(v->edit());
        Switch toggle=new Switch(activity);toggle.setChecked(enabled);row.addView(toggle);
        toggle.setOnCheckedChangeListener((v,on)->enabled=on);
        LinearLayout second=new LinearLayout(activity);second.setImportantForAccessibility(android.view.View.IMPORTANT_FOR_ACCESSIBILITY_YES);page.addView(second);
        Button later=new Button(activity);later.setText("12:15");second.addView(later);
        Switch other=new Switch(activity);other.setChecked(secondEnabled);second.addView(other);
        other.setOnCheckedChangeListener((v,on)->secondEnabled=on);
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
    static void check(Instrumentation test, Activity a,String target)throws Exception{
        ClockScenario fixture=new ClockScenario(a);
        test.runOnMainSync(fixture::list);
        UiAutomation access=test.getUiAutomation();
        String[] original={""};
        boolean[] saveSent={false};
        ClockEditor.Journal journal=(time,saving)->{original[0]=time;saveSent[0]=saving;return true;};
        for(boolean on:new boolean[]{true,false}){
            boolean resumed=false;
            ClockEditor editor=new ClockEditor(on,target,"",false,journal,time->true);
            String observed="no window";
            for(int attempt=0;attempt<75 && !editor.verified;attempt++){
                Thread.sleep(480);
                AccessibilityNodeInfo root=access.getRootInActiveWindow();
                if(root!=null){
                    List<AccessibilityNodeInfo> nodes=ClockUi.tree(root);
                    StringBuilder description=new StringBuilder();
                    for(AccessibilityNodeInfo n:nodes)
                        description.append(n.getClassName()).append('[').append(ClockUi.text(n)).append("] ");
                    observed=description.toString();
                    editor.advance(nodes);
                    if(on && saveSent[0] && !resumed){
                        // Recreate the editor just after sending Save, as after a process interruption.
                        editor=new ClockEditor(true,target,original[0],true,journal,time->true);
                        resumed=true;
                    }
                }
                if(editor.failure!=null)throw new AssertionError(editor.failure+" | "+observed);
            }
            if(!editor.verified || fixture.enabled!=on || !target.equals(fixture.time) || !fixture.secondEnabled)
                throw new AssertionError("Clock editor verification: "+fixture.time+" "+fixture.enabled+" | "+observed);
            if(on){
                if(!resumed)throw new AssertionError("save journal was never exercised");
                String rev=Link.prefs(a).getString("revision","");
                Link.request(a,"applied",rev);
                PlanScenario.step("verified");
            }
        }
    }
}
