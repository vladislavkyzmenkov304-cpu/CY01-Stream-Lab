package com.vk.cy01streamlab;

import java.io.*;
import java.net.SocketTimeoutException;

/** Bounded recovery: never accept a dollar byte alone as a packet boundary. */
final class RtpBoundaryRecovery {
    static final int CAPACITY = 196640;
    static final int SCAN_LIMIT = 65536;
    private final InputStream input;
    private final byte[] bytes = new byte[CAPACITY];
    private final long deadline = System.nanoTime() + 3_000_000_000L;
    private int size;
    private RtpBoundaryRecovery(InputStream input, int first) {
        this.input=input; bytes[size++]=(byte)first;
    }
    private void ensure(int count) throws IOException {
        if(count>bytes.length) throw new IOException("RTP recovery byte budget exceeded");
        while(size<count) {
            if(System.nanoTime()>deadline) throw new IOException("RTP recovery deadline exceeded");
            try {
                int n=input.read(bytes,size,count-size);
                if(n<0) throw new EOFException("EOF during RTP boundary recovery");
                size+=n;
            } catch(SocketTimeoutException timeout) {
                // Keep every byte already received until the overall deadline.
            }
        }
    }
    private int u16(int p) { return ((bytes[p]&255)<<8)|(bytes[p+1]&255); }
    private long u32(int p) { return ((long)u16(p)<<16)|u16(p+2); }
    private int frameLength(int p, long ssrc, int pt) throws IOException {
        ensure(p+4);
        if(bytes[p]!=36 || bytes[p+1]!=0) return -1;
        int len=u16(p+2);
        if(len<13) return -1;
        ensure(p+16);
        if((bytes[p+4]&0xc0)!=0x80 || (bytes[p+5]&127)!=pt || u32(p+12)!=ssrc) return -1;
        ensure(p+4+len);
        int end=p+4+len, payload=p+16+4*(bytes[p+4]&15);
        if((bytes[p+4]&16)!=0) {
            if(payload+4>end)return -1;
            payload+=4+4*u16(payload+2);
        }
        if((bytes[p+4]&32)!=0) {
            int padding=bytes[end-1]&255;
            if(padding==0)return -1;
            end-=padding;
        }
        if(payload>=end)return -1;
        int nal=bytes[payload]&31;
        if((bytes[payload]&128)!=0 || !(nal>=1 && nal<=23 || nal==24 || nal==28))return -1;
        if(nal==28 && payload+2>=end)return -1;
        return len+4;
    }
    static int recover(PushbackInputStream input,int first,long ssrc,int lastSeq,int pt) throws IOException {
        RtpBoundaryRecovery scan=new RtpBoundaryRecovery(input,first);
        for(int p=0;p<SCAN_LIMIT;p++) {
            scan.ensure(p+1);
            if(scan.bytes[p]!=36)continue;
            int length;
            try { length=scan.frameLength(p,ssrc,pt); } catch(EOFException incompleteCandidate) { continue; }
            if(length<0)continue;
            int seq=scan.u16(p+6), advance=(seq-lastSeq)&65535;
            if(advance==0 || advance>4096)continue;
            int next=p+length;
            try { if(scan.frameLength(next,ssrc,pt)<0)continue; } catch(EOFException incompleteCandidate) { continue; }
            if(((scan.u16(next+6)-seq)&65535)!=1)continue;
            if(((scan.u32(next+8)-scan.u32(p+8))&0xffffffffL)>900000L)continue;
            input.unread(scan.bytes,p,scan.size-p);
            return p;
        }
        throw new IOException("No two matching RTP frames within recovery byte budget");
    }
}
