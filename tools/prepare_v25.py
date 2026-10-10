from pathlib import Path
import runpy

# v2.5: field fix for RTSP-over-TCP parser. CY01 may emit ASCII RTSP control
# messages between interleaved RTP frames; v2.4 treated the first 'R'/'M' as fatal.
runpy.run_path("tools/prepare_v24_ci.py", run_name="__main__")

def rr(t,o,n,l):
    if o not in t: raise SystemExit(l+" not found")
    return t.replace(o,n,1)

g=Path("app/build.gradle"); s=g.read_text()
s=rr(s,"applicationId 'com.vk.cy01streamlab24'","applicationId 'com.vk.cy01streamlab25'","id")
s=rr(s,"versionCode 2400","versionCode 2500","code")
s=rr(s,"versionName '2.4.0'","versionName '2.5.0'","name"); g.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java"); s=p.read_text()
s=s.replace("CY01 Live v2.4 started","CY01 Live v2.5 started").replace("CY01 Live v2.4","CY01 Live v2.5").replace("CY01StreamLab-OneTap/2.4","CY01StreamLab-OneTap/2.5")
s=s.replace("v2.4: no explicit Android Network binding","v2.5: no explicit Android Network binding").replace("v2.4 will NOT bind sockets","v2.5 will NOT bind sockets")
p.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java"); r=p.read_text()
r=r.replace("CY01 LIVE v2.4 started","CY01 LIVE v2.5 started").replace("CY01 LIVE VIDEO v2.4","CY01 LIVE VIDEO v2.5").replace("CY01StreamLab-Raw/2.4","CY01StreamLab-Raw/2.5").replace("CY01 LIVE v2.4 compact report","CY01 LIVE v2.5 compact report").replace("MIC TEST v2.4:","MIC TEST v2.5:")

old='''                if (marker != '$') {
                    framingLossCount++;
                    throw new IllegalStateException("RTSP interleaved framing lost at marker=0x"
                            + Integer.toHexString(marker & 0xFF)
                            + "; refusing destructive byte-scan resync");
                }
'''
new='''                if (marker != '$') {
                    if (marker == 'R' || marker == 'S' || marker == 'O' || marker == 'G' || marker == 'M') {
                        ByteArrayOutputStream control = new ByteArrayOutputStream(1024);
                        control.write(marker);
                        int state = 0;
                        while (control.size() < 32768) {
                            int b = in.read();
                            if (b < 0) throw new EOFException("EOF in interleaved RTSP control message");
                            control.write(b);
                            if (state == 0 && b == '\\r') state = 1;
                            else if (state == 1 && b == '\\n') state = 2;
                            else if (state == 2 && b == '\\r') state = 3;
                            else if (state == 3 && b == '\\n') break;
                            else state = b == '\\r' ? 1 : 0;
                        }
                        String controlText = control.toString(StandardCharsets.US_ASCII.name());
                        String firstLine = controlText.split("\\r\\n", 2)[0];
                        log("RTSP interleaved control message: " + firstLine);
                        continue;
                    }
                    framingLossCount++;
                    throw new IllegalStateException("RTSP interleaved framing lost at marker=0x"
                            + Integer.toHexString(marker & 0xFF));
                }
'''
r=rr(r,old,new,"interleaved control parser")

# Preserve RTSP interleaved header bytes across socket timeouts. A timeout after
# consuming channel/length previously left the parser one or two bytes off.
r = rr(r,
'''                int channel = in.read();
                int hi = in.read();
                int lo = in.read();
                if (channel < 0 || hi < 0 || lo < 0) throw new EOFException("EOF in interleaved header");
                int length = (hi << 8) | lo;
''',
'''                byte[] frameHeader = readExactly(in, 3);
                int channel = frameHeader[0] & 0xff;
                int length = ((frameHeader[1] & 0xff) << 8) | (frameHeader[2] & 0xff);
''',
"timeout-safe interleaved frame header")

