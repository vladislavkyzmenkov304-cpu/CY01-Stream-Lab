from pathlib import Path
import runpy

# v2.3: prioritize stream smoothness. The field logs show false resyncs inside
# valid interleaved RTP causing byte loss, AU starvation and decoder stalls.
runpy.run_path("tools/prepare_v22.py", run_name="__main__")

def rr(t,o,n,l):
    if o not in t: raise SystemExit(l+" not found")
    return t.replace(o,n,1)

g=Path("app/build.gradle"); s=g.read_text()
s=rr(s,"applicationId 'com.vk.cy01streamlab22'","applicationId 'com.vk.cy01streamlab23'","id")
s=rr(s,"versionCode 2200","versionCode 2300","code")
s=rr(s,"versionName '2.2.0'","versionName '2.3.0'","name"); g.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java"); s=p.read_text()
s=s.replace("CY01 Live v2.2 started","CY01 Live v2.3 started").replace("CY01 Live v2.2","CY01 Live v2.3").replace("CY01StreamLab-OneTap/2.2","CY01StreamLab-OneTap/2.3")
s=s.replace("v2.2: no explicit Android Network binding","v2.3: no explicit Android Network binding").replace("v2.2 will NOT bind sockets","v2.3 will NOT bind sockets")
p.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java"); r=p.read_text()
r=r.replace("CY01 LIVE v2.2 started","CY01 LIVE v2.3 started").replace("CY01 LIVE VIDEO v2.2","CY01 LIVE VIDEO v2.3").replace("CY01StreamLab-Raw/2.2","CY01StreamLab-Raw/2.3").replace("CY01 LIVE v2.2 compact report","CY01 LIVE v2.3 compact report").replace("MIC TEST v2.2:","MIC TEST v2.3:")

# Disable byte-scanning resync inside an established RTSP interleaved stream.
# A TCP read may split anywhere, but framing remains: '$', channel, uint16 length, exact payload.
old='''                if (marker != '$') {
                    long skipped = 1L;
                    int next;
                    while ((next = in.read()) >= 0 && next != '$') skipped++;
                    if (next < 0) throw new EOFException("RTSP/RTP socket closed during resync");
                    interleavedResyncBytes += skipped;
                    if (interleavedResyncBytes <= 65536L) {
                        log("RTSP interleaved resync: skipped binary/non-framed bytes=" + skipped
                                + " total=" + interleavedResyncBytes);
                    }
                    marker = next;
                }
'''
new='''                if (marker != '$') {
                    throw new IOException("RTSP interleaved framing lost: marker=0x"
                            + Integer.toHexString(marker & 0xFF)
                            + "; refusing destructive byte-scan resync");
                }
'''
r=rr(r,old,new,"remove destructive resync")

# Avoid repeated codec teardown/recreate on transient gaps. Field logs show RTP/AU
# continues while decoder stalls; wait for an IDR before escalating.
old='''            if (decoderConfigured && lastDecoderOutputMs > 0
                    && now - lastDecoderOutputMs >= DECODER_STALL_MS
                    && rtpPacketCount > lastRecoveryRtpCount + 8) {
                decoderRecoveryCount++;
                log("DECODER STALL detected: no output for " + (now - lastDecoderOutputMs)
                        + " ms while RTP/access units continue; recovery #" + decoderRecoveryCount);
                lastRecoveryRtpCount = rtpPacketCount;
                recoverDecoder();
            }
'''
new='''            if (decoderConfigured && lastDecoderOutputMs > 0
                    && now - lastDecoderOutputMs >= DECODER_STALL_MS
                    && rtpPacketCount > lastRecoveryRtpCount + 8) {
                decoderRecoveryCount++;
                log("DECODER STALL observed: no output for " + (now - lastDecoderOutputMs)
                        + " ms while RTP/access units continue; waiting for next in-band IDR before codec reset #"
                        + decoderRecoveryCount);
                lastRecoveryRtpCount = rtpPacketCount;
                waitingForRecoveryIdr = true;
            }
'''
r=rr(r,old,new,"defer codec reset")

# On next IDR, reset only if output still stalled; otherwise clear the transient.
old='''        if (nalType == 5) {
            nalCounts[5]++;
'''
new='''        if (nalType == 5) {
            nalCounts[5]++;
            if (waitingForRecoveryIdr) {
                long gap = System.currentTimeMillis() - lastDecoderOutputMs;
                waitingForRecoveryIdr = false;
                if (decoderConfigured && gap >= DECODER_STALL_MS) {
                    log("DECODER RECOVERY: stalled through IDR; reconfiguring codec at clean keyframe");
                    recoverDecoder();
                } else {
                    log("DECODER STALL cleared before IDR; codec reset avoided");
                }
            }
'''
r=rr(r,old,new,"IDR gated recovery")

field='''    private long decoderRecoveryCount;
'''
field_new=field+'''    private volatile boolean waitingForRecoveryIdr;
'''
r=rr(r,field,field_new,"recovery idr field")
reset='''        decoderRecoveryCount = 0L;
'''
reset_new=reset+'''        waitingForRecoveryIdr = false;
'''
r=rr(r,reset,reset_new,"reset recovery idr")
p.write_text(r)
print("v2.3 smoothness-first transport/decoder preparation complete")
