package com.vk.cy01streamlab;

/** Playback-only 16 kHz PCM16 leveler. Never mutates the captured source. */
final class SpeechPlaybackLeveler {
    static byte[] process(byte[] source) {
        byte[] out=source.clone();
        // Smooth gain over 20 ms windows. Ignore near-silence, cap boost at 12 dB.
        double gain=1.0;
        for(int begin=0;begin+1<out.length;begin+=640) {
            int end=Math.min(out.length,begin+640), count=(end-begin)/2;
            double squares=0;
            for(int i=begin;i+1<end;i+=2){int s=sample(source,i);squares+=(double)s*s;}
            double rms=Math.sqrt(squares/Math.max(1,count));
            double target=rms<60 ? 1.0 : Math.max(1.0,Math.min(4.0,3277.0/rms));
            double next=gain+(target-gain)*(target<gain ? 0.5 : 0.12);
            for(int i=begin;i+1<end;i+=2) {
                double g=gain+(next-gain)*(i-begin)/(double)Math.max(2,end-begin);
                double v=sample(source,i)*g, a=Math.abs(v);
                // Continuous soft limiter: avoid integer wrap and abrupt hard clipping.
                if(a>24000) v=Math.copySign(24000+8000*(1-Math.exp(-(a-24000)/8000)),v);
                int s=(int)Math.round(v);out[i]=(byte)s;out[i+1]=(byte)(s>>8);
            }
            gain=next;
        }
        return out;
    }
    private static int sample(byte[] p,int i){return (short)((p[i]&255)|(p[i+1]<<8));}
}
