from pathlib import Path
import runpy

runpy.run_path("tools/prepare_v20.py", run_name="__main__")


def rr(text, old, new, label, count=1):
    if old not in text:
        raise SystemExit(label + " not found")
    return text.replace(old, new, count)


g = Path("app/build.gradle")
s = g.read_text()
s = rr(s, "applicationId 'com.vk.cy01streamlab20'", "applicationId 'com.vk.cy01streamlab21'", "v2.1 app id")
s = rr(s, "versionCode 2000", "versionCode 2100", "v2.1 version code")
s = rr(s, "versionName '2.0.0'", "versionName '2.1.0'", "v2.1 version name")
g.write_text(s)

p = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = p.read_text()
s = s.replace("CY01 Live v2.0 started", "CY01 Live v2.1 started")
s = s.replace("CY01 Live v2.0", "CY01 Live v2.1")
s = s.replace("CY01StreamLab-OneTap/2.0", "CY01StreamLab-OneTap/2.1")
s = s.replace("v2.0: no explicit Android Network binding", "v2.1: no explicit Android Network binding")
s = s.replace("v2.0 will NOT bind sockets", "v2.1 will NOT bind sockets")

s = rr(s,
"""            cameraRecoveryRequested = false;
            startLiveTest();
""",
"""            log("MIC->CAMERA recovery: preview/P2P rebuild starting; waiting for fresh /ch0 readiness");
            startLiveTest();
""",
"keep camera recovery request asserted")

s = rr(s,
"""        Intent intent = new Intent(MainActivityV03.this, RawRtspH264Activity.class);
        intent.putExtra("AUTO_START", true);
        intent.putExtra("ONE_TAP", true);
""",
"""        Intent intent = new Intent(MainActivityV03.this, RawRtspH264Activity.class);
        intent.putExtra("AUTO_START", true);
        intent.putExtra("ONE_TAP", true);
        intent.putExtra("RTSP_HOST", glassesIp != null ? glassesIp : "192.168.49.96");
""",
"pass current RTSP host")
p.write_text(s)

p = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = p.read_text()
r = r.replace("CY01 LIVE v2.0 started", "CY01 LIVE v2.1 started")
r = r.replace("CY01 LIVE VIDEO v2.0", "CY01 LIVE VIDEO v2.1")
r = r.replace("CY01StreamLab-Raw/2.0", "CY01StreamLab-Raw/2.1")
r = r.replace("CY01 LIVE v2.0 compact report", "CY01 LIVE v2.1 compact report")
r = r.replace("MIC TEST v2.0:", "MIC TEST v2.1:")

r = rr(r,
"""    private static final String HOST = "192.168.49.96";
    private static final int PORT = 8554;
    private static final String BASE_URI = "rtsp://" + HOST + ":" + PORT + "/ch0";
""",
"""    private static final String DEFAULT_HOST = "192.168.49.96";
    private static final int PORT = 8554;
    private String rtspHost = DEFAULT_HOST;
    private String baseUri = "rtsp://" + DEFAULT_HOST + ":" + PORT + "/ch0";
""",
"dynamic RTSP host fields")
r = r.replace("new InetSocketAddress(HOST, PORT)", "new InetSocketAddress(rtspHost, PORT)")
r = r.replace('"TCP " + HOST + ":" + PORT', '"TCP " + rtspHost + ":" + PORT')
r = r.replace("BASE_URI", "baseUri")

r = rr(r,
"""        autoStartRequested = getIntent().getBooleanExtra("AUTO_START", false);
        log("CY01 LIVE v2.1 started");
""",
"""        autoStartRequested = getIntent().getBooleanExtra("AUTO_START", false);
        String requestedHost = getIntent().getStringExtra("RTSP_HOST");
        if (requestedHost != null && !requestedHost.trim().isEmpty()) {
            rtspHost = requestedHost.trim();
            baseUri = "rtsp://" + rtspHost + ":" + PORT + "/ch0";
        }
        log("CY01 LIVE v2.1 started");
""",
"read RTSP host extra")

r = rr(r,
"""    private long renderedStallOver250Count;
""",
"""    private long renderedStallOver250Count;
    private long earlyInterleavedFrameCount;
    private long earlyInterleavedByteCount;
""",
"early interleaved counters")

r = rr(r,
"""        renderedStallOver250Count = 0L;
""",
"""        renderedStallOver250Count = 0L;
        earlyInterleavedFrameCount = 0L;
        earlyInterleavedByteCount = 0L;
""",
"reset early interleaved counters")

