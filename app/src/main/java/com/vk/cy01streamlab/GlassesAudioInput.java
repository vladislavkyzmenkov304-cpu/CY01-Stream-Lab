package com.vk.cy01streamlab;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.*;
import android.os.Build;
import android.os.SystemClock;
import java.io.*;
import java.nio.*;
import java.util.*;
import java.util.function.Consumer;

/** Android communication audio, independent of the camera's BLE/P2P mode. */
final class GlassesAudioInput {
    static final int PERMISSION_REQUEST = 6026;
    private final Activity activity;
    private final AudioManager manager;
    private final Consumer<String> message;
    private volatile boolean active;
    private volatile Thread worker;
    private volatile String state = "off";
    private volatile long pcmBytes;
    private volatile int peak;
    private volatile boolean routeVerified;
    private final byte[] recent = new byte[16000 * 2 * 10];
    private int cursor, used;
    private MediaPlayer playback;

    GlassesAudioInput(Activity a, Consumer<String> m) {
        activity = a; message = m;
        manager = (AudioManager) a.getSystemService(Context.AUDIO_SERVICE);
    }
    String snapshot() {
        return "bluetoothMic state=" + state + " routeVerified=" + routeVerified
                + " pcmBytes=" + pcmBytes + " peak=" + peak;
    }
    private void say(String text) {
        activity.runOnUiThread(() -> { if (!activity.isFinishing()) message.accept(text); });
    }
    void toggle() {
        if (worker != null) { stop(); say("Микрофон выключается."); return; }
        if (Build.VERSION.SDK_INT < 31) { say("Этот аудиорежим требует Android 12 или новее."); return; }
        if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED
                || activity.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            activity.requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO, Manifest.permission.BLUETOOTH_CONNECT}, PERMISSION_REQUEST);
            return;
        }
        try {
            List<AudioDeviceInfo> choices = new ArrayList<>();
            for (AudioDeviceInfo d : manager.getAvailableCommunicationDevices()) {
                if (isBluetooth(d)) choices.add(d);
            }
            if (choices.isEmpty()) {
                state = "no_bluetooth_audio_device";
                say("Android не видит микрофон Bluetooth. Подключите очки как гарнитуру в настройках Bluetooth.");
                return;
            }
            String[] names = new String[choices.size()];
            for (int i=0;i<names.length;i++) names[i]=choices.get(i).getProductName().toString();
            new AlertDialog.Builder(activity).setTitle("Выберите очки для записи звука")
                    .setItems(names, (dialog, which) -> start(choices.get(which)))
                    .setNegativeButton("Отмена", null).show();
        } catch (Exception e) { state="device_error"; say("Не удалось получить аудиоустройства: " + e.getClass().getSimpleName()); }
    }
    private static boolean isBluetooth(AudioDeviceInfo d) {
        return d != null && (d.getType()==AudioDeviceInfo.TYPE_BLUETOOTH_SCO
                || d.getType()==AudioDeviceInfo.TYPE_BLE_HEADSET);
    }
    private boolean selectedRoute(AudioDeviceInfo selected, AudioDeviceInfo input) {
        AudioDeviceInfo comm=manager.getCommunicationDevice();
        if(comm==null || comm.getId()!=selected.getId() || !isBluetooth(input) || !input.isSource()) return false;
        String a=selected.getAddress(), b=input.getAddress();
        if(a!=null && b!=null && !a.isEmpty() && !b.isEmpty()) return a.equalsIgnoreCase(b);
        // No address is not proof of identity. Require matching device names too.
        String sn=selected.getProductName().toString(), in=input.getProductName().toString();
        return !sn.isEmpty() && sn.equalsIgnoreCase(in);
    }
    private void start(AudioDeviceInfo selected) {
        if(worker!=null || activity.isFinishing()) return;
        stopPlayback();
        active=true; routeVerified=false; pcmBytes=0; peak=0; cursor=0; used=0; state="routing";
        worker=new Thread(() -> capture(selected), "CY01-Bluetooth-microphone"); worker.start();
    }
    private void capture(AudioDeviceInfo selected) {
        AudioRecord recorder=null;
        int oldMode=manager.getMode();
        boolean modeChanged=false, selectedByUs=false;
        try {
            if(oldMode!=AudioManager.MODE_NORMAL) throw new IOException("Другой звонок или аудиосеанс уже активен");
            if(!active) return;
            manager.setMode(AudioManager.MODE_IN_COMMUNICATION); modeChanged=true;
            if(!manager.setCommunicationDevice(selected)) throw new IOException("Android отклонил выбор микрофона");
            selectedByUs=true;
            say("Подключение микрофона «"+selected.getProductName()+"».");
            long deadline=SystemClock.elapsedRealtime()+30000L;
            while(active && SystemClock.elapsedRealtime()<deadline) {
                AudioDeviceInfo d=manager.getCommunicationDevice();
                if(d!=null && d.getId()==selected.getId()) break;
                Thread.sleep(50L);
            }
            if(!active) return;
            AudioDeviceInfo d=manager.getCommunicationDevice();
            if(d==null || d.getId()!=selected.getId()) throw new IOException("Аудиомаршрут не подключился за 30 секунд");
            int minimum=AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
            if(minimum<=0) throw new IOException("PCM 16 кГц не поддерживается");
            recorder=new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION,16000,
                    AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,Math.max(minimum*2,6400));
            if(recorder.getState()!=AudioRecord.STATE_INITIALIZED) throw new IOException("Не удалось открыть запись");
            recorder.startRecording();
            byte[] data=new byte[640];
            long routeDeadline=SystemClock.elapsedRealtime()+5000L, lastReport=0L, lastData=SystemClock.elapsedRealtime();
            while(active) {
                int n=recorder.read(data,0,data.length,AudioRecord.READ_NON_BLOCKING);
                if(n<0) throw new IOException("AudioRecord read="+n);
                boolean matches=selectedRoute(selected,recorder.getRoutedDevice());
                if(!matches) {
                    if(routeVerified || SystemClock.elapsedRealtime()>routeDeadline)
                        throw new IOException("Маршрут записи не подтверждён как выбранные очки; запись остановлена");
                    // Discard all bytes until the actual recording input is verified.
                    Thread.sleep(10L); continue;
                }
                if(!routeVerified) { routeVerified=true; state="recording"; say("Bluetooth-микрофон подключён: «"+selected.getProductName()+"»."); }
                if(n>0) {
                    lastData=SystemClock.elapsedRealtime(); pcmBytes+=n;
                    int currentPeak=0;
                    for(int i=0;i+1<n;i+=2) currentPeak=Math.max(currentPeak,Math.abs((short)((data[i]&255)|(data[i+1]<<8))));
                    peak=currentPeak;
                    synchronized(recent) {for(int i=0;i<n;i++){recent[cursor]=data[i];cursor=(cursor+1)%recent.length;used=Math.min(used+1,recent.length);}}
                    if(lastData-lastReport>=5000L) {lastReport=lastData;say("Микрофон включён · уровень " + (peak * 100 / 32768) + "%");}
                } else {
                    if(SystemClock.elapsedRealtime()-lastData>5000L) throw new IOException("Микрофон не отдаёт PCM-данные");
                    Thread.sleep(10L);
                }
            }
            state="stopped";
        } catch(Exception e) {state="error";say("Микрофон: "+e.getMessage()+". "+snapshot());}
        finally {
            if(recorder!=null){try{recorder.stop();}catch(Exception ignored){}recorder.release();}
            try {
                AudioDeviceInfo current=Build.VERSION.SDK_INT>=31?manager.getCommunicationDevice():null;
                boolean stillOurs=current==null || current.getId()==selected.getId();
                if(selectedByUs && stillOurs) manager.clearCommunicationDevice();
                if(modeChanged && stillOurs && manager.getMode()==AudioManager.MODE_IN_COMMUNICATION) manager.setMode(oldMode);
            } catch(Exception ignored) {}
            active=false; routeVerified=false; if(state.equals("routing"))state="stopped"; worker=null;
        }
    }
    void stop() { active=false; stopPlayback(); }
    private void stopPlayback() { if(playback!=null){try{playback.release();}catch(Exception ignored){}playback=null;} }
    void playRecent() {
        if(worker!=null) {say("Сначала выключите микрофон, затем прослушайте последние 10 секунд.");return;}
        byte[] pcm;
        synchronized(recent){
            if(used==0){say("Записи с подтверждённого Bluetooth-микрофона пока нет.");return;}
            pcm=new byte[used];int begin=(cursor-used+recent.length)%recent.length;
            for(int i=0;i<used;i++)pcm[i]=recent[(begin+i)%recent.length];
        }
        try {
            stopPlayback(); File f=new File(activity.getCacheDir(),"cy01_bluetooth_recent.wav");
            ByteBuffer h=ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);
            h.put(new byte[]{82,73,70,70}).putInt(36+pcm.length).put(new byte[]{87,65,86,69,102,109,116,32})
                .putInt(16).putShort((short)1).putShort((short)1).putInt(16000).putInt(32000)
                .putShort((short)2).putShort((short)16).put(new byte[]{100,97,116,97}).putInt(pcm.length);
            try(FileOutputStream out=new FileOutputStream(f)){out.write(h.array());out.write(pcm);}
            playback=new MediaPlayer();playback.setDataSource(f.getAbsolutePath());
            playback.setOnCompletionListener(p->{p.release();if(playback==p)playback=null;f.delete();});
            playback.prepare();playback.start();
        } catch(Exception e){stopPlayback();say("Не удалось воспроизвести запись: "+e.getMessage());}
    }
}
