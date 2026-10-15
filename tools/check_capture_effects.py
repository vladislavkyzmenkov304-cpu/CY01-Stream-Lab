"""Exercise the actual session-effects helper against controlled Android API responses."""
from pathlib import Path
import tempfile, subprocess
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    package=root/'android/media/audiofx';package.mkdir(parents=True)
    (package/'AudioEffect.java').write_text('''package android.media.audiofx;
public class AudioEffect {
 public static boolean available=true, control=true, fail=false, initial=true;
 public static int writes,releases;
 private boolean enabled=initial;
 public boolean getEnabled(){return enabled;}
 public boolean hasControl(){return control;}
 public int setEnabled(boolean value){writes++;if(fail)return -5;enabled=value;return 0;}
 public void release(){releases++;}
}''')
    for name in ['NoiseSuppressor','AutomaticGainControl','AcousticEchoCanceler']:
        (package/(name+'.java')).write_text('package android.media.audiofx; public class '+name+' extends AudioEffect { public static boolean isAvailable(){return available;} public static '+name+' create(int session){return new '+name+'();}}')
    test=root/'CaptureEffectsCheck.java'
    test.write_text('''package com.vk.cy01streamlab;
import android.media.audiofx.AudioEffect;
public class CaptureEffectsCheck {
 static void check(boolean v){if(!v)throw new AssertionError();}
 public static void main(String[] args){
  CaptureAudioEffects e=new CaptureAudioEffects(7,false);
  check(AudioEffect.writes==0 && e.snapshot().contains("enabled=true"));e.close();
  check(AudioEffect.releases==3);
  e=new CaptureAudioEffects(8,true);
  check(AudioEffect.writes==3 && e.snapshot().contains("offObserved=true"));e.close();
  AudioEffect.fail=true;e=new CaptureAudioEffects(9,true);
  check(e.snapshot().contains("disableResult=-5") && e.snapshot().contains("offObserved=false"));e.close();
  AudioEffect.control=false;int before=AudioEffect.writes;e=new CaptureAudioEffects(10,true);
  check(AudioEffect.writes==before && e.snapshot().contains("no_control") && e.snapshot().contains("offObserved=false"));e.close();
  AudioEffect.available=false;e=new CaptureAudioEffects(11,true);
  check(e.snapshot().contains("unavailable") && !e.snapshot().contains("offObserved=true"));e.close();
  System.out.println("Capture effects PASS: standard unchanged, off verified, rejection, no control, unavailable, release");
 }
}''')
    subprocess.run(['javac','-d',tmp,*map(str,package.glob('*.java')),'app/src/main/java/com/vk/cy01streamlab/CaptureAudioEffects.java',str(test)],check=True)
    subprocess.run(['java','-cp',tmp,'com.vk.cy01streamlab.CaptureEffectsCheck'],check=True)
