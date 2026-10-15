package com.vk.cy01streamlab;

/** Maps RTP-derived media time to the monotonic Surface clock. */
final class VideoPresentationClock {
    static final long BUFFER_NS=250_000_000L;
    private boolean initialized;
    private long anchorNs;
    long rebuffers, lateDrops;
    void reset(){initialized=false;}
    // Anchor on packet arrival, before codec setup/queueing. A delayed output
    // must not permanently add the decoder startup time to every future frame.
    void observe(long ptsUs,long arrivalNs) {
        long candidate=arrivalNs+BUFFER_NS-ptsUs*1000L;
        if(!initialized || candidate<anchorNs){anchorNs=candidate;initialized=true;}
    }
    long schedule(long ptsUs,long nowNs) {
        long mediaNs=ptsUs*1000L;
        if(!initialized){anchorNs=nowNs+BUFFER_NS-mediaNs;initialized=true;}
        long due=anchorNs+mediaNs;
        if(due<nowNs-500_000_000L || due>nowNs+750_000_000L) {
            anchorNs=nowNs+BUFFER_NS-mediaNs;due=nowNs+BUFFER_NS;rebuffers++;
        }
        if(due<nowNs-80_000_000L){lateDrops++;return -1L;}
        return Math.max(nowNs,due);
    }
}
