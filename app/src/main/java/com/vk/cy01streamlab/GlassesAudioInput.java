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
    private boolean disableAndroidEffects;
    private volatile String recordedMode = "standard";
    private volatile String effectsReport = "not_started";
    void chooseCaptureMode() {
        if(worker!=null){say("Выключите микрофон перед сменой режима.");return;}
        new AlertDialog.Builder(activity).setTitle("Обработка записи")
            .setSingleChoiceItems(new String[]{"Стандартный", "Без эффектов Android (если доступно)"},
                disableAndroidEffects?1:0, (dialog,which)->{
                    if(worker!=null){say("Сначала выключите микрофон.");dialog.dismiss();return;}
                    disableAndroidEffects=which==1;
                    say("Режим следующей записи: "+(disableAndroidEffects?"без эффектов Android (если доступно)":"стандартный")
                        +". Обработка внутри очков этим переключателем не управляется.");
                    dialog.dismiss();
                }).setNegativeButton("Отмена",null).show();
    }
    private volatile boolean active;
    private volatile Thread worker;
    private volatile String state = "off";
    private volatile long pcmBytes, maxReadGapMs;
    private volatile int peak, sessionPeak;
    private volatile double rmsDb = -120.0;
    private volatile String clientSilenced = "unknown";
    private volatile boolean systemMuted;
    private volatile String inputDescription = "none";
    private volatile boolean routeVerified;
    private final byte[] recent = new byte[16000 * 2 * 120];
    private int cursor, used;
    private MediaPlayer playback;
    private File playbackFile;
    private volatile int playbackEpoch;

    GlassesAudioInput(Activity a, Consumer<String> m) {
        activity = a; message = m;
        manager = (AudioManager) a.getSystemService(Context.AUDIO_SERVICE);
    }
    String snapshot() {
        return "bluetoothMic state=" + state + " routeVerified=" + routeVerified
                + " maxReadGapMs="+maxReadGapMs+" source=MIC pcmBytes=" + pcmBytes + " peak=" + peak + " sessionPeak=" + sessionPeak
                + " rmsDbFS=" + String.format(Locale.US, "%.1f", rmsDb)
                + " clientSilenced=" + clientSilenced + " systemMuted=" + systemMuted
                + " input=" + inputDescription + " captureMode="+recordedMode+" androidEffects={"+effectsReport+"}";
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
        active=true; routeVerified=false; pcmBytes=0; maxReadGapMs=0; peak=0; sessionPeak=0; rmsDb=-120.0;
        clientSilenced="unknown"; systemMuted=false; inputDescription="none";
        synchronized(recent) { cursor=0; used=0; }
        recordedMode=disableAndroidEffects?"android_fx_off_requested":"standard";
        effectsReport="not_started";
        state="routing";
        worker=new Thread(() -> capture(selected), "CY01-Bluetooth-microphone"); worker.start();
    }
    private void capture(AudioDeviceInfo selected) {
        AudioRecord recorder=null;
        CaptureAudioEffects effects=null;
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
            recorder=new AudioRecord(MediaRecorder.AudioSource.MIC,16000,
                    AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,Math.max(minimum*2,32000));
            if(recorder.getState()!=AudioRecord.STATE_INITIALIZED) throw new IOException("Не удалось открыть запись");
            // Prefer the matching input as well as the selected communication output.
            for (AudioDeviceInfo input : manager.getDevices(AudioManager.GET_DEVICES_INPUTS)) {
                if (selectedRoute(selected, input)) {
                    say("Bluetooth input preference accepted=" + recorder.setPreferredDevice(input));
                    break;
                }
            }
            effects=new CaptureAudioEffects(recorder.getAudioSessionId(),
                    recordedMode.equals("android_fx_off_requested"));
            effectsReport=effects.snapshot();
            say("Обработка Android: "+effectsReport);
            recorder.startRecording();
            if(recorder.getRecordingState()!=AudioRecord.RECORDSTATE_RECORDING)
                throw new IOException("AudioRecord не начал запись");
            byte[] data=new byte[640];
            long routeDeadline=SystemClock.elapsedRealtime()+5000L, lastReport=0L, lastData=SystemClock.elapsedRealtime();
            long windowSamples=0L;
            double windowSquares=0.0;
            int windowPeak=0;
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
                if(!routeVerified) { routeVerified=true; state="receiving_pcm"; say("Маршрут Bluetooth подтверждён: «"+selected.getProductName()+"»."); }
                if(n>0) {
                    long receivedAt=SystemClock.elapsedRealtime();
                    if(pcmBytes>0) maxReadGapMs=Math.max(maxReadGapMs,receivedAt-lastData);
                    lastData=receivedAt; pcmBytes+=n;
                    for(int i=0;i+1<n;i+=2) {
                        int sample=(short)((data[i]&255)|(data[i+1]<<8));
                        int magnitude=Math.abs(sample);
                        windowPeak=Math.max(windowPeak,magnitude);
                        sessionPeak=Math.max(sessionPeak,magnitude);
                        windowSquares+=(double)sample*sample;
                        windowSamples++;
                    }
                    synchronized(recent) {for(int i=0;i<n;i++){recent[cursor]=data[i];cursor=(cursor+1)%recent.length;used=Math.min(used+1,recent.length);}}
                    if(lastData-lastReport>=1000L) {
                        lastReport=lastData;
                        peak=windowPeak;
                        rmsDb=windowSamples>0 && windowSquares>0
                                ? 20.0*Math.log10(Math.sqrt(windowSquares/windowSamples)/32768.0) : -120.0;
                        windowPeak=0; windowSquares=0.0; windowSamples=0;
                        String observedEffects=effects.snapshot();
                        if(!observedEffects.equals(effectsReport)){
                            effectsReport=observedEffects;say("Обработка Android: "+effectsReport);
                        }
                        systemMuted=manager.isMicrophoneMute();
                        AudioRecordingConfiguration config=recorder.getActiveRecordingConfiguration();
                        clientSilenced=config==null ? "unknown" : Boolean.toString(config.isClientSilenced());
                        AudioDeviceInfo actual=recorder.getRoutedDevice();
                        inputDescription=actual==null ? "none" : actual.getProductName()+"/type="+actual.getType()
                                +"/rate="+(config==null ? "unknown" : config.getFormat().getSampleRate());
                        if(systemMuted || "true".equals(clientSilenced)) {
                            state="system_silenced";
                            say("Запись заглушена Android: mute="+systemMuted+", silenced="+clientSilenced);
                        } else {
                            state=rmsDb < -60.0 ? "low_signal" : "signal_present";
                            say((rmsDb < -60.0 ? "Сигнал почти отсутствует" : "Есть аудиосигнал")
                                    +String.format(Locale.US," · %.1f dBFS · пик %.2f%%",rmsDb,peak*100.0/32768.0));
                        }
                    }
                } else {
                    if(SystemClock.elapsedRealtime()-lastData>5000L) throw new IOException("Микрофон не отдаёт PCM-данные");
                    Thread.sleep(10L);
                }
            }
            state="stopped";
            say("Запись остановлена. " + snapshot());
        } catch(Exception e) {state="error";say("Микрофон: "+e.getMessage()+". "+snapshot());}
        finally {
            if(effects!=null){effectsReport=effects.snapshot();effects.close();}
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
    private void stopPlayback() { playbackEpoch++; if(playbackFile!=null){playbackFile.delete();playbackFile=null;} if(playback!=null){try{playback.release();}catch(Exception ignored){}playback=null;} }
    private volatile boolean savingWav;
    void saveOriginalWav() {
        if(worker!=null){say("Сначала выключите микрофон, затем сохраните WAV.");return;}
        if(savingWav){say("WAV уже сохраняется…");return;}
        if(Build.VERSION.SDK_INT<29){say("Сохранение WAV требует Android 10 или новее.");return;}
        final byte[] pcm;
        synchronized(recent){
            if(used==0){say("Записи пока нет. Включите микрофон, затем выключите его.");return;}
            pcm=new byte[used];int begin=(cursor-used+recent.length)%recent.length;
            int first=Math.min(used,recent.length-begin);
            System.arraycopy(recent,begin,pcm,0,first);
            System.arraycopy(recent,0,pcm,first,used-first);
        }
        final String exportMode=recordedMode;
        savingWav=true;
        say("Сохранение исходного WAV…");
        new Thread(()->{
            android.net.Uri uri=null;
            android.content.ContentResolver resolver=activity.getApplicationContext().getContentResolver();
            String name="CY01_original_"+exportMode+"_"+new java.text.SimpleDateFormat("yyyyMMdd_HHmmss_SSS",Locale.US).format(new Date())+".wav";
            try {
                android.content.ContentValues values=new android.content.ContentValues();
                values.put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME,name);
                values.put(android.provider.MediaStore.MediaColumns.MIME_TYPE,"audio/wav");
                values.put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH,android.os.Environment.DIRECTORY_DOWNLOADS+"/CY01");
                values.put(android.provider.MediaStore.MediaColumns.IS_PENDING,1);
                uri=resolver.insert(android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI,values);
                if(uri==null)throw new IOException("Не удалось создать файл");
                ByteBuffer h=ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);
                h.put(new byte[]{82,73,70,70}).putInt(36+pcm.length).put(new byte[]{87,65,86,69,102,109,116,32})
                    .putInt(16).putShort((short)1).putShort((short)1).putInt(16000).putInt(32000)
                    .putShort((short)2).putShort((short)16).put(new byte[]{100,97,116,97}).putInt(pcm.length);
                try(OutputStream out=resolver.openOutputStream(uri,"w")){
                    if(out==null)throw new IOException("Не удалось открыть файл");
                    out.write(h.array());out.write(pcm);
                }
                values.clear();values.put(android.provider.MediaStore.MediaColumns.IS_PENDING,0);
                if(resolver.update(uri,values,null,null)!=1)throw new IOException("Не удалось завершить сохранение");
                say(String.format(Locale.US,"WAV сохранён: Загрузки/CY01/%s · %.1f с · оригинал без обработки (до 120 с)",name,pcm.length/32000.0));
            }catch(Exception e){
                if(uri!=null)try{resolver.delete(uri,null,null);}catch(Exception ignored){}
                say("Не удалось сохранить WAV: "+e.getMessage());
            }finally{savingWav=false;}
        },"CY01-save-wav").start();
    }

    void playRecent() { playRecent(true); }
    void playRecent(boolean enhanced) {
        if(worker!=null) {say("Сначала выключите микрофон, затем прослушайте запись.");return;}
        byte[] pcm;
        synchronized(recent){
            if(used==0){say("Записи с подтверждённого Bluetooth-микрофона пока нет.");return;}
            pcm=new byte[used];int begin=(cursor-used+recent.length)%recent.length;
            int first=Math.min(used,recent.length-begin);
            System.arraycopy(recent,begin,pcm,0,first);
            System.arraycopy(recent,0,pcm,first,used-first);
        }
        stopPlayback();
        final int epoch=playbackEpoch;
        final byte[] captured=pcm;
        say("Подготовка записи для прослушивания…");
        new Thread(()->{
          File prepared=null;
          try {
            byte[] review=enhanced ? SpeechPlaybackLeveler.process(captured) : captured;
            File f=File.createTempFile("cy01_review_",".wav",activity.getCacheDir());
            prepared=f;
            ByteBuffer h=ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);
            h.put(new byte[]{82,73,70,70}).putInt(36+review.length).put(new byte[]{87,65,86,69,102,109,116,32})
                .putInt(16).putShort((short)1).putShort((short)1).putInt(16000).putInt(32000)
                .putShort((short)2).putShort((short)16).put(new byte[]{100,97,116,97}).putInt(review.length);
            try(FileOutputStream out=new FileOutputStream(f)){out.write(h.array());out.write(review);}
            activity.runOnUiThread(()->{
                if(epoch!=playbackEpoch || active || activity.isFinishing()){f.delete();return;}
                say(String.format(Locale.US,"Воспроизведение %.1f с · %s",review.length/32000.0,enhanced ? "выравнивание речи" : "оригинал"));
                startPreparedPlayback(f);
            });
          } catch(Exception e){if(prepared!=null)prepared.delete();say("Не удалось подготовить запись: "+e.getMessage());}
        },"CY01-audio-review").start();
    }
    private void startPreparedPlayback(File f) {
        try {
            playbackFile=f;
            playback=new MediaPlayer();
            playback.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());
            playback.setDataSource(f.getAbsolutePath());
            playback.setOnCompletionListener(p->{p.release();if(playback==p)playback=null;f.delete();});
            // Explicitly prefer the phone speaker for review while video reception continues.
            if(Build.VERSION.SDK_INT>=28) {
                for(AudioDeviceInfo output:manager.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) {
                    if(output.getType()==AudioDeviceInfo.TYPE_BUILTIN_SPEAKER) {
                        say("Прослушивание: динамик телефона, запрос маршрута="+playback.setPreferredDevice(output));
                        break;
                    }
                }
            }
            playback.setOnPreparedListener(p->{if(playback==p)p.start();});
            playback.setOnErrorListener((p,what,extra)->{if(playback==p)stopPlayback();f.delete();say("Ошибка прослушивания: "+what+"/"+extra);return true;});
            playback.prepareAsync();
            final MediaPlayer started=playback;
            new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(()->{
                if(playback!=started || Build.VERSION.SDK_INT<28)return;
                try{
                    AudioDeviceInfo route=started.getRoutedDevice();
                    say("Маршрут воспроизведения: "+(route==null ? "не подтверждён" : route.getProductName()+"/type="+route.getType()));
                }catch(Exception ignored){}
            },500L);
        } catch(Exception e){stopPlayback();say("Не удалось воспроизвести запись: "+e.getMessage());}
    }
}
