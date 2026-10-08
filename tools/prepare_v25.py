from pathlib import Path
import runpy

# v2.5: field fix for RTSP-over-TCP parser. CY01 may emit ASCII RTSP control
# messages between interleaved RTP frames; v2.4 treated the first 'R'/'M' as fatal.
runpy.run_path("tools/prepare_v24_impl.py", run_name="__main__")

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
p.write_text(r)
print("v2.5 prepared: RTSP control/data multiplex parser")
