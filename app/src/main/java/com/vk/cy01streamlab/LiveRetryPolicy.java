package com.vk.cy01streamlab;

/** A LIVE request outlives individual TCP sessions. No lifetime retry quota. */
final class LiveRetryPolicy {
    private int shortFailures;
    synchronized void reset() { shortFailures=0; }
    synchronized long nextDelayMs(long sessionMs, boolean rendered) {
        if(rendered && sessionMs>=60_000L) shortFailures=0;
        shortFailures=Math.min(5,shortFailures+1);
        return Math.min(10_000L,1000L << (shortFailures-1));
    }
}
