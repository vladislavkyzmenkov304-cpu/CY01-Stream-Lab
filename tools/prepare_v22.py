from pathlib import Path
import runpy

# v2.2: make mic lifecycle single-shot and recover camera without prematurely clearing recovery state.
runpy.run_path("tools/prepare_v21.py", run_name="__main__")

def rr(t,o,n,l):
    if o not in t: raise SystemExit(l+" not found")
    return t.replace(o,n,1)

g=Path("app/build.gradle"); s=g.read_text()
s=rr(s,"applicationId 'com.vk.cy01streamlab21'","applicationId 'com.vk.cy01streamlab22'","id")
s=rr(s,"versionCode 2100","versionCode 2200","code")
s=rr(s,"versionName '2.1.0'","versionName '2.2.0'","name"); g.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java"); s=p.read_text()
s=s.replace("CY01 Live v2.1 started","CY01 Live v2.2 started").replace("CY01 Live v2.1","CY01 Live v2.2").replace("CY01StreamLab-OneTap/2.1","CY01StreamLab-OneTap/2.2")
s=s.replace("v2.1: no explicit Android Network binding","v2.2: no explicit Android Network binding").replace("v2.1 will NOT bind sockets","v2.2 will NOT bind sockets")

# prepare_v21 already keeps cameraRecoveryRequested asserted through the P2P rebuild.
# Do not patch that state a second time here.

# Single-shot mic completion: ignore stale/manual duplicate stop calls after the first completion.
marker="""    private void stopBleMicProbe() {
"""
replacement="""    private void stopBleMicProbe() {
        if (!bleMicProbeRunning && bleMicStopRunnable == null) {
            return;
        }
"""
s=rr(s,marker,replacement,"single shot mic stop")

# Do not send camera preview directly from mic-stop. Recovery owner is the v2.x state machine.
old="""        if (bleReady) {
            log("BLE MIC TEST complete: restoring camera preview [02 01 14 01]");
            sendFrame(0x41, new byte[]{0x02, 0x01, 0x14, 0x01});
        }
"""
new="""        log("BLE MIC TEST complete: camera restore is owned by MIC->CAMERA recovery state machine");
"""
s=rr(s,old,new,"single recovery owner")
p.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java"); r=p.read_text()
r=r.replace("CY01 LIVE v2.1 started","CY01 LIVE v2.2 started").replace("CY01 LIVE VIDEO v2.1","CY01 LIVE VIDEO v2.2").replace("CY01StreamLab-Raw/2.1","CY01StreamLab-Raw/2.2").replace("CY01 LIVE v2.1 compact report","CY01 LIVE v2.2 compact report").replace("MIC TEST v2.1:","MIC TEST v2.2:")
p.write_text(r)
print("v2.2 single-shot mic and recovery-state fix prepared")
