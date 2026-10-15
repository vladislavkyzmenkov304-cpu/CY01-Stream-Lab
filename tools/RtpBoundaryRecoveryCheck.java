package com.vk.cy01streamlab;
import java.io.*;
import java.net.SocketTimeoutException;
import java.util.Arrays;

public class RtpBoundaryRecoveryCheck {
    static byte[] packet(int seq,int ssrc,int size) {
        byte[] b=new byte[size+4]; b[0]=36; b[2]=(byte)(size>>8);b[3]=(byte)size;
        b[4]=(byte)0x80;b[5]=(byte)0xe0;b[6]=(byte)(seq>>8);b[7]=(byte)seq;
        b[12]=(byte)(ssrc>>24);b[13]=(byte)(ssrc>>16);b[14]=(byte)(ssrc>>8);b[15]=(byte)ssrc;
        b[16]=0x61;return b;
    }
    static byte[] join(byte[]... parts) throws Exception {
        ByteArrayOutputStream out=new ByteArrayOutputStream();for(byte[] p:parts)out.write(p);return out.toByteArray();
    }
    static class Feed extends ByteArrayInputStream {
        int timeoutAt;
        Feed(byte[] b,int at){super(b);timeoutAt=at;}
    }
    static void recovered(byte[] prefix,int lastSeq,byte[] a,byte[] b,int timeoutAt) throws Exception {
        byte[] wire=join(prefix,a,b);
        InputStream feed=new InputStream(){int p;boolean fired;
            public int read() throws IOException {
                if(p==timeoutAt && !fired){fired=true;throw new SocketTimeoutException("fixture");}
                return p<wire.length?wire[p++]&255:-1;
            }
            public int read(byte[] out,int off,int len)throws IOException{int n=read();if(n<0)return -1;out[off]=(byte)n;return 1;}
        };
        PushbackInputStream in=new PushbackInputStream(feed,RtpBoundaryRecovery.CAPACITY);
        int first=in.read();
        int skipped=RtpBoundaryRecovery.recover(in,first,0x10203040L,lastSeq,96);
        if(skipped!=prefix.length)throw new AssertionError("wrong boundary: "+skipped);
        if(!Arrays.equals(in.readAllBytes(),join(a,b)))throw new AssertionError("lookahead bytes lost");
    }
    static void reject(byte[] bytes)throws Exception {
        PushbackInputStream in=new PushbackInputStream(new ByteArrayInputStream(bytes),RtpBoundaryRecovery.CAPACITY);
        try{RtpBoundaryRecovery.recover(in,in.read(),0x10203040L,99,96);throw new AssertionError("false boundary accepted");}
        catch(IOException expected){}
    }
    public static void main(String[] args)throws Exception {
        byte[] a=packet(100,0x10203040,20),b=packet(101,0x10203040,30),noise={0x70,1,2,36,7,0,0};
        for(int i=1;i<noise.length+a.length+b.length;i++)recovered(noise,99,a,b,i);
        recovered(noise,65534,packet(65535,0x10203040,20),packet(0,0x10203040,30),-1);
        recovered(noise,99,packet(100,0x10203040,65535),b,-1);
        recovered(join(noise,packet(100,0x11111111,20)),99,a,b,-1);
        byte[] bogus=packet(100,0x10203040,20);bogus[2]=(byte)255;bogus[3]=(byte)255;
        recovered(join(noise,bogus),99,a,b,-1);
        reject(join(noise,a));
        reject(join(noise,a,packet(103,0x10203040,30)));
        reject(join(noise,a,packet(101,0x11111111,30)));
        reject(new byte[RtpBoundaryRecovery.SCAN_LIMIT+1]);
        System.out.println("RTP recovery PASS: false markers, SSRC, sequence/wrap, length bounds, timeout offsets, replay integrity");
    }
}
