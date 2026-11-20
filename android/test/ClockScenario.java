package ru.para.wake;

import android.app.*;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.SharedPreferences;
import android.os.Bundle;
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
    boolean honor,honorButtons;
    String time="09:50";
    LinearLayout page;
    Dialog host,dialog;
    ClockScenario(Activity activity){this.activity=activity;}
    void page(){
        page=new LinearLayout(activity);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(20,100,20,20);
        if(host==null)host=new Dialog(activity,android.R.style.Theme_Material_Light_NoActionBar);
        host.setContentView(page);
        if(!host.isShowing())host.show();
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
    void rangeEditor(){
        page();label("Изменить будильник");
        LinearLayout row=new LinearLayout(activity);page.addView(row);
        for(int max:new int[]{23,59}){
            SeekBar range=new SeekBar(activity);range.setMax(max);range.setProgress(max==23?9:50);
            row.addView(range,new LinearLayout.LayoutParams(180,100));
        }
        label("Один раз");
    }
    void edit(){
        if(honor){honorEditor();return;}
        edits++;page();label("Изменить будильник");
        // The toolbar and wheels can appear in different frames on the stock Clock.
        page.postDelayed(this::editorBody,1250);
    }
    private void honorEditor(){
        edits++;
        dialog=new Dialog(activity);
        LinearLayout sheet=new LinearLayout(activity);sheet.setOrientation(LinearLayout.VERTICAL);
        LinearLayout toolbar=new LinearLayout(activity);sheet.addView(toolbar);
        TextView header=new TextView(activity);header.setText("Изменить будильник");toolbar.addView(header);
        Button save=new Button(activity);save.setContentDescription("Готово");toolbar.addView(save);
        LinearLayout pair=new LinearLayout(activity);sheet.addView(pair);
        int[] selected={Integer.parseInt(time.substring(0,2)),Integer.parseInt(time.substring(3))};
        if(honorButtons)HonorButtons.mount(pair,selected);
        else for(int i=0;i<2;i++){
            final int index=i,cycle=i==0?24:60;
            FrameLayout wrapper=new FrameLayout(activity);wrapper.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
            pair.addView(wrapper,new LinearLayout.LayoutParams(130,140));
            wrapper.setAccessibilityDelegate(new View.AccessibilityDelegate(){
                public void onInitializeAccessibilityNodeInfo(View host,AccessibilityNodeInfo info){
                    super.onInitializeAccessibilityNodeInfo(host,info);info.setClassName("vendor.NumberPicker");
                }
            });
            View field=new View(activity);field.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);wrapper.addView(field);
            field.setAccessibilityDelegate(new View.AccessibilityDelegate(){
                public void onInitializeAccessibilityNodeInfo(View host,AccessibilityNodeInfo info){
                    super.onInitializeAccessibilityNodeInfo(host,info);
                    info.setStateDescription((index==0?"Часы: ":"Минуты: ")+selected[index]);
                    info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_UP);
                    info.addAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_DOWN);
                }
                public boolean performAccessibilityAction(View host,int action,Bundle args){
                    if(action==AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_DOWN.getId() ||
                        action==AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_UP.getId()){
                        int delta=action==AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_DOWN.getId()?1:-1;
                        selected[index]=(selected[index]+delta+cycle)%cycle;
                        host.sendAccessibilityEvent(android.view.accessibility.AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED);
                        return true;
                    }
                    return super.performAccessibilityAction(host,action,args);
                }
            });
        }
        TextView once=new TextView(activity);once.setText("Один раз");sheet.addView(once);
        dialog.setContentView(sheet);
        save.setOnClickListener(v->{
            time=String.format(Locale.ROOT,"%02d:%02d",selected[0],selected[1]);dialog.dismiss();list();
        });
        dialog.show();
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
    }
    static void check(Instrumentation test, Activity a,String target)throws Exception{
        legacyCheck(test,a);
        ClockScenario fixture=new ClockScenario(a);
        try{checkWidgets(test,fixture,target);}
        finally{test.runOnMainSync(()->{
            if(fixture.dialog!=null)fixture.dialog.dismiss();
            if(fixture.host!=null)fixture.host.dismiss();
        });}
    }
    private static void checkWidgets(Instrumentation test,ClockScenario fixture,String target)throws Exception{
        Activity a=fixture.activity;
        UiAutomation access=test.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        test.runOnMainSync(fixture::rangeEditor);
        List<AccessibilityNodeInfo> rangeNodes=snapshot(access);
        List<AccessibilityNodeInfo> ranges=ClockUi.wheels(rangeNodes);
        for(int i=0;i<10 && ranges.size()!=2;i++){
            rangeNodes=snapshot(access);ranges=ClockUi.wheels(rangeNodes);
        }
        PlanScenario.check(ranges.size()==2 && ClockUi.value(ranges.get(0))==9 && ClockUi.value(ranges.get(1))==50,
            "expected fixture time 09:50: "+ClockUi.describe(rangeNodes));
        PlanScenario.check(ClockUi.move(ranges.get(1),50,30,60,false),"minute field rejected 50 -> 30");
        PlanScenario.check(ClockUi.value(ClockUi.wheels(snapshot(access)).get(1))==30,"minute range must report the change");
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
        // Reproduce the disabled 07:21 row, then the 08:31 row from the handset recordings.
        AccessibilityServiceInfo info=access.getServiceInfo();
        info.flags|=AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS|AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
        access.setServiceInfo(info);
        fixture.honor=true;
        String[][] scenarios={{"07:21","08:30"},{"08:31","08:30"},{"07:21","08:30"},{"23:59","00:00"},{"08:31","08:30"}};
        for(int scenario=0;scenario<scenarios.length;scenario++){
            fixture.honorButtons=scenario>=2;
            String start=scenarios[scenario][0], expected=scenarios[scenario][1];
            test.runOnMainSync(()->{fixture.time=start;fixture.enabled=false;fixture.list();});
            ClockEditor editor=new ClockEditor(true,expected);
            Thread.sleep(350);
            AccessibilityNodeInfo before=access.getRootInActiveWindow();
            editor.advance(ClockUi.tree(before));
            boolean dialogSeen=false;
            for(int i=0;i<65 && !editor.verified && editor.failure==null;i++){
                Thread.sleep(200);
                AccessibilityNodeInfo front=ClockAccess.foreground(a.getPackageName(),i==0?before:access.getRootInActiveWindow(),access.getWindows());
                if(front==null)continue;
                List<AccessibilityNodeInfo> nodes=ClockUi.tree(front);
                if(ClockUi.editing(nodes) && front.getWindowId()!=before.getWindowId())dialogSeen=true;
                if(fixture.honorButtons && ClockUi.editing(nodes)){
                    List<AccessibilityNodeInfo> columns=ClockUi.wheels(nodes);
                    PlanScenario.check(columns.size()==2 && ClockUi.id(columns.get(0)).equals("hwtimepicker_hour")
                        && ClockUi.id(columns.get(1)).equals("hwtimepicker_minute"),"select actual MagicOS wheels, not overlay inputs");
                }
                editor.advance(nodes);
            }
            PlanScenario.check(dialogSeen && editor.verified && fixture.enabled && fixture.time.equals(expected) &&
                fixture.secondEnabled && fixture.wrongClicks==0,"focused Clock dialog "+start+" -> "+expected+": "+editor.trace+" / "+editor.failure);
        }
    }
}
