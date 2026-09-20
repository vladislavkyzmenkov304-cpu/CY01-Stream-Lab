from pathlib import Path
import runpy

# Build on v1.4.2: keep video/P2P recovery and add a bounded BLE microphone probe.
runpy.run_path("tools/prepare_v142.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab142'", "applicationId 'com.vk.cy01streamlab15'", "v1.5 applicationId")
s = require_replace(s, "versionCode 1420", "versionCode 1500", "v1.5 versionCode")
s = require_replace(s, "versionName '1.4.2'", "versionName '1.5.0'", "v1.5 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Live v1.4.2 started", "CY01 Live v1.5 started")
s = s.replace("CY01 Live v1.4.2", "CY01 Live v1.5")
s = s.replace("v1.4.2: no explicit Android Network binding", "v1.5: no explicit Android Network binding")
s = s.replace("v1.4.2 will NOT bind sockets", "v1.5 will NOT bind sockets")
s = s.replace("CY01StreamLab-OneTap/1.4.2", "CY01StreamLab-OneTap/1.5")

field = "    private Runnable p2pDiscoveryWatchdog;\n"
field_new = field + '''    private Runnable bleMicStopRunnable;
    private static volatile MainActivityV03 activeInstance;
    public static volatile long bleMicFrameCount;
    public static volatile long bleMicByteCount;
    public static volatile boolean bleMicStartedEvent;
    public static volatile boolean bleMicProbeRunning;
'''
s = require_replace(s, field, field_new, "v1.5 BLE mic fields")

oncreate = '''        super.onCreate(savedInstanceState);
        buildUi();
'''
oncreate_new = '''        super.onCreate(savedInstanceState);
        activeInstance = this;
        buildUi();
'''
s = require_replace(s, oncreate, oncreate_new, "v1.5 active instance")

# Parse BLE microphone packets before the generic 0x41 path.
marker = '''        if (opcode == 0x47 && payload.length > 6) {
            boolean liveReview = (payload[6] & 0x80) != 0;
            log("Capability supportLiveReview=" + liveReview + " (raw flag byte 0x" + String.format(Locale.US, "%02X", payload[6]) + ")");
            return;
        }

        if (opcode != 0x41 || payload.length < 2) return;
'''
insert = '''        if (opcode == 0x47 && payload.length > 6) {
            boolean liveReview = (payload[6] & 0x80) != 0;
            log("Capability supportLiveReview=" + liveReview + " (raw flag byte 0x" + String.format(Locale.US, "%02X", payload[6]) + ")");
            return;
        }

        if (opcode == 0x59) {
            int end = payload.length;
            while (end > 0 && payload[end - 1] == 0) end--;
            if (end > 0) {
                bleMicFrameCount++;
                bleMicByteCount += end;
                if (bleMicFrameCount == 1) {
                    log("BLE MICROPHONE OPUS CONFIRMED: first 0x59 frame bytes=" + end);
                } else if (bleMicFrameCount % 50 == 0) {
                    log("BLE MICROPHONE OPUS frames=" + bleMicFrameCount + " bytes=" + bleMicByteCount);
                }
            }
            return;
        }

        if (opcode == 0x73) {
            if (payload.length >= 2 && (payload[0] & 0xFF) == 0x03 && (payload[1] & 0xFF) == 0x01) {
                bleMicStartedEvent = true;
                log("BLE MICROPHONE START EVENT confirmed: cmd 0x73 payload=03-01");
            }
            return;
        }

        if (opcode != 0x41 || payload.length < 2) return;
'''
s = require_replace(s, marker, insert, "v1.5 BLE mic frame parser")

