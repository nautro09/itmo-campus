package ru.para.wake;

import android.view.accessibility.AccessibilityNodeInfo;
import java.util.List;
import java.util.Locale;

/** Change one existing one-shot alarm. Verify the saved row after any sorting by time. */
final class ClockEditor {
    enum Stage { LIST, EDIT, VERIFY, SWITCH }
    interface Journal { boolean write(String original,boolean saving); }
    private final boolean enable;
    private final String target;
    private final Journal journal;
    private final java.util.function.Predicate<String> cancelTime;
    private String original;
    private boolean saving;
    private Stage stage=Stage.LIST;
    private int previous=-1,stalled;
    String failure,deferTime;
    String trace="Ожидаю список будильников";
    boolean verified;

    ClockEditor(boolean enable,String target){this(enable,target,"",false,(time,saving)->true,time->true);}
    ClockEditor(boolean enable,String target,String original,boolean saving,Journal journal,java.util.function.Predicate<String> cancelTime){
        this.enable=enable;this.target=target;this.original=original;this.saving=saving;this.journal=journal;this.cancelTime=cancelTime;
    }
    void advance(List<AccessibilityNodeInfo> nodes){
        if(failure!=null || verified)return;
        if(stage==Stage.EDIT)edit(nodes);else list(nodes);
    }
    boolean started(){return stage!=Stage.LIST;}
    private ClockUi.Row matching(List<ClockUi.Row> rows,String time){
        ClockUi.Row match=null;
        for(ClockUi.Row row:rows)if(row.time.equals(time)){
            if(match!=null){failure="Есть два будильника с одинаковым временем";return null;}
            match=row;
        }
        return match;
    }
    private void list(List<AccessibilityNodeInfo> nodes){
        List<ClockUi.Row> rows=ClockUi.rows(nodes);
        if(rows.isEmpty()){
            trace=ClockUi.label(nodes,"Другие будильники")==null?"Часы открыты · ищу раздел «Другие будильники»"
                :"Раздел найден · ищу строку со временем и переключателем";
            return;
        }
        ClockUi.Row row=rows.get(0);
        if(stage==Stage.VERIFY || stage==Stage.SWITCH){
            row=matching(rows,enable?target:original);
            if(row==null){trace="Ожидаю сохранённую строку в списке";return;}
        }else{
            ClockUi.Row destination=enable?matching(rows,target):saving?matching(rows,original):null;
            if(failure!=null)return;
            if(saving && destination!=null){
                row=destination;stage=Stage.VERIFY;
            }else{
                if(!original.isEmpty() && !original.equals(row.time)){
                    failure="Порядок будильников изменился во время проверки";return;
                }
                original=row.time;
                if(matching(rows,original)==null)return;
                if(enable && !target.equals(original) && destination!=null){
                    failure="На рассчитанное время уже стоит другой будильник";return;
                }
                if(!journal.write(original,false)){failure="Не удалось сохранить состояние проверки";return;}
                if(enable && !target.equals(original)){
                    if(!ClockUi.click(row.open)){failure="Часы не дали открыть первую строку";return;}
                    stage=Stage.EDIT;trace="Строка открыта · ожидаю редактор";return;
                }
                if(!row.once){failure="Часы не подтвердили режим «Без повтора» у первой строки";return;}
            }
        }
        if(row.toggle.isChecked()==enable){verified=true;return;}
        if(stage==Stage.SWITCH)return;
        if(!enable && !cancelTime.test(row.time)){
            deferTime=row.time;return;
        }
        if(!journal.write(original,true)){failure="План изменился до переключения";return;}
        if(!ClockUi.click(row.toggle)){failure="Переключатель будильника недоступен";return;}
        stage=Stage.SWITCH;trace="Проверяю положение переключателя";
    }
    private void edit(List<AccessibilityNodeInfo> nodes){
        if(ClockUi.label(nodes,"Изменить будильник")==null)return;
        if(ClockUi.label(nodes,"Один раз")==null && ClockUi.label(nodes,"Без повтора")==null){
            failure="В редакторе не подтверждён однократный будильник";return;
        }
        List<AccessibilityNodeInfo> wheels=ClockUi.wheels(nodes);
        if(wheels.size()!=2){failure="Редактор открыт · Часы не показали два колеса времени";return;}
        int h=ClockUi.value(wheels.get(0)),m=ClockUi.value(wheels.get(1));
        if(h<0 || h>23 || m<0 || m>59){failure="Часы не сообщили выбранное время";return;}
        int current=h*60+m;
        if(previous==-1 && !original.equals(String.format(Locale.ROOT,"%02d:%02d",h,m))){
            failure="В редакторе оказалось другое исходное время";return;
        }
        if(previous==current){if(++stalled>=6)failure="Колесо не отреагировало на изменение";return;}
        previous=current;stalled=0;
        int hour=Integer.parseInt(target.substring(0,2)),minute=Integer.parseInt(target.substring(3));
        if(h==hour && m==minute){
            AccessibilityNodeInfo save=ClockUi.save(nodes);
            if(save==null){failure="Часы не показали кнопку сохранения";return;}
            saving=true;
            if(!journal.write(original,true) || !ClockUi.click(save)){failure="Не удалось сохранить время";return;}
            stage=Stage.VERIFY;trace="Время выбрано · проверяю сохранение";return;
        }
        boolean hours=h!=hour;
        trace=hours?"Меняю часы":"Меняю минуты";
        if(!ClockUi.move(wheels.get(hours?0:1),hours?h:m,hours?hour:minute,hours?24:60))
            failure="Часы не разрешили изменить значение колеса";
    }
}
