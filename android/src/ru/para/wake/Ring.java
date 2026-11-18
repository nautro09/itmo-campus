package ru.para.wake;

import android.app.*;
import android.content.*;
import android.media.*;
import android.os.*;

public class Ring extends Service {
    private MediaPlayer player;
    private final Handler timer=new Handler(Looper.getMainLooper());
    public IBinder onBind(Intent intent){return null;}
    public int onStartCommand(Intent intent,int flags,int id){
        if(intent!=null && "STOP".equals(intent.getAction())){stopSelf();return START_NOT_STICKY;}
        NotificationManager nm=getSystemService(NotificationManager.class);
        NotificationChannel channel=new NotificationChannel("alarm","Учебный будильник",NotificationManager.IMPORTANCE_HIGH);
        channel.setSound(null,null);
        nm.createNotificationChannel(channel);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,Ring.class).setAction("STOP"),Alarms.FLAGS);
        Notification n=new Notification.Builder(this,"alarm").setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle("Пора вставать · ИТМО").setContentText("Нажми «Выключить», чтобы остановить звонок.")
            .setCategory(Notification.CATEGORY_ALARM).setContentIntent(Alarms.show(this)).setOngoing(true)
            .addAction(android.R.drawable.ic_delete,"Выключить",stop).build();
        startForeground(3,n);
        if(player==null){
            try {
                player=new MediaPlayer();
                player.setWakeMode(this,PowerManager.PARTIAL_WAKE_LOCK);
                player.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build());
                android.net.Uri tone=RingtoneManager.getActualDefaultRingtoneUri(this,RingtoneManager.TYPE_ALARM);
                try {
                    if(tone==null) throw new java.io.IOException();
                    player.setDataSource(this,tone);
                } catch(Exception unavailable){
                    try(android.content.res.AssetFileDescriptor fd=getAssets().openFd("wake.wav")){
                        player.setDataSource(fd.getFileDescriptor(),fd.getStartOffset(),fd.getLength());
                    }
                }
                player.setLooping(true);player.prepare();player.start();
            } catch(Exception e){stopSelf();}
        }
        timer.removeCallbacksAndMessages(null);timer.postDelayed(this::stopSelf,intent!=null && "TEST".equals(intent.getAction()) ? 10000 : 5*60*1000);
        return START_NOT_STICKY;
    }
    public void onDestroy(){timer.removeCallbacksAndMessages(null);if(player!=null)player.release();stopForeground(STOP_FOREGROUND_REMOVE);super.onDestroy();}
}