r = rr(r,
'''                int channel = in.read();
                int hi = in.read();
                int lo = in.read();
                if (channel < 0 || hi < 0 || lo < 0) {
                    throw new EOFException("EOF in early interleaved RTP header");
                }
                int length = (hi << 8) | lo;
''',
'''                byte[] earlyFrameHeader = readExactly(in, 3);
                int channel = earlyFrameHeader[0] & 0xff;
                int length = ((earlyFrameHeader[1] & 0xff) << 8) | (earlyFrameHeader[2] & 0xff);
''',
"timeout-safe early RTP frame header")
# Post-PLAY RTSP control messages are multiplexed with interleaved RTP.
# Skip only known keepalive line breaks; reject invalid start-lines,
# consume any declared RTSP body, and bound the control header size.
r = rr(r,
r'''                if (marker != '$') {
                    if (marker == 'R' || marker == 'S' || marker == 'O' || marker == 'G' || marker == 'M') {
''',
r'''                if (marker != '$') {
                    if (marker == '\r' || marker == '\n') continue;
                    if (marker == 'R' || marker == 'S' || marker == 'O' || marker == 'G' || marker == 'M') {
''',
"skip interleaved RTSP keepalive blank lines")

r = rr(r,
r'''                        String controlText = control.toString(StandardCharsets.US_ASCII.name());
''',
r'''                        if (control.size() >= 32768) {
                            throw new IllegalStateException("Post-PLAY RTSP control header exceeds 32768 bytes");
                        }
                        String controlText = control.toString(StandardCharsets.US_ASCII.name());
''',
"reject truncated RTSP control header")

r = rr(r,
r'''                        log("RTSP interleaved control message: " + firstLine);
                        continue;
''',
r'''                        if (!(firstLine.startsWith("RTSP/")
                                || firstLine.startsWith("OPTIONS ")
                                || firstLine.startsWith("GET_PARAMETER ")
                                || firstLine.startsWith("SET_PARAMETER ")
                                || firstLine.startsWith("REDIRECT ")
                                || firstLine.startsWith("ANNOUNCE ")
                                || firstLine.startsWith("RECORD ")
                                || firstLine.startsWith("PLAY_NOTIFY "))) {
                            framingLossCount++;
                            throw new IllegalStateException("Non-RTSP post-PLAY data at frame boundary: "
                                    + firstLine.substring(0, Math.min(firstLine.length(), 96)));
                        }
                        int controlBodyLength = 0;
                        for (String controlLine : controlText.split("\\r\\n")) {
                            int colon = controlLine.indexOf(':');
                            if (colon > 0 && controlLine.substring(0, colon).trim()
                                    .equalsIgnoreCase("Content-Length")) {
                                try {
                                    controlBodyLength = Integer.parseInt(controlLine.substring(colon + 1).trim());
                                } catch (NumberFormatException invalid) {
                                    throw new IllegalStateException("Invalid RTSP control Content-Length", invalid);
                                }
                            }
                        }
                        if (controlBodyLength < 0 || controlBodyLength > 1048576) {
                            throw new IllegalStateException("RTSP control body out of bounds: " + controlBodyLength);
                        }
                        if (controlBodyLength != 0) readExactly(in, controlBodyLength);
                        log("RTSP interleaved control message: " + firstLine
                                + " bodyBytes=" + controlBodyLength);
                        continue;
''',
"consume control RTSP body and validate start line")

p.write_text(r)
print("v2.5 prepared: bounded RTSP control multiplex parser and timeout-safe interleaved headers")

# v2.5.2 field repair: preserve LIVE, terminate damaged reads, bounded reconnect.
g=Path('app/build.gradle'); s=g.read_text().replace('versionCode 2500','versionCode 2502').replace("versionName '2.5.0'", "versionName '2.5.2'"); g.write_text(s)
p=Path('app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java'); s=p.read_text(); s=s.replace('CY01 Live v2.5.1','CY01 Live v2.5.2').replace('CY01 Live v2.5 started','CY01 Live v2.5.2 started'); p.write_text(s)
p=Path('app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java'); r=p.read_text()
r=r.replace('CY01 LIVE v2.5', 'CY01 LIVE v2.5.2')
r=rr(r, '    private volatile boolean running;', '''    private volatile boolean running;
    private volatile long streamEndMs;
    private volatile int stopEpoch;
    private int transportRetries;
    private String previousTransportFailure = "none";''', 'recovery fields')
