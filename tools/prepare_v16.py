from pathlib import Path
import runpy

# Build on v1.5 and add decisive BLE/GATT microphone diagnostics.
runpy.run_path("tools/prepare_v15.py", run_name="__main__")

def rr(text, old, new, label):
    if old not in text:
        raise SystemExit(label + " not found")
    return text.replace(old, new, 1)

gradle=Path("app/build.gradle")
s=gradle.read_text()
s=rr(s,"applicationId 'com.vk.cy01streamlab15'","applicationId 'com.vk.cy01streamlab16'","app id")
s=rr(s,"versionCode 1500","versionCode 1600","version code")
s=rr(s,"versionName '1.5.0'","versionName '1.6.0'","version name")
gradle.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s=p.read_text()
s=s.replace("CY01 Live v1.5 started","CY01 Live v1.6 started").replace("CY01 Live v1.5","CY01 Live v1.6").replace("CY01StreamLab-OneTap/1.5","CY01StreamLab-OneTap/1.6")
old="""    public static volatile boolean bleMicProbeRunning;
"""
new=old+"""    public static volatile boolean bleMicGattQueued;
    public static volatile long bleMicRxNotificationCount;
    public static volatile int bleMicLastOpcode = -1;
"""
s=rr(s,old,new,"diag fields")
old="""    private synchronized void handleRx(byte[] chunk) {
        if (chunk == null || chunk.length == 0) return;
"""
new="""    private synchronized void handleRx(byte[] chunk) {
        if (chunk == null || chunk.length == 0) return;
        if (bleMicProbeRunning) bleMicRxNotificationCount++;
"""
s=rr(s,old,new,"rx counter")
old="""        int opcode = frame[1] & 0xFF;
        int payloadLen = le16(frame, 2);
"""
new="""        int opcode = frame[1] & 0xFF;
        if (bleMicProbeRunning) bleMicLastOpcode = opcode;
        int payloadLen = le16(frame, 2);
"""
s=rr(s,old,new,"opcode counter")
old="""        bleMicStartedEvent = false;
        bleMicProbeRunning = true;
"""
new="""        bleMicStartedEvent = false;
        bleMicGattQueued = false;
        bleMicRxNotificationCount = 0L;
        bleMicLastOpcode = -1;
        bleMicProbeRunning = true;
"""
s=rr(s,old,new,"diag reset")
old="""        sendFrame(0x41, new byte[]{0x02, 0x01, 0x07});
        bleMicStopRunnable = () -> stopBleMicProbe();
"""
new="""        bleMicGattQueued = sendFrameChecked(0x41, new byte[]{0x02, 0x01, 0x07});
        log("BLE MIC TEST start GATT queued=" + bleMicGattQueued);
        bleMicStopRunnable = () -> stopBleMicProbe();
"""
s=rr(s,old,new,"checked start")
marker="""    private byte[] buildFrame(int opcode, byte[] payload) {
"""
method="""    private boolean sendFrameChecked(int opcode, byte[] payload) {
        if (!bleReady || gatt == null || writeChar == null) {
            log("BLE checked TX blocked: channel not ready");
            return false;
        }
        byte[] frame = buildFrame(opcode, payload);
        writeChar.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE);
        writeChar.setValue(frame);
        boolean queued = gatt.writeCharacteristic(writeChar);
        log("TX-CHECKED " + hex(frame) + " queued=" + queued);
        return queued;
    }

"""
s=rr(s,marker,method+marker,"checked method")
old="""        log("BLE MIC TEST result: startedEvent=" + bleMicStartedEvent
                + " opusFrames=" + bleMicFrameCount + " opusBytes=" + bleMicByteCount);
"""
new="""        log("BLE MIC TEST result: gattQueued=" + bleMicGattQueued
                + " rxNotifications=" + bleMicRxNotificationCount
                + " lastOpcode=" + (bleMicLastOpcode < 0 ? "none" : String.format(Locale.US, "0x%02X", bleMicLastOpcode))
                + " startedEvent=" + bleMicStartedEvent
                + " opusFrames=" + bleMicFrameCount + " opusBytes=" + bleMicByteCount);
"""
s=rr(s,old,new,"result diag")
p.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r=p.read_text()
r=r.replace("CY01 LIVE v1.5 started","CY01 LIVE v1.6 started").replace("CY01 LIVE VIDEO v1.5","CY01 LIVE VIDEO v1.6").replace("CY01StreamLab-Raw/1.5","CY01StreamLab-Raw/1.6").replace("CY01 LIVE v1.5 compact report","CY01 LIVE v1.6 compact report")
old="""                        + "bleMicStarted=%s bleOpusFrames=%d bleOpusBytes=%d\\n"
                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d decoderRecoveries=%d\\n\\n",
"""
new="""                        + "bleGattQueued=%s bleRxNotifications=%d bleLastOpcode=%s\\n"
                        + "bleMicStarted=%s bleOpusFrames=%d bleOpusBytes=%d\\n"
                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d decoderRecoveries=%d\\n\\n",
"""
r=rr(r,old,new,"report labels")
old="""                MainActivityV03.bleMicStartedEvent, MainActivityV03.bleMicFrameCount, MainActivityV03.bleMicByteCount,
                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount);
"""
new="""                MainActivityV03.bleMicGattQueued, MainActivityV03.bleMicRxNotificationCount,
                MainActivityV03.bleMicLastOpcode < 0 ? "none" : String.format(Locale.US, "0x%02X", MainActivityV03.bleMicLastOpcode),
                MainActivityV03.bleMicStartedEvent, MainActivityV03.bleMicFrameCount, MainActivityV03.bleMicByteCount,
                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount);
"""
r=rr(r,old,new,"report args")
p.write_text(r)
print("v1.6 decisive BLE microphone diagnostics prepared")
