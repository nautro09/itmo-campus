package ru.para.wake;

import android.graphics.Rect;
import android.view.accessibility.AccessibilityNodeInfo;
import java.util.*;
import java.util.regex.Pattern;

/** Controls exposed by the Russian MagicOS Clock. Never tap guessed screen coordinates. */
final class ClockUi {
    static final Pattern TIME=Pattern.compile("(?:[01]?\\d|2[0-3]):[0-5]\\d");
    static List<AccessibilityNodeInfo> tree(AccessibilityNodeInfo root){
        ArrayList<AccessibilityNodeInfo> result=new ArrayList<>();
        result.add(root);
        for(int i=0;i<result.size();i++){
            AccessibilityNodeInfo node=result.get(i);
            for(int j=0;j<node.getChildCount();j++){
                AccessibilityNodeInfo child=node.getChild(j);
                if(child!=null && child.isVisibleToUser())result.add(child);
                if(result.size()>600)throw new IllegalStateException("Слишком много элементов в Часах");
            }
        }
        return result;
    }
    static String text(AccessibilityNodeInfo n){return n.getText()==null?"":n.getText().toString().trim();}
    static String desc(AccessibilityNodeInfo n){return n.getContentDescription()==null?"":n.getContentDescription().toString().trim();}
    static Rect bounds(AccessibilityNodeInfo n){Rect r=new Rect();n.getBoundsInScreen(r);return r;}
    static String id(AccessibilityNodeInfo n){
        String id=n.getViewIdResourceName();return id==null?"":id.substring(id.lastIndexOf('/')+1).toLowerCase(Locale.ROOT);
    }
    static AccessibilityNodeInfo label(List<AccessibilityNodeInfo> nodes,String label){
        for(AccessibilityNodeInfo n:nodes)if(text(n).equalsIgnoreCase(label)||desc(n).equalsIgnoreCase(label))return n;
        return null;
    }
    static final class Row{
        final String time;
        final AccessibilityNodeInfo open,toggle;
        Row(String time,AccessibilityNodeInfo open,AccessibilityNodeInfo toggle){this.time=time;this.open=open;this.toggle=toggle;}
    }
    static String normalized(String value){return value.length()==4?"0"+value:value;}
    static List<Row> rows(List<AccessibilityNodeInfo> nodes){
        List<Row> rows=new ArrayList<>();
        AccessibilityNodeInfo header=label(nodes,"Другие будильники");
        if(header==null)return rows;
        int top=bounds(header).bottom;
        for(AccessibilityNodeInfo n:nodes){
            String time=text(n);
            if(!TIME.matcher(time).matches() || bounds(n).centerY()<top)continue;
            AccessibilityNodeInfo ancestor=n;
            for(int depth=0;ancestor!=null && depth<6;depth++,ancestor=ancestor.getParent()){
                if(bounds(ancestor).top<top)break;
                List<AccessibilityNodeInfo> children=tree(ancestor);
                AccessibilityNodeInfo toggle=null,open=null;
                int times=0,switches=0;
                for(AccessibilityNodeInfo c:children){
                    if(TIME.matcher(text(c)).matches())times++;
                    if(c.isCheckable()){switches++;toggle=c;}
                }
                if(times>1 || switches>1)break;
                if(switches!=1)continue;
                for(AccessibilityNodeInfo a=n;a!=null;a=a.getParent()){
                    if(a.isClickable() && !a.isCheckable()){open=a;break;}
                    if(a.equals(ancestor))break;
                }
                if(open==null && ancestor.isClickable())open=ancestor;
                rows.add(new Row(normalized(time),open,toggle));break;
            }
            // If the top time has no recognisable control, do not silently skip to the next alarm.
            boolean found=false;
            for(Row r:rows)if(r.time.equals(normalized(time)))found=true;
            if(!found)return Collections.emptyList();
        }
        rows.sort(Comparator.comparingInt(r->bounds(r.toggle).centerY()));
        return rows;
    }
    static boolean click(AccessibilityNodeInfo n){
        return n!=null && n.isEnabled() && n.performAction(AccessibilityNodeInfo.ACTION_CLICK);
    }
    static AccessibilityNodeInfo save(List<AccessibilityNodeInfo> nodes){
        for(AccessibilityNodeInfo n:nodes){
            String key=id(n);
            if(n.isClickable() && (key.matches("(?:.*_)?(?:save|done|positive|ok)(?:_button)?") ||
                desc(n).matches("(?iu)сохранить|готово|ок|ok") || text(n).matches("(?iu)сохранить|готово")))return n;
        }
        return null;
    }
    static List<AccessibilityNodeInfo> wheels(List<AccessibilityNodeInfo> nodes){
        ArrayList<AccessibilityNodeInfo> found=new ArrayList<>();
        for(AccessibilityNodeInfo n:nodes){
            String cl=String.valueOf(n.getClassName()).toLowerCase(Locale.ROOT);
            if(cl.contains("numberpicker") || cl.contains("spinner") && n.isScrollable()
                || n.isScrollable() && id(n).matches(".*(hour|minute).*"))found.add(n);
        }
        found.sort(Comparator.comparingInt(n->bounds(n).centerX()));
        if(found.size()!=2 || bounds(found.get(0)).right>bounds(found.get(1)).left)return Collections.emptyList();
        return found;
    }
    static int value(AccessibilityNodeInfo wheel){
        AccessibilityNodeInfo.RangeInfo range=wheel.getRangeInfo();
        if(range!=null)return Math.round(range.getCurrent());
        for(String s:new String[]{text(wheel),desc(wheel)})if(s.matches("[0-9]{1,2}"))return Integer.parseInt(s);
        int best=Integer.MAX_VALUE,value=-1,center=bounds(wheel).centerY();
        for(AccessibilityNodeInfo n:tree(wheel)){
            String s=text(n);
            if(!s.matches("[0-9]{1,2}"))continue;
            int distance=Math.abs(bounds(n).centerY()-center);
            if(distance<best){best=distance;value=Integer.parseInt(s);}
        }
        return value;
    }
}