r=rr(r, '    private void startRawTest() {', '''    private void startRawTest() {
        if (running) return;
        transportRetries = 0;
        startRawSession();
    }

    private void startRawSession() {''', 'manual start')
r=rr(r, '        resetStreamState();', '        stopEpoch++;\n        resetStreamState();', 'invalidate pending retry')
r=rr(r, '        streamStartMs = System.currentTimeMillis();', '        streamEndMs = 0L;\n        streamStartMs = System.currentTimeMillis();', 'reset end time')
r=rr(r, '        Socket socket = null;\n        try {', '        Socket socket = null;\n        boolean retryTransport = false;\n        final int epoch = stopEpoch;\n        try {', 'retry session scope')
r=rr(r, '                    log("RAW SESSION ERROR: " + errorText(e));', '''                    retryTransport = true;
                    previousTransportFailure = errorText(e);
                    log("RAW SESSION ERROR: " + previousTransportFailure);''', 'retry on failed connection')
r=rr(r, '        } finally {\n            running = false;', '        } finally {\n            streamEndMs = System.currentTimeMillis();\n            running = false;', 'freeze end')
r=rr(r, '                    + " NAL[IDR]=" + nalCounts[5]);\n        }', '''                    + " NAL[IDR]=" + nalCounts[5]);
            if (retryTransport && epoch == stopEpoch && !micTransitionExpected) {
                preserveGoodSessionSummary();
                if (transportRetries < 2) {
                    transportRetries++;
                    log("RTSP reconnect scheduled: attempt=" + transportRetries + "/2; previous=" + previousTransportFailure);
                    main.postDelayed(() -> {
                        if (epoch == stopEpoch && !running && surfaceReady && !isFinishing()) {
                            startRawSession();
                        }
                    }, 1000L * transportRetries);
                } else {
                    status("Соединение потеряно. Две попытки восстановления завершились ошибкой.");
                }
            }
        }''', 'bounded recovery')
# Only an idle timeout BEFORE the next marker can safely restart the loop.
r=rr(r, '                int marker = in.read();', '''                int marker;
                try {
                    marker = in.read();
                } catch (SocketTimeoutException idle) {
                    timeoutCount++;
                    drainDecoder();
                    if (timeoutCount >= 4) throw new EOFException("RTSP idle for four read deadlines");
                    continue;
                }
                timeoutCount = 0;''', 'idle boundary')
r=rr(r, '''                timeoutCount++;
                if (timeoutCount <= 3 || timeoutCount % 5 == 0) {
                    log("Waiting for RTP... socket timeout #" + timeoutCount);
                }''', '''                // Never resume at a marker after abandoning a partially consumed frame.
                throw new java.io.IOException("Incomplete RTSP frame/control message; reconnect required", timeout);''', 'partial timeout terminal')
r=r.replace("marker == 'G' || marker == 'M'", "marker == 'G' || marker == 'M' || marker == 'A' || marker == 'P'")
# The old control action deliberately removed P2P and produced zero audio in field logs.
# Do not repeat that destructive experiment as a normal microphone operation.
a=r.index('    private void startCombinedMicTest() {'); b=r.index('    private void pollCameraRecoveryReady()',a)
r=r[:a]+'''    private void startCombinedMicTest() {
        log("MICROPHONE MODE unavailable: simultaneous glasses audio is not established; LIVE preserved; no BLE mode switch sent");
        status("Микрофон очков пока недоступен. Видео продолжает работать.");
    }

'''+r[b:]
r=r.replace('START MIC TEST 10s', 'МИКРОФОН — НЕДОСТУПЕН')
r=r.replace('LIVE ready. Tap МИКРОФОН — НЕДОСТУПЕН, speak continuously, then inspect/play sample.', 'Видео работает. Микрофон очков пока недоступен.')
r=rr(r, '    private void stopRawTest() {', '    private void stopRawTest() {\n        stopEpoch++;\n        if (streamEndMs == 0L) streamEndMs = System.currentTimeMillis();', 'cancel retry')
r=rr(r, '    private void preserveGoodSessionSummary() {\n        if (!firstRendered || decodedOutputCount <= 0) return;\n        long now = System.currentTimeMillis();', '    private void preserveGoodSessionSummary() {\n        if (!firstRendered || decodedOutputCount <= 0) return;\n        long now = streamEndMs > 0L ? streamEndMs : System.currentTimeMillis();', 'freeze previous stats')
r=rr(r, '    private String buildCompactDiagnosticReport() {\n        long now = System.currentTimeMillis();', '    private String buildCompactDiagnosticReport() {\n        long now = streamEndMs > 0L ? streamEndMs : System.currentTimeMillis();', 'freeze report stats')
r=rr(r, '        String result = summary + diagnosticSnapshot();', '        summary += "transportRetries=" + transportRetries + " previousTransportFailure=" + previousTransportFailure + "\\n";\n        String result = summary + diagnosticSnapshot();', 'preserve failure report')
p.write_text(r)
print('v2.5.2 prepared: LIVE-safe mic guard, bounded RTSP reconnect, frozen end statistics')

