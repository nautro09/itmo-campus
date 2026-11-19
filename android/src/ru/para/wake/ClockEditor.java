package ru.para.wake;

import android.view.accessibility.AccessibilityNodeInfo;
import java.util.List;
import java.util.Locale;

/** Edits a single existing row, then verifies the saved time and switch in the list. */
final class ClockEditor {
    private final boolean enable;
    private final String target;
    private String original="";
    private int stage,previous=-1,stalled;
    String failure;
    boolean verified;
    ClockEditor(boolean enable,String target){this.enable=enable;this.target=target;}
    void advance(List<AccessibilityNodeInfo> nodes){
        if(failure!=null || verified)return;
        if(stage==1)edit(nodes);else list(nodes);
    }
    boolean started(){return stage!=0;}
    private void fail(String reason){failure=reason;}
    private void success(){verified=true;}
    private void list(List<AccessibilityNodeInfo> nodes){
        List<ClockUi.Row> rows=ClockUi.rows(nodes);
        if(rows.isEmpty())return;
        ClockUi.Row row=rows.get(0);
        if(stage==0){
            original=row.time;
            if(enable && !target.equals(original)){
                for(ClockUi.Row r:rows)if(r.time.equals(target)){fail("Другой будильник уже имеет это время");return;}
                if(!ClockUi.click(row.open)){fail("Не найдена кнопка первого будильника");return;}
                stage=1;return;
            }
        }else{
            String expected=enable?target:original;
            ClockUi.Row match=null;
            for(ClockUi.Row r:rows)if(r.time.equals(expected)){
                if(match!=null){fail("Несколько будильников с таким временем");return;}
                match=r;
            }
            if(match==null)return;
            row=match;
        }
        if(row.toggle.isChecked()==enable){success();return;}
        if(stage==3)return;
        if(!ClockUi.click(row.toggle)){fail("Переключатель недоступен");return;}
        stage=3;
    }
    private void edit(List<AccessibilityNodeInfo> nodes){
        if(ClockUi.label(nodes,"Изменить будильник")==null)return;
        if(ClockUi.label(nodes,"Один раз")==null){fail("Редактор не подтвердил однократный будильник");return;}
        List<AccessibilityNodeInfo> wheels=ClockUi.wheels(nodes);
        if(wheels.size()!=2){fail("Часы не предоставили два колеса времени");return;}
        int h=ClockUi.value(wheels.get(0)),m=ClockUi.value(wheels.get(1));
        if(h<0 || h>23 || m<0 || m>59){fail("Не удалось прочитать выбранное время");return;}
        int current=h*60+m;
        if(previous==-1 && !original.equals(String.format(Locale.ROOT,"%02d:%02d",h,m))){
            fail("Открылась другая строка будильника");return;
        }
        if(previous==current){if(++stalled>=4)fail("Колесо времени не изменилось");return;}
        previous=current;stalled=0;
        int hour=Integer.parseInt(target.substring(0,2)),minute=Integer.parseInt(target.substring(3));
        if(h==hour && m==minute){
            if(!ClockUi.click(ClockUi.save(nodes))){fail("Не найдена галочка сохранения");return;}
            stage=2;return;
        }
        boolean hours=h!=hour;
        int delta=hours?hour-h:minute-m;
        int cycle=hours?24:60;
        boolean forward=(delta+cycle)%cycle<=cycle/2;
        if(!wheels.get(hours?0:1).performAction(forward?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD))
            fail("Часы не разрешили прокрутку колеса");
    }
}
