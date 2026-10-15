from pathlib import Path
import runpy

# v1.9: preserve stable v1.8 video and make camera -> mic -> camera an explicit transition.
runpy.run_path("tools/prepare_v18.py", run_name="__main__")

def rr(t,o,n,l):
    if o not in t: raise SystemExit(l+" not found")
    return t.replace(o,n,1)

g=Path("app/build.gradle"); s=g.read_text()
s=rr(s,"applicationId 'com.vk.cy01streamlab18'","applicationId 'com.vk.cy01streamlab19'","id")
s=rr(s,"versionCode 1800","versionCode 1900","code")
s=rr(s,"versionName '1.8.0'","versionName '1.9.0'","name"); g.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java"); s=p.read_text()
s=s.replace("CY01 Live v1.8 started","CY01 Live v1.9 started").replace("CY01 Live v1.8","CY01 Live v1.9").replace("CY01StreamLab-OneTap/1.8","CY01StreamLab-OneTap/1.9")
s=s.replace("v1.8: no explicit Android Network binding","v1.9: no explicit Android Network binding").replace("v1.8 will NOT bind sockets","v1.9 will NOT bind sockets")

old="""        if (opcode == 0x73) {
            if (payload.length >= 2 && (payload[0] & 0xFF) == 0x03 && (payload[1] & 0xFF) == 0x01) {
                bleMicStartedEvent = true;
                log("BLE MICROPHONE START EVENT confirmed: cmd 0x73 payload=03-01");
            }
            return;
        }
"""
new="""        if (opcode == 0x73) {
            log("BLE DATA REPORTING 0x73 payload=" + hex(payload)
                    + " micProbeRunning=" + bleMicProbeRunning);
            if (payload.length >= 2 && (payload[0] & 0xFF) == 0x03 && (payload[1] & 0xFF) == 0x01) {
                bleMicStartedEvent = true;
                log("BLE MICROPHONE START EVENT confirmed: cmd 0x73 payload=03-01");
            }
            return;
        }
"""
s=rr(s,old,new,"73 logging")

old="""        bleMicProbeRunning = false;
        log("BLE MIC TEST result: gattQueued=" + bleMicGattQueued
"""
new="""        bleMicProbeRunning = false;
        log("BLE MIC TEST result: gattQueued=" + bleMicGattQueued
"""
# keep exact stop point, then append preview restore after result log block
needle="""                + " startedEvent=" + bleMicStartedEvent
                + " opusFrames=" + bleMicFrameCount + " opusBytes=" + bleMicByteCount);
    }
"""
replacement="""                + " startedEvent=" + bleMicStartedEvent
                + " opusFrames=" + bleMicFrameCount + " opusBytes=" + bleMicByteCount);
        if (bleReady) {
            log("BLE MIC TEST complete: restoring camera preview [02 01 14 01]");
            sendFrame(0x41, new byte[]{0x02, 0x01, 0x14, 0x01});
        }
    }
"""
s=rr(s,needle,replacement,"preview restore")
p.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java"); r=p.read_text()
r=r.replace("CY01 LIVE v1.8 started","CY01 LIVE v1.9 started").replace("CY01 LIVE VIDEO v1.8","CY01 LIVE VIDEO v1.9").replace("CY01StreamLab-Raw/1.8","CY01StreamLab-Raw/1.9").replace("CY01 LIVE v1.8 compact report","CY01 LIVE v1.9 compact report").replace("MIC TEST v1.8:","MIC TEST v1.9:")
field="""    private volatile boolean running;
"""
field_new=field+"""    private volatile boolean micTransitionExpected;
"""
r=rr(r,field,field_new,"transition field")
old="""        log("MIC TEST v1.9: M02S camera/mic are exclusive; preview will be stopped before BLE speech mode");
        startMicCapture(12000L);
"""
new="""        log("MIC TEST v1.9: M02S camera/mic are exclusive; RTSP EOF is expected during BLE mic window");
        micTransitionExpected = true;
        startMicCapture(12000L);
"""
r=rr(r,old,new,"expected transition")
# Keep the BLE probe alive when RTSP ends; mark EOF as expected in diagnostics.
old="""        } catch (Exception e) {
            log("RAW SESSION ERROR: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally {
"""
new="""        } catch (Exception e) {
            if (micTransitionExpected) {
                log("RAW SESSION TRANSITION: RTSP closed during microphone mode as expected: "
                        + e.getClass().getSimpleName() + ": " + e.getMessage());
            } else {
                log("RAW SESSION ERROR: " + e.getClass().getSimpleName() + ": " + e.getMessage());
            }
        } finally {
"""
r=rr(r,old,new,"expected EOF")
# After the 12 s capture timer, clear transition and automatically attempt raw video again after preview restore.
needle="""                    status(micSampleBytes > 0
                            ? "Mic AAC sample captured. Tap PLAY MIC SAMPLE."
                            : "No RTSP mic audio captured; check BLE OPUS counters in compact report.");
                }
            }, durationMs + 250L);
"""
replacement="""                    status(micSampleBytes > 0
                            ? "Mic AAC sample captured. Restoring camera."
                            : "Mic window complete; restoring camera and preserving BLE diagnostics.");
                    micTransitionExpected = false;
                    main.postDelayed(() -> {
                        if (!running) {
                            log("MIC TEST: attempting automatic RTSP camera recovery after BLE preview restore");
                            startRawTest();
                        }
                    }, 1800L);
                }
            }, durationMs + 250L);
"""
r=rr(r,needle,replacement,"auto camera recovery")
p.write_text(r)
print("v1.9 camera-mic-camera transition preparation complete")
