package ru.para.wake;

import android.view.accessibility.AccessibilityNodeInfo;
import android.os.SystemClock;
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
    private final boolean saving;
    private Stage stage=Stage.LIST;
    private int previous=-1;
    private long waitingSince,movedAt;
    private boolean retried;
    int actions;
    String failure,deferTime;
    String trace="Ожидаю список будильников";
    boolean verified;

    ClockEditor(boolean enable,String target){this(enable,target,"",false,(time,saving)->true,time->true);}
    ClockEditor(boolean enable,String target,String original,boolean saving,Journal journal,java.util.function.Predicate<String> cancelTime){
        this.enable=enable;this.target=target;this.saving=saving;
        // Only an issued Save or switch action has an identity worth recovering after a restart.
        this.original=saving?original:"";this.journal=journal;this.cancelTime=cancelTime;
    }
    void advance(List<AccessibilityNodeInfo> nodes){
        if(failure!=null || verified)return;
        if(stage==Stage.EDIT)edit(nodes);else list(nodes);
    }
    boolean started(){return stage!=Stage.LIST;}
    private void awaiting(String detail){
        long now=SystemClock.elapsedRealtime();
        if(!detail.equals(trace)){trace=detail;waitingSince=now;}
        else if(now-waitingSince>=5_000)failure=detail;
    }
    private ClockUi.Row matching(List<ClockUi.Row> rows,String time){
        ClockUi.Row match=null;
        for(ClockUi.Row row:rows)if(row.time.equals(time)){
            if(match!=null){failure="Есть два будильника с одинаковым временем";return null;}
            match=row;
        }
        return match;
    }
    private void list(List<AccessibilityNodeInfo> nodes){
        if(ClockUi.editing(nodes)){
            awaiting("Ожидаю возврата из редактора к списку будильников");return;
        }
        List<ClockUi.Row> rows=ClockUi.rows(nodes);
        if(rows.isEmpty()){
            if(stage==Stage.VERIFY){awaiting("После сохранения ожидаю список будильников");return;}
            trace=ClockUi.label(nodes,"Другие будильники")==null?"Часы открыты · ищу раздел «Другие будильники»"
                :"Раздел найден · ищу строку со временем и переключателем";
            return;
        }
        ClockUi.Row row=rows.get(0);
        if(stage==Stage.VERIFY || stage==Stage.SWITCH){
            row=matching(rows,enable?target:original);
            if(row==null){awaiting("В списке пока нет строки с ожидаемым временем");return;}
        }else{
            ClockUi.Row destination=enable?matching(rows,target):saving?matching(rows,original):null;
            if(failure!=null)return;
            if(saving && destination!=null){
                row=destination;stage=Stage.VERIFY;
            }else{
                if(saving && !original.equals(row.time)){
                    trace="Сверяю первую строку с уже отправленным изменением";
                    failure="Порядок будильников изменился во время проверки";return;
                }
                original=row.time;
                if(matching(rows,original)==null)return;
                if(enable && !target.equals(original) && destination!=null){
                    failure="На рассчитанное время уже стоит другой будильник";return;
                }
                if(enable && !target.equals(original)){
                    if(!journal.write(original,false)){failure="План изменился до открытия первой строки";return;}
                    if(!ClockUi.click(row.open)){failure="Часы не дали открыть первую строку";return;}
                    actions++;
                    stage=Stage.EDIT;trace="Строка открыта · ожидаю редактор";return;
                }
            }
        }
        if(!row.once){awaiting("Часы не подтвердили режим «Без повтора» у выбранной строки");return;}
        if(row.toggle.isChecked()==enable){verified=true;return;}
        if(stage==Stage.SWITCH){awaiting("После нажатия положение переключателя не изменилось");return;}
        if(!enable && !cancelTime.test(row.time)){
            deferTime=row.time;return;
        }
        if(!journal.write(original,true)){failure="План изменился до переключения";return;}
        if(!ClockUi.toggle(row)){failure="Переключатель будильника недоступен";return;}
        actions++;
        stage=Stage.SWITCH;trace="Проверяю положение переключателя";
    }
    private void edit(List<AccessibilityNodeInfo> nodes){
        if(ClockUi.label(nodes,"Изменить будильник")==null){awaiting("Ожидаю экран «Изменить будильник»");return;}
        if(ClockUi.label(nodes,"Один раз")==null && ClockUi.label(nodes,"Без повтора")==null){
            awaiting("В редакторе не подтверждён однократный будильник");return;
        }
        List<AccessibilityNodeInfo> wheels=ClockUi.wheels(nodes);
        if(wheels.size()!=2){awaiting("Редактор открыт · Часы не показали два колеса времени");return;}
        int current=ClockUi.timeInEditor(nodes,wheels);
        if(current<0){awaiting("Часы не сообщили выбранное время");return;}
        int h=current/60,m=current%60;
        if(previous==-1 && !original.equals(String.format(Locale.ROOT,"%02d:%02d",h,m))){
            awaiting("В редакторе оказалось другое исходное время");return;
        }
        int hour=Integer.parseInt(target.substring(0,2)),minute=Integer.parseInt(target.substring(3));
        if(h==hour && m==minute){
            AccessibilityNodeInfo save=ClockUi.save(nodes);
            if(save==null){awaiting("Время выбрано · ищу кнопку сохранения в Часах");return;}
            if(!journal.write(original,true) || !ClockUi.click(save)){failure="Не удалось сохранить время";return;}
            actions++;
            stage=Stage.VERIFY;trace="Время выбрано · проверяю сохранение";return;
        }
        boolean hours=h!=hour;
        trace=String.format(Locale.ROOT,"В редакторе %02d:%02d · выставляю %s",h,m,target);
        boolean unchanged=previous==current;
        long now=SystemClock.elapsedRealtime();
        if(unchanged){
            if(now-movedAt>=4000){failure="Колесо не отреагировало на изменение";return;}
            if(retried || now-movedAt<1000)return;
            retried=true;
        }else{previous=current;movedAt=now;retried=false;}
        if(ClockUi.move(wheels.get(hours?0:1),hours?h:m,hours?hour:minute,hours?24:60,unchanged))actions++;
        else failure="Часы не разрешили изменить значение колеса";
    }
}