# Exercise the actual generated parser with synthetic byte streams in Cloud.
# No device identifiers or field payloads enter this public fixture.
import shutil, subprocess, tempfile
if shutil.which('javac'):
    methods=r[r.index('    private byte[] readExactly('):r.index('    private void startCombinedMicTest()')]
    harness=r'''import java.io.*;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
public class ParserCheck {
 boolean running=true; long partialFrameTimeoutCount, partialFrameTimeoutBytes, framingLossCount;
 int packets; byte[] last;
 void log(String s) {} void drainDecoder() {}
 void handleInterleavedPacket(int channel, byte[] bytes) { packets++; last=bytes; }
 static class Feed extends InputStream {
  byte[] data; int pos, at, remaining;
  Feed(byte[] d,int a,int count) {data=d;at=a;remaining=count;}
  public int read() throws IOException {
   if(pos==at && remaining-- > 0) throw new SocketTimeoutException("injected");
   return pos<data.length ? data[pos++]&255 : -1;
  }
  public int read(byte[] b,int off,int len) throws IOException {
   int v=read(); if(v<0)return -1; b[off]=(byte)v;return 1;
  }
 }
 void consume(Feed f) throws Exception {try {readInterleaved(f);}catch(EOFException expected){}}
 public static void main(String[] args) throws Exception {
  byte[] frame=new byte[]{36,0,0,3,10,20,30};
  for(int i=0;i<frame.length;i++){
   ParserCheck c=new ParserCheck(); c.consume(new Feed(frame,i,1));
   if(c.packets!=1 || c.last[2]!=30)throw new AssertionError("lost alignment at "+i);
  }
  ParserCheck c=new ParserCheck();
  try{c.readInterleaved(new Feed(frame,5,4));throw new AssertionError("partial deadline swallowed");}
  catch(IOException expected){if(expected instanceof EOFException)throw new AssertionError(expected);}
  if(c.packets!=0)throw new AssertionError("truncated frame delivered");
  String control="RTSP/1.0 200 OK\r\nContent-Length: 3\r\n\r\nabc";
  ByteArrayOutputStream b=new ByteArrayOutputStream();b.write(control.getBytes(StandardCharsets.US_ASCII));b.write(frame);
  c=new ParserCheck();c.consume(new Feed(b.toByteArray(),-1,0));
  if(c.packets!=1)throw new AssertionError("body boundary");
  c=new ParserCheck();
  try{c.readInterleaved(new Feed(new byte[]{(byte)0xd3},-1,0));throw new AssertionError("invalid marker accepted");}
  catch(IllegalStateException expected){if(c.framingLossCount!=1)throw new AssertionError("counter");}
  c=new ParserCheck();c.consume(new Feed(frame,0,4));if(c.packets!=0)throw new AssertionError("idle deadline");
  System.out.println("Parser regression checks PASS: timeout offsets, incomplete frame, RTSP body, invalid marker, idle deadline");
 }
'''+methods+'\n}\n'
    with tempfile.TemporaryDirectory() as tmp:
        f=Path(tmp)/'ParserCheck.java';f.write_text(harness)
        subprocess.run(['javac',str(f)],check=True)
        subprocess.run(['java','-cp',tmp,'ParserCheck'],check=True)
else:
    print('Parser runtime checks require javac; Cloud build executes them before assembling APK')
