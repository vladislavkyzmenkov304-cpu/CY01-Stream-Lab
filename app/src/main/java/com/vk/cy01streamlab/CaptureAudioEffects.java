package com.vk.cy01streamlab;

import android.media.audiofx.AudioEffect;
import android.media.audiofx.NoiseSuppressor;
import android.media.audiofx.AutomaticGainControl;
import android.media.audiofx.AcousticEchoCanceler;

/** Session-scoped Android effects only; cannot bypass headset firmware processing. */
final class CaptureAudioEffects {
    private final AudioEffect[] effects = new AudioEffect[3];
    private final String[] names = {"NS", "AGC", "AEC"};
    private final String[] initial = new String[3];
    private final boolean disable;

    CaptureAudioEffects(int session, boolean disable) {
        this.disable = disable;
        for(int i=0;i<effects.length;i++) {
            try {
                boolean available=i==0?NoiseSuppressor.isAvailable():
                        i==1?AutomaticGainControl.isAvailable():AcousticEchoCanceler.isAvailable();
                if(!available){initial[i]="unavailable";continue;}
                effects[i]=i==0?NoiseSuppressor.create(session):
                        i==1?AutomaticGainControl.create(session):AcousticEchoCanceler.create(session);
                AudioEffect effect=effects[i];
                if(effect==null){initial[i]="create_failed";continue;}
                initial[i]="before="+effect.getEnabled();
                if(disable) {
                    if(effect.hasControl()) initial[i]+=",disableResult="+effect.setEnabled(false);
                    else initial[i]+=",disableResult=no_control";
                }
            } catch(RuntimeException e) {
                initial[i]=(initial[i]==null?"":initial[i]+",")+"error="+e.getClass().getSimpleName();
            }
        }
    }

    String snapshot() {
        StringBuilder out=new StringBuilder("request=").append(disable?"off":"unchanged");
        for(int i=0;i<effects.length;i++) {
            out.append("; ").append(names[i]).append('[').append(initial[i]);
            if(effects[i]!=null) {
                try {
                    boolean enabled=effects[i].getEnabled();
                    out.append(",enabled=").append(enabled).append(",control=").append(effects[i].hasControl());
                    if(disable) out.append(",offObserved=").append(!enabled);
                } catch(RuntimeException e){out.append(",state=unknown");}
            }
            out.append(']');
        }
        return out.toString();
    }

    void close() {
        for(AudioEffect effect:effects) {
            if(effect!=null)try{effect.release();}catch(RuntimeException ignored){}
        }
    }
}
