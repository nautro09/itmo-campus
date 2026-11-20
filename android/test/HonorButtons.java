package ru.para.wake;

import android.view.View;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.*;
import java.util.Locale;

/** MagicOS 9 exposes adjacent values on buttons and a separate input beside the picker. */
final class HonorButtons {
    private static void resource(View view,String name){
        view.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
        view.setAccessibilityDelegate(new View.AccessibilityDelegate(){
            @Override public void onInitializeAccessibilityNodeInfo(View v,AccessibilityNodeInfo n){
                super.onInitializeAccessibilityNodeInfo(v,n);
                n.setViewIdResourceName("com.hihonor.deskclock:id/"+name);
            }
        });
    }
    static void mount(LinearLayout pair,int[] selected){
        resource(pair,"alarm_timePicker");
        for(int i=0;i<2;i++){
            final int field=i,cycle=i==0?24:60;
            String name=i==0?"hwtimepicker_hour":"hwtimepicker_minute";
            FrameLayout banner=new FrameLayout(pair.getContext());
            resource(banner,name+"_banner");pair.addView(banner,new LinearLayout.LayoutParams(170,210));
            LinearLayout wheel=new LinearLayout(pair.getContext());wheel.setOrientation(LinearLayout.VERTICAL);
            resource(wheel,name);banner.addView(wheel);
            Button above=new Button(pair.getContext()),below=new Button(pair.getContext());
            resource(above,"hwadvancednumberpicker_increment");resource(below,"hwadvancednumberpicker_decrement");
            TextView middle=new TextView(pair.getContext());resource(middle,"hwadvancednumberpicker_textview");
            for(View view:new View[]{above,middle,below})wheel.addView(view,new LinearLayout.LayoutParams(170,70));
            EditText overlay=new EditText(pair.getContext());resource(overlay,name+"_input");
            overlay.setFocusable(false);FrameLayout.LayoutParams lp=new FrameLayout.LayoutParams(100,50);
            lp.gravity=android.view.Gravity.CENTER;banner.addView(overlay,lp);
            Runnable update=()->{
                above.setText(String.format(Locale.ROOT,"%02d",(selected[field]+cycle-1)%cycle));
                below.setText(String.format(Locale.ROOT,"%02d",(selected[field]+1)%cycle));
            };
            above.setOnClickListener(v->{selected[field]=(selected[field]+cycle-1)%cycle;update.run();});
            below.setOnClickListener(v->{selected[field]=(selected[field]+1)%cycle;update.run();});
            update.run();
        }
    }
}
