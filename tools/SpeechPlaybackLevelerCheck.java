package com.vk.cy01streamlab;
import java.util.Arrays;
public final class SpeechPlaybackLevelerCheck {
 static void require(boolean ok,String message){if(!ok)throw new AssertionError(message);}
 static int sample(byte[] p,int i){return (short)((p[i]&255)|(p[i+1]<<8));}
 public static void main(String[] args){
  byte[] p=new byte[64000];
  for(int i=0;i<p.length;i+=2){int s=(int)(1000*Math.sin(i*Math.PI/16));p[i]=(byte)s;p[i+1]=(byte)(s>>8);}
  p[0]=0;p[1]=(byte)128;byte[] original=p.clone();
  byte[] out=SpeechPlaybackLeveler.process(p);
  require(Arrays.equals(p,original),"source mutated");require(out.length==p.length,"duration changed");
  long before=0,after=0;
  for(int i=32000;i<p.length;i+=2){before+=Math.abs(sample(p,i));after+=Math.abs(sample(out,i));}
  require(after>before*3,"single transient still suppresses quiet speech");
  for(int i=0;i<out.length;i+=2)require(Math.abs(sample(out,i))<=32000,"limiter overflow");
  byte[] silence=new byte[1001];require(Arrays.equals(silence,SpeechPlaybackLeveler.process(silence)),"silence/odd length");
  byte[] noise=new byte[32000];for(int i=0;i<noise.length;i+=2)noise[i]=16;
  require(Arrays.equals(noise,SpeechPlaybackLeveler.process(noise)),"near silence amplified");
  System.out.println("Speech playback PASS: original preserved, duration preserved, isolated peak, quiet voice gain, limiter, silence");
 }
}
