from pathlib import Path

def rr(t, o, n, label, count=1):
    if o not in t:
        raise SystemExit(label + " not found")
    return t.replace(o, n, count)

g = Path("app/build.gradle")
s = g.read_text()
s = rr(s, "applicationId 'com.vk.cy01streamlab19'", "applicationId 'com.vk.cy01streamlab20'", "app id")
s = rr(s, "versionCode 1900", "versionCode 2000", "version code")
s = rr(s, "versionName '1.9.0'", "versionName '2.0.0'", "version name")
g.write_text(s)

p = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = p.read_text()
s = s.replace("CY01 Live v1.9 started", "CY01 Live v2.0 started")
s = s.replace("CY01 Live v1.9", "CY01 Live v2.0")
s = s.replace("CY01StreamLab-OneTap/1.9", "CY01StreamLab-OneTap/2.0")
s = s.replace("v1.9: no explicit Android Network binding", "v2.0: no explicit Android Network binding")
s = s.replace("v1.9 will NOT bind sockets", "v2.0 will NOT bind sockets")

field = "    private static volatile MainActivityV03 activeInstance;\n"
field_new = field + """    public static volatile boolean cameraRecoveryRequested;
    public static volatile boolean cameraRecoveryReady;
    public static volatile String cameraRecoveryIp;
"""
s = rr(s, field, field_new, "camera recovery fields")

marker = "    public static boolean requestBleMicProbe(long durationMs) {\n"
methods = """    public static boolean requestCameraRecoveryAfterMic() {
        MainActivityV03 instance = activeInstance;
        if (instance == null || !instance.bleReady) return false;
        instance.recoverCameraAfterMic();
        return true;
    }

    public static boolean consumeCameraRecoveryReady() {
        if (!cameraRecoveryReady) return false;
        cameraRecoveryReady = false;
        return true;
    }

    private void recoverCameraAfterMic() {
        if (!bleReady) {
            log("MIC->CAMERA recovery blocked: BLE channel is not ready");
            return;
        }
        cameraRecoveryRequested = true;
        cameraRecoveryReady = false;
        cameraRecoveryIp = null;
        oneTapLiveRequested = true;
        oneTapLaunchInProgress = false;
        oneTapRearmSent = false;
        log("MIC->CAMERA recovery: rebuilding preview -> P2P -> current IP -> /ch0 before RTSP restart");

        Runnable restart = () -> {
            resetP2pState();
            if (!bleReady) {
                cameraRecoveryRequested = false;
                log("MIC->CAMERA recovery aborted: BLE dropped before preview re-arm");
                return;
            }
            startLiveTest();
        };

        if (p2pManager == null || p2pChannel == null) {
            main.post(restart);
            return;
        }
        p2pManager.removeGroup(p2pChannel, new WifiP2pManager.ActionListener() {
            @Override public void onSuccess() {
                log("MIC->CAMERA recovery: stale P2P group removed");
                main.postDelayed(restart, 300L);
            }
            @Override public void onFailure(int reason) {
                log("MIC->CAMERA recovery: removeGroup=" + p2pReason(reason)
                        + " (" + reason + "); continuing with clean state");
                main.postDelayed(restart, 300L);
            }
        });
    }

"""
s = rr(s, marker, methods + marker, "camera recovery methods")

launch_marker = """        log("ONE-TAP /ch0 READY: " + reason);
        log("ONE-TAP launching raw RTP/H.264 decoder with AUTO_START=true");
"""
launch_new = """        if (cameraRecoveryRequested) {
            cameraRecoveryRequested = false;
            cameraRecoveryIp = glassesIp;
            cameraRecoveryReady = true;
            oneTapLiveRequested = false;
            oneTapLaunchInProgress = false;
            log("MIC->CAMERA recovery READY: P2P route and /ch0 DESCRIBE confirmed at "
                    + (cameraRecoveryIp == null ? "unknown" : cameraRecoveryIp));
            status("LIVE recovery ready; returning control to video session");
            return;
        }
        log("ONE-TAP /ch0 READY: " + reason);
        log("ONE-TAP launching raw RTP/H.264 decoder with AUTO_START=true");
"""
s = rr(s, launch_marker, launch_new, "recovery ready gate")
p.write_text(s)

p = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = p.read_text()
r = r.replace("CY01 LIVE v1.9 started", "CY01 LIVE v2.0 started")
r = r.replace("CY01 LIVE VIDEO v1.9", "CY01 LIVE VIDEO v2.0")
r = r.replace("CY01StreamLab-Raw/1.9", "CY01StreamLab-Raw/2.0")
r = r.replace("CY01 LIVE v1.9 compact report", "CY01 LIVE v2.0 compact report")
r = r.replace("MIC TEST v1.9:", "MIC TEST v2.0:")

field = "    private long lastStatsDecodedCount;\n"
field_new = field + """    private long lastVideoRtpArrivalMs;
    private long maxVideoRtpGapMs;
    private long videoRtpGapOver100Count;
    private long lastRenderedFrameMs;
    private long maxRenderedFrameGapMs;
    private long renderedGapOver100Count;
    private long renderedStallOver250Count;
    private String previousGoodSession = "";
    private boolean cameraRecoveryPollActive;
    private long cameraRecoveryDeadlineMs;
"""
r = rr(r, field, field_new, "smoothness fields")

reset = "        lastStatsDecodedCount = 0L;\n"
reset_new = reset + """        lastVideoRtpArrivalMs = 0L;
        maxVideoRtpGapMs = 0L;
        videoRtpGapOver100Count = 0L;
        lastRenderedFrameMs = 0L;
        maxRenderedFrameGapMs = 0L;
        renderedGapOver100Count = 0L;
        renderedStallOver250Count = 0L;
"""
r = rr(r, reset, reset_new, "smoothness reset")

rtp_marker = """        rtpPacketCount++;
        rtpPayloadByteCount += (end - off);
"""
rtp_new = """        long rtpArrivalMs = System.currentTimeMillis();
        if (lastVideoRtpArrivalMs > 0L) {
            long gap = Math.max(0L, rtpArrivalMs - lastVideoRtpArrivalMs);
            if (gap > maxVideoRtpGapMs) maxVideoRtpGapMs = gap;
            if (gap >= 100L) videoRtpGapOver100Count++;
        }
        lastVideoRtpArrivalMs = rtpArrivalMs;
        rtpPacketCount++;
        rtpPayloadByteCount += (end - off);
"""
r = rr(r, rtp_marker, rtp_new, "RTP gap metrics")

render_marker = """            codec.setOnFrameRenderedListener((mc, presentationTimeUs, nanoTime) -> {
                if (!firstRendered) {
"""
render_new = """            codec.setOnFrameRenderedListener((mc, presentationTimeUs, nanoTime) -> {
                long renderedNow = System.currentTimeMillis();
                if (lastRenderedFrameMs > 0L) {
                    long gap = Math.max(0L, renderedNow - lastRenderedFrameMs);
                    if (gap > maxRenderedFrameGapMs) maxRenderedFrameGapMs = gap;
                    if (gap >= 100L) renderedGapOver100Count++;
                    if (gap >= 250L) renderedStallOver250Count++;
                }
                lastRenderedFrameMs = renderedNow;
                if (!firstRendered) {
"""
r = rr(r, render_marker, render_new, "render gap metrics")

old_recovery = """                    micTransitionExpected = false;
                    main.postDelayed(() -> {
                        if (!running) {
                            log("MIC TEST: attempting automatic RTSP camera recovery after BLE preview restore");
                            startRawTest();
                        }
                    }, 1800L);
"""
new_recovery = """                    micTransitionExpected = false;
                    boolean recoveryRequested = MainActivityV03.requestCameraRecoveryAfterMic();
                    log("MIC TEST: full camera recovery requested=" + recoveryRequested);
                    if (recoveryRequested) {
                        log("MIC TEST: route rebuild delegated to main activity");
                    } else {
                        status("Camera recovery unavailable; copy report.");
                    }
"""
r = rr(r, old_recovery, new_recovery, "full camera recovery")

marker = "    private void startMicCapture(long durationMs) {\n"
helpers = """    private void preserveGoodSessionSummary() {
        if (!firstRendered || decodedOutputCount <= 0) return;
        long now = System.currentTimeMillis();
        double seconds = streamStartMs > 0L ? Math.max(0.001, (now - streamStartMs) / 1000.0) : 0.0;
        double fps = seconds > 0.0 ? decodedOutputCount / seconds : 0.0;
        previousGoodSession = String.format(Locale.US,
                "rendered=%s duration=%.1fs RTP=%d AU=%d decoded=%d avgFPS=%.1f",
                firstRendered, seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps);
    }

"""
r = rr(r, marker, helpers + marker, "preserve good-session helper")

p.write_text(r)
print("v2.0 good-session preservation preparation complete")
