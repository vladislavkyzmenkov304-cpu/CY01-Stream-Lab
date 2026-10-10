package com.vk.cy01streamlab;
import java.io.*;
import java.net.SocketTimeoutException;
import java.util.Arrays;
import java.util.concurrent.*;

public class VideoPipelineCheck {
    static void require(boolean ok,String why){if(!ok)throw new AssertionError(why);}
    public static void main(String[] args)throws Exception {
        byte[] wire=new byte[200000];for(int i=0;i<wire.length;i++)wire[i]=(byte)(i*37);
        CountDownLatch filled=new CountDownLatch(1);
        InputStream source=new ByteArrayInputStream(wire){
            @Override public synchronized int read(byte[] b,int off,int n){int result=super.read(b,off,n);if(pos>=4096)filled.countDown();return result;}
        };
        try(BufferedSocketInput pump=new BufferedSocketInput(source,4096,500)) {
            require(filled.await(2,TimeUnit.SECONDS),"producer must read while consumer is paused");
            require(Arrays.equals(wire,pump.readAllBytes()),"bounded queue lost or reordered bytes");
        }
        InputStream timeoutThenData=new InputStream(){int call;
            public int read()throws IOException{if(call++==0)throw new SocketTimeoutException();return call==2 ? 77 : -1;}
            public int read(byte[] b,int off,int len)throws IOException{int v=read();if(v<0)return -1;b[off]=(byte)v;return 1;}
        };
        try(BufferedSocketInput pump=new BufferedSocketInput(timeoutThenData,64,500)) {
            require(pump.read()==77 && pump.read()==-1,"socket timeout must not discard following data");
        }
        InputStream errorAfterData=new InputStream(){int call;
            public int read()throws IOException{if(call++==0)return 42;throw new IOException("fixture failure");}
            public int read(byte[] b,int off,int len)throws IOException{b[off]=(byte)read();return 1;}
        };
        try(BufferedSocketInput pump=new BufferedSocketInput(errorAfterData,64,500)) {
            require(pump.read()==42,"data before error must be delivered");
            try{pump.read();throw new AssertionError("error hidden");}catch(IOException expected){}
        }
        CountDownLatch released=new CountDownLatch(1);
        InputStream paused=new InputStream(){
            public int read()throws IOException{try{released.await();return -1;}catch(InterruptedException e){throw new IOException(e);}}
            public void close(){released.countDown();}
        };
        BufferedSocketInput pump=new BufferedSocketInput(paused,64,30);
        try{pump.read();throw new AssertionError("reader must time out");}catch(SocketTimeoutException expected){}
        pump.close();
        try{pump.read();throw new AssertionError("closed reader accepted");}catch(IOException expected){}

        VideoPresentationClock clock=new VideoPresentationClock();long now=10_000_000_000L;
        long first=clock.schedule(0,now),second=clock.schedule(33333,now+1_000_000L);
        require(first==now+250_000_000L,"initial jitter buffer");
        require(second-first==33_333_000L,"burst delivery must preserve media frame spacing");
        require(clock.schedule(66666,now+450_000_000L)==-1,"late output should be dropped");
        long afterGap=clock.schedule(100000,now+5_000_000_000L);
        require(afterGap==now+5_250_000_000L && clock.rebuffers==1,"long stall must rebase clock");
        clock.reset();require(clock.schedule(9_000_000,now)==now+250_000_000L,"decoder reset clock");
        System.out.println("Video pipeline PASS: independent reader, queue wrap/backpressure, timeout preservation, EOF/error/close, burst pacing, late drop, stall rebase");
    }
}