method_marker = "    private void startOneTapLive() {\n"
methods = '''    public static boolean requestBleMicProbe(long durationMs) {
        MainActivityV03 instance = activeInstance;
        if (instance == null || !instance.bleReady) return false;
        instance.startBleMicProbe(durationMs);
        return true;
    }

    public static void stopBleMicProbeFromRaw() {
        MainActivityV03 instance = activeInstance;
        if (instance != null) instance.stopBleMicProbe();
    }

    private void startBleMicProbe(long durationMs) {
        if (!bleReady) {
            log("BLE MIC TEST blocked: BLE channel is not ready");
            return;
        }
        if (bleMicStopRunnable != null) main.removeCallbacks(bleMicStopRunnable);
        bleMicFrameCount = 0L;
        bleMicByteCount = 0L;
        bleMicStartedEvent = false;
        bleMicProbeRunning = true;
        log("BLE MIC TEST: starting source-derived speech-recognition mode [02 01 07] for "
                + durationMs + " ms; keep speaking during the test");
        sendFrame(0x41, new byte[]{0x02, 0x01, 0x07});
        bleMicStopRunnable = () -> stopBleMicProbe();
        main.postDelayed(bleMicStopRunnable, Math.max(3000L, durationMs));
    }

    private void stopBleMicProbe() {
        if (bleMicStopRunnable != null) {
            main.removeCallbacks(bleMicStopRunnable);
            bleMicStopRunnable = null;
        }
        if (bleMicProbeRunning && bleReady) {
            log("BLE MIC TEST: stopping speech-recognition mode [02 01 0B]");
            sendFrame(0x41, new byte[]{0x02, 0x01, 0x0B});
        }
        bleMicProbeRunning = false;
        log("BLE MIC TEST result: startedEvent=" + bleMicStartedEvent
                + " opusFrames=" + bleMicFrameCount + " opusBytes=" + bleMicByteCount);
    }

'''
s = require_replace(s, method_marker, methods + method_marker, "v1.5 BLE mic methods")

destroy_marker = '''    @Override
    protected void onDestroy() {
'''
destroy_new = '''    @Override
    protected void onDestroy() {
        if (bleMicStopRunnable != null) main.removeCallbacks(bleMicStopRunnable);
        if (activeInstance == this) activeInstance = null;
'''
s = require_replace(s, destroy_marker, destroy_new, "v1.5 mic cleanup")


activity.write_text(s)

raw = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = raw.read_text()
r = r.replace("CY01 LIVE v1.4.2 started", "CY01 LIVE v1.5 started")
r = r.replace("CY01 LIVE VIDEO v1.4.2", "CY01 LIVE VIDEO v1.5")
r = r.replace("CY01StreamLab-Raw/1.4.2", "CY01StreamLab-Raw/1.5")
r = r.replace("CY01 LIVE v1.4.2 compact report", "CY01 LIVE v1.5 compact report")

button_old = '''        root.addView(button("COPY RAW LOG", v -> copyLog()));
        root.addView(button("PLAY MIC SAMPLE", v -> playMicSample()));
        root.addView(button("STOP RAW TEST", v -> stopRawTest()));
'''
button_new = '''        root.addView(button("COPY RAW LOG", v -> copyLog()));
        root.addView(button("START MIC TEST 10s", v -> startCombinedMicTest()));
        root.addView(button("PLAY MIC SAMPLE", v -> playMicSample()));
        root.addView(button("STOP RAW TEST", v -> stopRawTest()));
'''
r = require_replace(r, button_old, button_new, "v1.5 mic test button")

# Do not start a capture that can never finish before the user explicitly starts the mic test.
play_old = '''            if (audioTrackReady) {
                startMicCapture(12000L);
                log("MIC TEST armed: speak normally for the first ~10 seconds; 12-second AAC sample will be saved automatically");
            }
            status(audioTrackReady
                    ? "LIVE video + microphone track2. Speak for 10 s, then tap PLAY MIC SAMPLE."
                    : "PLAY accepted. Video only; microphone track2 SETUP failed.");
'''
play_new = '''            if (audioTrackReady) {
                log("MIC TEST ready: RTSP track2 SETUP succeeded but capture waits for START MIC TEST 10s");
            }
            status(audioTrackReady
                    ? "LIVE ready. Tap START MIC TEST 10s, speak continuously, then inspect/play sample."
                    : "PLAY accepted. Video only; microphone track2 SETUP failed.");
'''
r = require_replace(r, play_old, play_new, "v1.5 explicit mic start")