old_response = """    private RtspResponse readRtspResponse(InputStream in) throws Exception {
        ByteArrayOutputStream headerBytes = new ByteArrayOutputStream(2048);
        int state = 0;
        while (true) {
            int b = in.read();
            if (b < 0) throw new EOFException("EOF while reading RTSP headers");
            headerBytes.write(b);
            if (state == 0 && b == '\\r') state = 1;
            else if (state == 1 && b == '\\n') state = 2;
            else if (state == 2 && b == '\\r') state = 3;
            else if (state == 3 && b == '\\n') break;
            else state = b == '\\r' ? 1 : 0;
            if (headerBytes.size() > 32768) throw new IllegalStateException("RTSP headers too large");
        }

        String headerText = headerBytes.toString(StandardCharsets.US_ASCII.name());
        String[] lines = headerText.split("\\\\r\\\\n");
        String statusLine = lines.length == 0 ? "" : lines[0];
        int code = parseStatusCode(statusLine);
        Map<String, String> headers = new HashMap<>();
        for (int i = 1; i < lines.length; i++) {
            int colon = lines[i].indexOf(':');
            if (colon <= 0) continue;
            headers.put(lines[i].substring(0, colon).trim().toLowerCase(Locale.ROOT),
                    lines[i].substring(colon + 1).trim());
        }
        int contentLength = 0;
        try { contentLength = Integer.parseInt(headers.getOrDefault("content-length", "0")); }
        catch (Exception ignored) {}
        byte[] body = readExactly(in, contentLength);
        return new RtspResponse(code, statusLine, headers, body);
    }
"""
new_response = """    private RtspResponse readRtspResponse(InputStream in) throws Exception {
        ByteArrayOutputStream headerBytes = new ByteArrayOutputStream(2048);
        int first;
        while (true) {
            first = in.read();
            if (first < 0) throw new EOFException("EOF while waiting for RTSP response");
            if (first == '$') {
                int channel = in.read();
                int hi = in.read();
                int lo = in.read();
                if (channel < 0 || hi < 0 || lo < 0) {
                    throw new EOFException("EOF in early interleaved RTP header");
                }
                int length = (hi << 8) | lo;
                byte[] packet = readExactly(in, length);
                earlyInterleavedFrameCount++;
                earlyInterleavedByteCount += length;
                if (earlyInterleavedFrameCount <= 3) {
                    log("RTSP response race: consumed early interleaved channel=" + channel
                            + " bytes=" + length + " before RTSP status line");
                }
                handleInterleavedPacket(channel, packet);
                continue;
            }
            if (first == '\\r' || first == '\\n') continue;
            break;
        }

        headerBytes.write(first);
        int state = first == '\\r' ? 1 : 0;
        while (true) {
            int b = in.read();
            if (b < 0) throw new EOFException("EOF while reading RTSP headers");
            headerBytes.write(b);
            if (state == 0 && b == '\\r') state = 1;
            else if (state == 1 && b == '\\n') state = 2;
            else if (state == 2 && b == '\\r') state = 3;
            else if (state == 3 && b == '\\n') break;
            else state = b == '\\r' ? 1 : 0;
            if (headerBytes.size() > 32768) throw new IllegalStateException("RTSP headers too large");
        }

        String headerText = headerBytes.toString(StandardCharsets.US_ASCII.name());
        String[] lines = headerText.split("\\\\r\\\\n");
        String statusLine = lines.length == 0 ? "" : lines[0];
        if (!statusLine.startsWith("RTSP/")) {
            throw new IllegalStateException("Invalid RTSP status line after framed read: " + statusLine);
        }
        int code = parseStatusCode(statusLine);
        Map<String, String> headers = new HashMap<>();
        for (int i = 1; i < lines.length; i++) {
            int colon = lines[i].indexOf(':');
            if (colon <= 0) continue;
            headers.put(lines[i].substring(0, colon).trim().toLowerCase(Locale.ROOT),
                    lines[i].substring(colon + 1).trim());
        }
        int contentLength = 0;
        try { contentLength = Integer.parseInt(headers.getOrDefault("content-length", "0")); }
        catch (Exception ignored) {}
        byte[] body = readExactly(in, contentLength);
        return new RtspResponse(code, statusLine, headers, body);
    }
"""
r = rr(r, old_response, new_response, "framed RTSP response parser")

r = rr(r,
"""                if (channel == 0) handleRtp(packet);
                else if (channel == 2) handleAudioRtp(packet);
                // channel 1 = video RTCP, channel 3 = audio RTCP; both intentionally ignored.
""",
"""                handleInterleavedPacket(channel, packet);
""",
"central interleaved dispatch")

