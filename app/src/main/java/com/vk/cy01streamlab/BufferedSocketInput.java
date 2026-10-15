package com.vk.cy01streamlab;

import java.io.*;
import java.net.SocketTimeoutException;

/** One socket reader, bounded byte-preserving queue, independent of codec work. */
final class BufferedSocketInput extends InputStream {
    private final InputStream source;
    private final byte[] ring;
    private final int timeoutMs;
    private final Thread reader;
    private int head, size, peak;
    private long received, maxGapMs, lastReceiveNs, fullWaits;
    private boolean closed, ended;
    private IOException failure;

    BufferedSocketInput(InputStream source) { this(source, 512*1024, 2500); }
    BufferedSocketInput(InputStream source,int capacity,int timeoutMs) {
        this.source=source;this.ring=new byte[capacity];this.timeoutMs=timeoutMs;
        reader=new Thread(this::pump,"CY01-socket-reader");reader.setDaemon(true);reader.start();
    }
    private void pump() {
        byte[] chunk=new byte[Math.min(16384,ring.length)];
        try {
            while(true) {
                synchronized(this){if(closed)return;}
                int n;
                try{n=source.read(chunk);}catch(SocketTimeoutException idle){continue;}
                if(n<0)break;
                if(n==0)continue;
                synchronized(this) {
                    long now=System.nanoTime();
                    if(lastReceiveNs!=0)maxGapMs=Math.max(maxGapMs,(now-lastReceiveNs)/1_000_000L);
                    lastReceiveNs=now;received+=n;
                }
                int off=0;
                while(off<n) {
                    synchronized(this) {
                        while(size==ring.length && !closed){fullWaits++;wait();}
                        if(closed)return;
                        int tail=(head+size)%ring.length;
                        int count=Math.min(n-off,Math.min(ring.length-size,ring.length-tail));
                        System.arraycopy(chunk,off,ring,tail,count);
                        off+=count;size+=count;peak=Math.max(peak,size);notifyAll();
                    }
                }
            }
        } catch(InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            synchronized(this){if(!closed)failure=new IOException("Socket reader interrupted",interrupted);}
        } catch(IOException error) {
            synchronized(this){if(!closed)failure=error;}
        } finally { synchronized(this){ended=true;notifyAll();} }
    }
    @Override public synchronized int read(byte[] out,int off,int len)throws IOException {
        if(off<0 || len<0 || off>out.length-len)throw new IndexOutOfBoundsException();
        if(len==0)return 0;
        long end=System.nanoTime()+timeoutMs*1_000_000L;
        while(size==0 && !closed && !ended) {
            long left=end-System.nanoTime();
            if(left<=0)throw new SocketTimeoutException("No bytes from socket reader");
            try{wait(Math.max(1L,left/1_000_000L));}
            catch(InterruptedException e){Thread.currentThread().interrupt();throw new IOException("Read interrupted",e);}
        }
        if(closed)throw new IOException("Socket input closed");
        if(size==0){if(failure!=null)throw failure;return -1;}
        int count=Math.min(len,Math.min(size,ring.length-head));
        System.arraycopy(ring,head,out,off,count);
        head=(head+count)%ring.length;size-=count;notifyAll();return count;
    }
    @Override public int read()throws IOException {byte[] b=new byte[1];return read(b,0,1)<0?-1:b[0]&255;}
    @Override public synchronized int available(){return size;}
    synchronized String snapshot(){return "socketReadBytes="+received+" socketReadMaxGapMs="+maxGapMs+" socketQueueBytes="+size+" socketQueuePeak="+peak+" socketFullWaits="+fullWaits;}
    @Override public void close()throws IOException {
        synchronized(this){closed=true;notifyAll();}
        try{source.close();}finally{reader.interrupt();}
    }
}