# Make AAC capture close on a timer even when no audio RTP arrives.
start_capture_old = '''            micSampleOut = new FileOutputStream(micSampleFile, false);
            micCaptureDeadlineMs = System.currentTimeMillis() + durationMs;
            micSampleBytes = 0L;
            log("MIC CAPTURE started: " + micSampleFile.getAbsolutePath() + " durationMs=" + durationMs);
'''
start_capture_new = '''            micSampleOut = new FileOutputStream(micSampleFile, false);
            micCaptureDeadlineMs = System.currentTimeMillis() + durationMs;
            micSampleBytes = 0L;
            log("MIC CAPTURE started: " + micSampleFile.getAbsolutePath() + " durationMs=" + durationMs);
            main.postDelayed(() -> {
                if (micSampleOut != null && System.currentTimeMillis() >= micCaptureDeadlineMs) {
                    closeMicCapture();
                    log("MIC CAPTURE timer complete: audioRTP=" + audioRtpPacketCount
                            + " audioAAC=" + audioAacFrameCount + " sampleBytes=" + micSampleBytes);
                    status(micSampleBytes > 0
                            ? "Mic AAC sample captured. Tap PLAY MIC SAMPLE."
                            : "No RTSP mic audio captured; check BLE OPUS counters in compact report.");
                }
            }, durationMs + 250L);
'''
r = require_replace(r, start_capture_old, start_capture_new, "v1.5 independent mic capture timer")

marker2 = '''    private void startMicCapture(long durationMs) {
'''
combined = '''    private void startCombinedMicTest() {
        if (!running || sessionId == null) {
            log("START MIC TEST blocked: RTSP live session is not running");
            return;
        }
        if (MainActivityV03.bleMicProbeRunning) {
            log("START MIC TEST blocked: BLE microphone probe already running");
            return;
        }
        startMicCapture(12000L);
        boolean requested = MainActivityV03.requestBleMicProbe(10000L);
        log("MIC TEST trigger: BLE speech-recognition command requested=" + requested
                + "; watching both RTSP track2 AAC and BLE cmd 0x59 OPUS");
        status(requested
                ? "MIC TEST running: speak continuously for 10 seconds."
                : "MIC TEST: BLE trigger unavailable; watching RTSP track2 only.");
    }

'''
r = require_replace(r, marker2, combined + marker2, "v1.5 combined mic method")

report_old = '''                        + "audioRTP=%d audioAAC=%d audioBytes=%d micSampleBytes=%d\n"
                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d decoderRecoveries=%d\n\n",
'''
report_new = '''                        + "audioRTP=%d audioAAC=%d audioBytes=%d micSampleBytes=%d\n"
                        + "bleMicStarted=%s bleOpusFrames=%d bleOpusBytes=%d\n"
                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d decoderRecoveries=%d\n\n",
'''
r = require_replace(r, report_old, report_new, "v1.5 report BLE mic fields")

args_old = '''                audioRtpPacketCount, audioAacFrameCount, audioAacByteCount, micSampleBytes,
                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount);
'''
args_new = '''                audioRtpPacketCount, audioAacFrameCount, audioAacByteCount, micSampleBytes,
                MainActivityV03.bleMicStartedEvent, MainActivityV03.bleMicFrameCount, MainActivityV03.bleMicByteCount,
                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount);
'''
r = require_replace(r, args_old, args_new, "v1.5 report BLE mic args")

stop_old = '''    private void stopRawTest() {
        closeMicCapture();
        stopMicPlayback();
        running = false;
'''
stop_new = '''    private void stopRawTest() {
        closeMicCapture();
        stopMicPlayback();
        MainActivityV03.stopBleMicProbeFromRaw();
        running = false;
'''
r = require_replace(r, stop_old, stop_new, "v1.5 stop BLE mic")

raw.write_text(r)
print("v1.5 bounded BLE microphone + RTSP audio test preparation complete")
