from pathlib import Path
import runpy

# v1.7: test the M02S microphone in its required exclusive device mode.
runpy.run_path("tools/prepare_v16.py", run_name="__main__")

def rr(t,o,n,l):
    if o not in t: raise SystemExit(l+" not found")
    return t.replace(o,n,1)

g=Path("app/build.gradle"); s=g.read_text()
s=rr(s,"applicationId 'com.vk.cy01streamlab16'","applicationId 'com.vk.cy01streamlab17'","id")
s=rr(s,"versionCode 1600","versionCode 1700","code")
s=rr(s,"versionName '1.6.0'","versionName '1.7.0'","name"); g.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java"); s=p.read_text()
s=s.replace("CY01 Live v1.6 started","CY01 Live v1.7 started").replace("CY01 Live v1.6","CY01 Live v1.7").replace("CY01StreamLab-OneTap/1.6","CY01StreamLab-OneTap/1.7")
old="""    public static boolean requestBleMicProbe(long durationMs) {
        MainActivityV03 instance = activeInstance;
        if (instance == null || !instance.bleReady) return false;
        instance.startBleMicProbe(durationMs);
        return true;
    }
"""
new="""    public static boolean requestBleMicProbe(long durationMs) {
        MainActivityV03 instance = activeInstance;
        if (instance == null || !instance.bleReady) return false;
        instance.startExclusiveBleMicProbe(durationMs);
        return true;
    }
"""
s=rr(s,old,new,"request")
marker="""    private void startBleMicProbe(long durationMs) {
"""
method="""    private void startExclusiveBleMicProbe(long durationMs) {
        if (!bleReady) {
            log("BLE MIC EXCLUSIVE blocked: BLE channel is not ready");
            return;
        }
        log("BLE MIC EXCLUSIVE: stopping preview mode [02 01 15 01] before speech recognition");
        sendFrame(0x41, new byte[]{0x02, 0x01, 0x15, 0x01});
        main.postDelayed(() -> {
            log("BLE MIC EXCLUSIVE: preview stop settling complete; starting speech recognition");
            startBleMicProbe(durationMs);
        }, 900L);
    }

"""
s=rr(s,marker,method+marker,"exclusive method")
p.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java"); r=p.read_text()
r=r.replace("CY01 LIVE v1.6 started","CY01 LIVE v1.7 started").replace("CY01 LIVE VIDEO v1.6","CY01 LIVE VIDEO v1.7").replace("CY01StreamLab-Raw/1.6","CY01StreamLab-Raw/1.7").replace("CY01 LIVE v1.6 compact report","CY01 LIVE v1.7 compact report")
old="""        startMicCapture(12000L);
        boolean requested = MainActivityV03.requestBleMicProbe(10000L);
"""
new="""        log("MIC TEST v1.7: M02S camera/mic are exclusive; preview will be stopped before BLE speech mode");
        startMicCapture(12000L);
        boolean requested = MainActivityV03.requestBleMicProbe(10000L);
"""
r=rr(r,old,new,"mic note"); p.write_text(r)
print("v1.7 exclusive M02S microphone-mode probe prepared")
