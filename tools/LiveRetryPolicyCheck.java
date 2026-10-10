package com.vk.cy01streamlab;

public final class LiveRetryPolicyCheck {
    public static void main(String[] args) {
        LiveRetryPolicy p=new LiveRetryPolicy();
        long[] expected={1000,2000,4000,8000,10000};
        for(long e:expected) if(p.nextDelayMs(12_400,true)!=e) throw new AssertionError("backoff");
        for(int i=0;i<1000;i++) if(p.nextDelayMs(0,false)!=10000) throw new AssertionError("retry cap/overflow");
        if(p.nextDelayMs(498_000,true)!=1000) throw new AssertionError("stable session reset");
        if(p.nextDelayMs(12_400,true)!=2000) throw new AssertionError("field failure after stable session");
        p.reset();
        if(p.nextDelayMs(0,false)!=1000) throw new AssertionError("manual restart");
        System.out.println("LIVE retry policy PASS: sustained failures, bounded backoff, stable-session reset, manual reset");
    }
}
