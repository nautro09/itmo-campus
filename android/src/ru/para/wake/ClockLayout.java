package ru.para.wake;

import android.app.Activity;
import android.content.res.ColorStateList;
import android.graphics.*;
import android.graphics.drawable.*;
import android.view.*;
import android.widget.*;
import java.time.LocalTime;

/** Native controls, scalable labels and the palette of the Para launcher icon. */
final class ClockLayout {
    static final int PAPER=0xfff6f5f8, INK=0xff292538, MUTED=0xff615d6c, LINE=0xffe2dfe7,
        NIGHT=0xff302840, LILAC=0xffe4d4fa, LIME=0xffd8ec9f, WHITE=0xffffffff, GREEN=0xff48612c;
    final Activity host;
    final LinearLayout page;
    final ScrollView scroll;
    ClockLayout(Activity host){
        this.host=host;
        scroll=new ScrollView(host);
        scroll.setBackgroundColor(PAPER);
        scroll.setClipToPadding(false);
        scroll.setFillViewport(true);
        page=column();
        scroll.addView(page);
        host.setContentView(scroll);
        page.setPadding(dp(18),dp(12),dp(18),dp(20));
        scroll.setOnApplyWindowInsetsListener((v,i)->{
            page.setPadding(dp(18)+i.getSystemWindowInsetLeft(),dp(12)+i.getSystemWindowInsetTop(),
                dp(18)+i.getSystemWindowInsetRight(),dp(24)+i.getSystemWindowInsetBottom());
            return i;
        });
    }
    int dp(int n){return Math.round(host.getResources().getDisplayMetrics().density*n);}
    LinearLayout column(){LinearLayout v=new LinearLayout(host);v.setOrientation(LinearLayout.VERTICAL);return v;}
    LinearLayout row(){LinearLayout v=new LinearLayout(host);v.setGravity(Gravity.CENTER_VERTICAL);return v;}
    void flex(LinearLayout parent,View v){parent.addView(v,new LinearLayout.LayoutParams(0,-2,1));}
    GradientDrawable shape(int fill,int radius,int border){
        GradientDrawable d=new GradientDrawable();d.setColor(fill);d.setCornerRadius(dp(radius));
        if(border!=0)d.setStroke(dp(1),border);
        return d;
    }
    TextView label(String value,int sp,int color,boolean bold){
        TextView v=new TextView(host);
        v.setText(value);v.setTextSize(sp);v.setTextColor(color);v.setIncludeFontPadding(false);
        v.setTypeface(Typeface.create(bold?"sans-serif-medium":"sans-serif",Typeface.NORMAL));
        v.setBreakStrategy(android.text.Layout.BREAK_STRATEGY_SIMPLE);
        return v;
    }
    TextView line(LinearLayout parent,String value,int sp,int color,boolean bold,int before){
        TextView v=label(value,sp,color,bold);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(before);
        parent.addView(v,lp);return v;
    }
    LinearLayout card(int fill){
        LinearLayout v=column();
        v.setPadding(dp(18),dp(17),dp(18),dp(17));
        v.setBackground(shape(fill,22,fill==WHITE?LINE:0));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(12);page.addView(v,lp);
        return v;
    }
    Button button(String text,boolean primary,Runnable click){
        Button b=new Button(host);
        b.setText(text);b.setTextSize(15);b.setAllCaps(false);b.setGravity(Gravity.CENTER);
        b.setTextColor(primary?WHITE:INK);b.setLetterSpacing(0);b.setTypeface(Typeface.create("sans-serif-medium",0));
        b.setMinWidth(0);b.setMinimumWidth(0);b.setMinHeight(dp(48));b.setMinimumHeight(dp(48));
        b.setPadding(dp(12),dp(8),dp(12),dp(8));b.setStateListAnimator(null);
        b.setBackgroundTintList(null);
        b.setBackground(new RippleDrawable(ColorStateList.valueOf(0x223f344e),
            shape(primary?NIGHT:0xfff1edf6,14,0),null));
        b.setOnClickListener(v->click.run());
        return b;
    }
    Button action(LinearLayout parent,String text,boolean primary,Runnable click){
        Button b=button(text,primary,click);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(10);parent.addView(b,lp);return b;
    }
    void header(String title,String action,Runnable click){
        LinearLayout bar=row();
        ImageView logo=new ImageView(host);
        logo.setImageResource(host.getApplicationInfo().icon);logo.setBackground(shape(NIGHT,11,0));
        logo.setClipToOutline(true);bar.addView(logo,dp(35),dp(35));
        TextView name=label(title,21,INK,true);name.setPadding(dp(10),0,dp(4),0);flex(bar,name);
        bar.addView(button(action,false,click));page.addView(bar);
    }
    void dial(LinearLayout parent,LocalTime time){
        // The hands show the calculated time, including the hour-hand offset for the minutes.
        View dial=new View(host){
            final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
            protected void onDraw(Canvas canvas){
                float size=Math.min(getWidth(),getHeight());
                canvas.save();canvas.translate(getWidth()/2f,getHeight()/2f);canvas.scale(size/100f,size/100f);
                paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2);paint.setColor(0xff766982);
                canvas.drawCircle(0,0,46,paint);paint.setStrokeCap(Paint.Cap.ROUND);
                for(int i=0;i<12;i++){
                    canvas.drawLine(0,-39,0,i%3==0?-33:-37,paint);canvas.rotate(30);
                }
                hand(canvas,30*(time.getHour()%12)+time.getMinute()/2f,21,5,LILAC);
                hand(canvas,6*time.getMinute(),32,3,LIME);
                paint.setStyle(Paint.Style.FILL);canvas.drawCircle(0,0,3,paint);canvas.restore();
            }
            void hand(Canvas c,float angle,int length,int width,int color){
                c.save();c.rotate(angle);paint.setColor(color);paint.setStrokeWidth(width);
                c.drawLine(0,0,0,-length,paint);c.restore();
            }
        };
        dial.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        parent.addView(dial,dp(58),dp(58));
    }
    void rule(LinearLayout table,String start,String wake,boolean active,boolean heading){
        LinearLayout r=row();
        int vertical=heading?4:9;
        r.setPadding(dp(10),dp(vertical),dp(10),dp(vertical));
        if(active)r.setBackground(shape(0xffeaf1d9,10,0));
        int color=heading?MUTED:active?GREEN:INK;
        TextView first=label(start,heading?13:17,color,!heading);
        TextView second=label(wake,heading?13:17,color,!heading);
        if(!heading){first.setFontFeatureSettings("tnum");second.setFontFeatureSettings("tnum");}
        second.setGravity(Gravity.END);flex(r,first);flex(r,second);table.addView(r);
    }
}
