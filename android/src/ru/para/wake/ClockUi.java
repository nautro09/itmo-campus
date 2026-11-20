package ru.para.wake;

import android.graphics.Rect;
import android.view.accessibility.AccessibilityNodeInfo;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class ClockUi {
    private static final Pattern TIME = Pattern.compile("(?<![0-9])([01]?[0-9]|2[0-3]):([0-5][0-9])(?![0-9])");
    private static final Pattern NUMBER = Pattern.compile("(?iu)^([0-9]{1,2})(?:\\s*(?:ч|час(?:а|ов)?|мин(?:ут(?:а|ы)?)?)\\.?)?$");
    private static final Pattern SAVE_ID = Pattern.compile("(?:.*_)?(?:save|done|positive|ok|confirm)(?:_(?:button|btn|image|icon|view))?");
    private static final Pattern SAVE_LABEL = Pattern.compile("(?iu)(?:сохранить(?: изменения| будильник)?|готово|подтвердить|ок|ok|save|done)(?:,?\\s+кнопка)?");

    static List<AccessibilityNodeInfo> tree(AccessibilityNodeInfo root){
        List<AccessibilityNodeInfo> nodes=new ArrayList<>();
        nodes.add(root);
        for(int i=0;i<nodes.size();i++){
            AccessibilityNodeInfo parent=nodes.get(i);
            for(int j=0;j<parent.getChildCount();j++){
                AccessibilityNodeInfo child=parent.getChild(j);
                if(child!=null && child.isVisibleToUser())nodes.add(child);
                if(nodes.size()>800)throw new IllegalStateException("Слишком много элементов в Часах");
            }
        }
        return nodes;
    }
    static String text(AccessibilityNodeInfo n){return clean(n.getText());}
    static String desc(AccessibilityNodeInfo n){return clean(n.getContentDescription());}
    static String clean(CharSequence value){
        return value==null?"":value.toString().replace('\u00a0',' ').replace('\u202f',' ').replace("\u200e","").replace("\u200f","").trim();
    }
    static Rect bounds(AccessibilityNodeInfo n){Rect r=new Rect();n.getBoundsInScreen(r);return r;}
    static String id(AccessibilityNodeInfo n){
        String id=n.getViewIdResourceName();return id==null?"":id.substring(id.lastIndexOf('/')+1).toLowerCase(Locale.ROOT);
    }
    static AccessibilityNodeInfo label(List<AccessibilityNodeInfo> nodes,String name){
        for(AccessibilityNodeInfo n:nodes)if(text(n).equalsIgnoreCase(name)||desc(n).equalsIgnoreCase(name))return n;
        return null;
    }
    private static String rowTime(AccessibilityNodeInfo node){
        for(String value:new String[]{text(node),desc(node)}){
            Matcher clock=TIME.matcher(value);
            if(!clock.find())continue;
            String hour=clock.group(1);
            String time=(hour.length()==1?"0":"")+hour+":"+clock.group(2);
            if(clock.find())return "";
            return time;
        }
        return "";
    }
    static final class Row{
        final String time;
        final AccessibilityNodeInfo open,toggle;
        final boolean once;
        Row(String time,AccessibilityNodeInfo open,AccessibilityNodeInfo toggle,boolean once){
            this.time=time;this.open=open;this.toggle=toggle;this.once=once;
        }
    }
    static List<Row> rows(List<AccessibilityNodeInfo> nodes){
        AccessibilityNodeInfo header=label(nodes,"Другие будильники");
        if(header==null)return Collections.emptyList();
        int top=bounds(header).bottom;
        Map<AccessibilityNodeInfo,Row> found=new HashMap<>();
        for(AccessibilityNodeInfo n:nodes){
            String time=rowTime(n);
            if(time.isEmpty() || bounds(n).top<top)continue;
            Row row=identify(n,time,top);
            if(row==null)return Collections.emptyList();
            Row previous=found.get(row.toggle);
            if(previous==null || previous.open==null)found.put(row.toggle,row);
        }
        List<Row> rows=new ArrayList<>(found.values());
        rows.sort(Comparator.comparingInt(r->bounds(r.toggle).centerY()));
        return rows;
    }
    private static Row identify(AccessibilityNodeInfo timeNode,String time,int top){
        AccessibilityNodeInfo opener=null;
        Row candidate=null;
        for(AccessibilityNodeInfo parent=timeNode;parent!=null && bounds(parent).top>=top;parent=parent.getParent()){
            if(opener==null && parent.isClickable() && !parent.isCheckable())opener=parent;
            AccessibilityNodeInfo toggle=null;
            boolean once=false;
            for(AccessibilityNodeInfo n:tree(parent)){
                if(n.isCheckable()){
                    if(toggle!=null)return candidate;
                    toggle=n;
                }
                String other=rowTime(n);
                if(!other.isEmpty() && !other.equals(time))return candidate;
                String words=(text(n)+" "+desc(n)).toLowerCase(Locale.ROOT);
                if(words.contains("без повтора") || words.contains("один раз"))once=true;
            }
            if(toggle!=null){
                candidate=new Row(time,opener,toggle,once);
                // The one-shot subtitle may sit below the horizontal time/switch group.
                if(opener!=null && once)return candidate;
            }
        }
        return candidate;
    }
    static boolean click(AccessibilityNodeInfo n){
        return n!=null && n.isEnabled() && n.performAction(AccessibilityNodeInfo.ACTION_CLICK);
    }
    static boolean toggle(Row row){
        if(!row.toggle.isEnabled())return false;
        if(click(row.toggle))return true;
        // Some stock rows expose the Switch state on a child and the action on its wrapper.
        AccessibilityNodeInfo parent=row.toggle.getParent();
        for(int depth=0;parent!=null && depth<2;depth++,parent=parent.getParent()){
            if(parent.equals(row.open))return false;
            for(AccessibilityNodeInfo n:tree(parent)){
                if(n.equals(parent) || n.equals(row.toggle))continue;
                if(n.isClickable() || n.isCheckable() || !text(n).isEmpty() || !desc(n).isEmpty())return false;
            }
            if(!rowTime(parent).isEmpty())return false;
            if(parent.isClickable())return click(parent);
        }
        return false;
    }
    private static boolean saveLabel(AccessibilityNodeInfo n){
        return SAVE_ID.matcher(id(n)).matches() || SAVE_LABEL.matcher(text(n)).matches() || SAVE_LABEL.matcher(desc(n)).matches();
    }
    private static AccessibilityNodeInfo saveAction(AccessibilityNodeInfo label){
        AccessibilityNodeInfo action=label;
        for(int depth=0;action!=null && depth<=2;depth++,action=action.getParent()){
            if(!action.isClickable())continue;
            if(!action.isEnabled())return null;
            // A toolbar containing both the cross and the checkmark is never itself a Save button.
            for(AccessibilityNodeInfo n:tree(action)){
                if(n.equals(action) || saveLabel(n))continue;
                if(n.isClickable() || n.isCheckable() || !text(n).isEmpty() || !desc(n).isEmpty())return null;
            }
            if(!action.equals(label) && (!text(action).isEmpty() || !desc(action).isEmpty()) && !saveLabel(action))return null;
            return action;
        }
        return null;
    }
    static AccessibilityNodeInfo save(List<AccessibilityNodeInfo> nodes){
        AccessibilityNodeInfo found=null;
        for(AccessibilityNodeInfo n:nodes){
            if(!saveLabel(n))continue;
            AccessibilityNodeInfo action=saveAction(n);
            if(action==null)continue;
            if(found!=null && !found.equals(action))return null;
            found=action;
        }
        return found;
    }
    static List<AccessibilityNodeInfo> wheels(List<AccessibilityNodeInfo> nodes){
        List<AccessibilityNodeInfo> found=new ArrayList<>();
        for(AccessibilityNodeInfo n:nodes){
            String cl=String.valueOf(n.getClassName()).toLowerCase(Locale.ROOT);
            boolean step=n.getActionList().contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_FORWARD)
                || n.getActionList().contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_BACKWARD);
            if(cl.contains("numberpicker") || (step || n.getRangeInfo()!=null) &&
                (cl.contains("spinner") || cl.endsWith("picker") && !cl.contains("timepicker") ||
                 id(n).matches(".*(?:hour|minute).*")))found.add(n);
        }
        // Some vendor controls announce their numeric range, with no NumberPicker class or ID.
        if(found.size()<2){
            AccessibilityNodeInfo title=label(nodes,"Изменить будильник"),repeat=label(nodes,"Один раз");
            if(repeat==null)repeat=label(nodes,"Без повтора");
            if(title!=null && repeat!=null){
                int top=bounds(title).bottom,bottom=bounds(repeat).top;
                for(AccessibilityNodeInfo n:nodes){
                    AccessibilityNodeInfo.RangeInfo range=n.getRangeInfo();
                    if(range==null || range.getMin()!=0 || range.getMax()!=23 && range.getMax()!=59 || found.contains(n))continue;
                    Rect frame=bounds(n);
                    if(frame.top>=top && frame.bottom<=bottom && n.getActionList().contains(
                        AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS))found.add(n);
                }
            }
        }
        found.sort(Comparator.comparingInt(n->bounds(n).centerX()));
        if(found.size()!=2)return Collections.emptyList();
        Rect left=bounds(found.get(0)),right=bounds(found.get(1));
        if(left.right>right.left || Math.min(left.bottom,right.bottom)<=Math.max(left.top,right.top))return Collections.emptyList();
        for(int i=0;i<2;i++){
            AccessibilityNodeInfo.RangeInfo range=found.get(i).getRangeInfo();
            if(range!=null && range.getMin()==0 && range.getMax()==(i==0?59:23))return Collections.emptyList();
        }
        return found;
    }
    // Support reports contain roles and static resource IDs only, never labels or screen contents.
    static String describe(List<AccessibilityNodeInfo> nodes){
        int switches=0,scroll=0;
        AccessibilityNodeInfo title=label(nodes,"Изменить будильник");
        Set<String> widgets=new LinkedHashSet<>();
        for(AccessibilityNodeInfo n:nodes){
            if(n.isCheckable())switches++;
            if(n.isScrollable())scroll++;
            String type=String.valueOf(n.getClassName());
            boolean editorControl=title!=null && (saveLabel(n) || type.toLowerCase(Locale.ROOT).contains("picker") ||
                n.isClickable() && bounds(n).centerY()<=bounds(title).bottom);
            if(widgets.size()>=10 || !(n.isScrollable() || n.isCheckable() || n.getRangeInfo()!=null || editorControl))continue;
            String resource=id(n);
            widgets.add(type.substring(type.lastIndexOf('.')+1)+(resource.isEmpty()?"":" / "+resource));
        }
        return "Переключателей "+switches+" · прокручиваемых элементов "+scroll
            +(widgets.isEmpty()?"":"\n"+String.join(", ",widgets));
    }
    private static int number(AccessibilityNodeInfo node){
        for(String s:new String[]{text(node),desc(node)}){
            Matcher m=NUMBER.matcher(s);
            if(m.matches())return Integer.parseInt(m.group(1));
        }
        return -1;
    }
    static int value(AccessibilityNodeInfo wheel){
        AccessibilityNodeInfo.RangeInfo range=wheel.getRangeInfo();
        if(range!=null)return Math.round(range.getCurrent());
        int direct=number(wheel);
        if(direct>=0)return direct;
        int best=Integer.MAX_VALUE,value=-1,center=bounds(wheel).centerY();
        for(AccessibilityNodeInfo n:tree(wheel)){
            int v=number(n);
            if(v<0)continue;
            int distance=Math.abs(bounds(n).centerY()-center);
            if(distance<best){best=distance;value=v;}
            else if(distance==best && value!=v)value=-1;
        }
        return value;
    }
    static boolean move(AccessibilityNodeInfo wheel,int current,int target,int cycle,boolean stalled){
        if(!stalled && wheel.getRangeInfo()!=null && wheel.getActionList().contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS)){
            android.os.Bundle args=new android.os.Bundle();
            args.putFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE,target);
            if(wheel.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId(),args))return true;
        }
        boolean forward=(target-current+cycle)%cycle<=cycle/2;
        int action=forward?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD;
        if(!stalled && wheel.performAction(action))return true;
        // Some OEM wheels expose adjacent values as buttons but do not expose a scroll action.
        int next=(current+(forward?1:-1)+cycle)%cycle;
        for(AccessibilityNodeInfo child:tree(wheel)){
            if(number(child)==next && child.isClickable())return click(child);
        }
        return stalled && wheel.performAction(action);
    }
}