r = rr(r,
"""    private void handleRtp(byte[] packet) {
""",
"""    private void handleInterleavedPacket(int channel, byte[] packet) {
        if (channel == 0) handleRtp(packet);
        else if (channel == 2) handleAudioRtp(packet);
    }

    private void handleRtp(byte[] packet) {
""",
"interleaved dispatch helper")

r = rr(r,
"""        log("MIC TEST v2.1: M02S camera/mic are exclusive; RTSP EOF is expected during BLE mic window");
        micTransitionExpected = true;
""",
"""        log("MIC TEST v2.1: M02S camera/mic are exclusive; RTSP EOF is expected during BLE mic window");
        preserveGoodSessionSummary();
        micTransitionExpected = true;
""",
"preserve good session before mic")

r = rr(r,
"""                    boolean recoveryRequested = MainActivityV03.requestCameraRecoveryAfterMic();
                    log("MIC TEST: full camera recovery requested=" + recoveryRequested);
                    if (recoveryRequested) {
                        log("MIC TEST: route rebuild delegated to main activity");
                    } else {
                        status("Camera recovery unavailable; copy report.");
                    }
""",
"""                    boolean recoveryRequested = MainActivityV03.requestCameraRecoveryAfterMic();
                    log("MIC TEST: full camera recovery requested=" + recoveryRequested);
                    if (recoveryRequested) {
                        log("MIC TEST: route rebuild delegated to main activity");
                        cameraRecoveryPollActive = true;
                        cameraRecoveryDeadlineMs = System.currentTimeMillis() + 30000L;
                        main.postDelayed(this::pollCameraRecoveryReady, 500L);
                    } else {
                        status("Camera recovery unavailable; copy report.");
                    }
""",
"start recovery polling")

r = rr(r,
"""    private void preserveGoodSessionSummary() {
""",
"""    private void pollCameraRecoveryReady() {
        if (!cameraRecoveryPollActive) return;
        if (MainActivityV03.consumeCameraRecoveryReady()) {
            cameraRecoveryPollActive = false;
            String recoveredIp = MainActivityV03.cameraRecoveryIp;
            if (recoveredIp != null && !recoveredIp.trim().isEmpty()) {
                rtspHost = recoveredIp.trim();
                baseUri = "rtsp://" + rtspHost + ":" + PORT + "/ch0";
            }
            log("MIC->CAMERA recovery handoff complete; restarting RTSP at " + baseUri);
            if (running) {
                stopRawTest();
                main.postDelayed(this::startRawTest, 350L);
            } else {
                startRawTest();
            }
            return;
        }
        if (System.currentTimeMillis() >= cameraRecoveryDeadlineMs) {
            cameraRecoveryPollActive = false;
            log("MIC->CAMERA recovery timed out waiting for rebuilt /ch0 route");
            status("Camera recovery timed out; copy report.");
            return;
        }
        main.postDelayed(this::pollCameraRecoveryReady, 500L);
    }

    private void preserveGoodSessionSummary() {
""",
"recovery polling helper")

r = rr(r,
"""                        + "bleMicStarted=%s bleOpusFrames=%d bleOpusBytes=%d\\n"
                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d decoderRecoveries=%d\\n\\n",
""",
"""                        + "bleMicStarted=%s bleOpusFrames=%d bleOpusBytes=%d\\n"
                        + "smooth rtpMaxGapMs=%d rtpGap100=%d frameMaxGapMs=%d frameGap100=%d frameStall250=%d earlyFrames=%d earlyBytes=%d\\n"
                        + "previousGood=%s\\n"
                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d decoderRecoveries=%d\\n\\n",
""",
"compact smoothness labels")

r = rr(r,
"""                MainActivityV03.bleMicStartedEvent, MainActivityV03.bleMicFrameCount, MainActivityV03.bleMicByteCount,
                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount);
""",
"""                MainActivityV03.bleMicStartedEvent, MainActivityV03.bleMicFrameCount, MainActivityV03.bleMicByteCount,
                maxVideoRtpGapMs, videoRtpGapOver100Count, maxRenderedFrameGapMs, renderedGapOver100Count,
                renderedStallOver250Count, earlyInterleavedFrameCount, earlyInterleavedByteCount,
                previousGoodSession.isEmpty() ? "none" : previousGoodSession,
                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount);
""",
"compact smoothness args")

r = rr(r,
"""    private void stopRawTest() {
        closeMicCapture();
""",
"""    private void stopRawTest() {
        cameraRecoveryPollActive = false;
        closeMicCapture();
""",
"cancel recovery poll on stop")

p.write_text(r)
print("v2.1 RTSP framing and recovery preparation complete")
