package ru.para.wake;

import android.app.*;
import android.content.SharedPreferences;
import android.view.View;
import java.util.List;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.*;
import java.util.Locale;

/** Exercise the production editor using actual Android widgets and accessibility actions. */
final class ClockScenario {
    final Activity activity;
    boolean enabled;
    boolean secondEnabled=true;
    boolean secondVisible=true;
    int edits,toggles,wrongClicks;
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
        LinearLayout alarm=new LinearLayout(activity);alarm.setOrientation(LinearLayout.VERTICAL);
        alarm.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);page.addView(alarm);
        LinearLayout row=new LinearLayout(activity);row.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);alarm.addView(row);
        Button edit=new Button(activity);edit.setText(time);row.addView(edit);
        edit.setOnClickListener(v->edit());
        Switch toggle=new Switch(activity);toggle.setChecked(enabled);row.addView(toggle);
        toggle.setOnCheckedChangeListener((v,on)->{enabled=on;toggles++;});
        TextView repeat=new TextView(activity);repeat.setText("Будильник, Без повтора");alarm.addView(repeat);
        if(!secondVisible)return;
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
        edits++;page();label("Изменить будильник");
        // The toolbar and wheels can appear in different frames on the stock Clock.
        page.postDelayed(this::editorBody,1250);
    }
    void editorBody(){
        LinearLayout wheels=new LinearLayout(activity);page.addView(wheels);
        NumberPicker h=picker(wheels,23,Integer.parseInt(time.substring(0,2)));
        NumberPicker m=picker(wheels,59,Integer.parseInt(time.substring(3)));
        label("Один раз");label("Звук · Нет");
        LinearLayout toolbar=new LinearLayout(activity);page.addView(toolbar);
        Button cancel=new Button(activity);cancel.setContentDescription("Отмена");toolbar.addView(cancel);
        cancel.setOnClickListener(v->wrongClicks++);
        FrameLayout save=new FrameLayout(activity);toolbar.addView(save,new LinearLayout.LayoutParams(110,100));
        save.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
        ImageView icon=new ImageView(activity);icon.setContentDescription("Сохранить будильник");
        icon.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);save.addView(icon);
        save.setOnClickListener(v->{time=String.format(Locale.ROOT,"%02d:%02d",h.getValue(),m.getValue());list();});
    }
    private static List<AccessibilityNodeInfo> snapshot(UiAutomation access)throws Exception{
        Thread.sleep(480);
        AccessibilityNodeInfo root=access.getRootInActiveWindow();
        if(root==null)throw new AssertionError("Clock fixture has no window");
        return ClockUi.tree(root);
    }
    private static void legacyCheck(Instrumentation test,Activity a)throws Exception{
        SharedPreferences p=Link.prefs(a);
        String rev=p.getString("revision","");
        p.edit().putString("originalTime","09:50").putBoolean("savePending",false).putString("blockedRev",rev)
            .putString("autoStatus","Порядок будильников изменился во время проверки · подробности в настройках").commit();
        ClockAccess.discardLegacySelection(p,rev);
        PlanScenario.check(!p.contains("originalTime") && !p.contains("blockedRev"),"4.1 selection must not block the next launch");
        p.edit().putString("originalTime","09:50").putBoolean("savePending",true).putString("autoApplied",rev)
            .putString("awaitClock",rev).putString("blockedRev",rev).commit();
        ClockAccess.discardLegacySelection(p,rev);
        PlanScenario.check(p.contains("originalTime") && p.getBoolean("savePending",false),"automatic resume must keep an issued change");
        test.runOnMainSync(()->ClockAccess.restartCheck(a));
        PlanScenario.check(!p.contains("originalTime") && !p.contains("savePending") && !p.contains("blockedRev")
            && !p.contains("autoApplied") && !p.contains("awaitClock") && rev.equals(p.getString("revision",""))
            && p.contains("cipher"),"manual recheck must start afresh and keep the pairing and plan");
        Thread.sleep(300); // Let the real dashboard draw its new status before installing fixture widgets.
    }
    static void check(Instrumentation test, Activity a,String target)throws Exception{
        legacyCheck(test,a);
        ClockScenario fixture=new ClockScenario(a);
        UiAutomation access=test.getUiAutomation();
        test.runOnMainSync(()->{fixture.time=target;fixture.secondVisible=false;fixture.list();});
        ClockEditor sameTime=new ClockEditor(true,target,"09:50",false,(time,saving)->true,time->true);
        sameTime.advance(snapshot(access));
        PlanScenario.check(!sameTime.verified && sameTime.failure==null,"must read the switch again before confirming");
        sameTime.advance(snapshot(access));
        PlanScenario.check(sameTime.verified && fixture.enabled && fixture.edits==0 && fixture.toggles==1,
            "one manually disabled stock alarm already at 08:30 must be enabled in place");

        test.runOnMainSync(()->{fixture.time="09:50";fixture.enabled=false;fixture.secondVisible=true;fixture.list();});
        List<AccessibilityNodeInfo> list=snapshot(access);
        ClockEditor reordered=new ClockEditor(true,target,"12:15",true,(time,saving)->true,time->true);
        reordered.advance(list);
        PlanScenario.check(reordered.failure!=null,"a background retry must not edit another first alarm after a reorder");
        ClockEditor occupied=new ClockEditor(true,"12:15");
        occupied.advance(list);
        PlanScenario.check(occupied.failure!=null && fixture.edits==0 && fixture.toggles==1,
            "a second alarm already at the desired time must be left alone");
        String[] original={""};
        boolean[] saveSent={false};
        ClockEditor.Journal journal=(time,saving)->{original[0]=time;saveSent[0]=saving;return true;};
        for(boolean on:new boolean[]{true,false}){
            boolean resumed=false;
            ClockEditor editor=new ClockEditor(on,target,"07:00",false,journal,time->true);
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
            if(!editor.verified || fixture.enabled!=on || !target.equals(fixture.time) || !fixture.secondEnabled
                    || fixture.edits!=1 || fixture.wrongClicks!=0)
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
