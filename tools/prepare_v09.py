from pathlib import Path
import runpy

# Build on the field-proven v0.8.1 transport/decoder path.
runpy.run_path("tools/prepare_v08.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab8'", "applicationId 'com.vk.cy01streamlab9'", "v0.9 applicationId")
s = require_replace(s, "versionCode 801", "versionCode 900", "v0.9 versionCode")
s = require_replace(s, "versionName '0.8.1'", "versionName '0.9.0'", "v0.9 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Stream Lab v0.8.1 started", "CY01 Stream Lab v0.9 started")
s = s.replace("CY01 Stream Lab v0.8.1", "CY01 Stream Lab v0.9")
s = s.replace("v0.8.1: no explicit Android Network binding", "v0.9: no explicit Android Network binding")
s = s.replace("v0.8.1 will NOT bind sockets", "v0.9 will NOT bind sockets")

field = "    private Runnable p2pConnectWatchdog;\n"
extra_fields = field + """    private boolean oneTapLiveRequested;
    private boolean oneTapLaunchInProgress;
    private boolean oneTapRearmSent;
"""
s = require_replace(s, field, extra_fields, "one-tap fields")

status_marker = '''        status.setPadding(0, dp(8), 0, dp(8));
        box.addView(status);

        box.addView(button("1. CONNECT CY01", v -> scanAndConnect()));'''
status_replacement = '''        status.setPadding(0, dp(8), 0, dp(8));
        box.addView(status);

        box.addView(button("LIVE — ONE TAP", v -> startOneTapLive()));
        box.addView(button("1. CONNECT CY01", v -> scanAndConnect()));'''
s = require_replace(s, status_marker, status_replacement, "one-tap button")

note_old = "No firmware flashing, OTA, reset, restart or BLE brute force. The Eyevue-style HTTP trigger is now manual and is NOT run by the base probe. Preview auto-stops after 240 seconds."
note_new = "LIVE — ONE TAP automates BLE → preview → Wi-Fi Direct → /ch0 → raw H.264 decode. It probes /ch0 before re-arm and re-sends only the already verified [02 01 14 01] if needed. No firmware flashing, OTA, reset, restart or BLE brute force. Manual lab controls remain below."
s = require_replace(s, note_old, note_new, "v0.9 note")

# Once BLE notifications are ready, a one-tap request automatically continues to preview.
descriptor_old = '''            bleReady = statusCode == BluetoothGatt.GATT_SUCCESS;
            log("BLE command channel ready=" + bleReady + " status=" + statusCode);
            status("BLE: " + (bleReady ? "ready" : "error") + " | P2P: " + (p2pConnected ? "connected" : "disconnected"));
        }'''
descriptor_new = '''            bleReady = statusCode == BluetoothGatt.GATT_SUCCESS;
            log("BLE command channel ready=" + bleReady + " status=" + statusCode);
            status("BLE: " + (bleReady ? "ready" : "error") + " | P2P: " + (p2pConnected ? "connected" : "disconnected"));
            if (bleReady && oneTapLiveRequested) {
                log("ONE-TAP: BLE ready; continuing automatically to preview/P2P");
                main.postDelayed(MainActivityV03.this::startLiveTest, 250);
            }
        }'''
s = require_replace(s, descriptor_old, descriptor_new, "descriptor auto-continue")

# Route an accepted P2P IP directly into the one-tap /ch0 readiness test instead of the old lab probe.
ip_old = '''            glassesIp = candidateIp;
            log("Glasses P2P IP accepted = " + glassesIp);
            logP2pRoutes();
            main.postDelayed(this::runBaseProbeSuite, 700);
            return;'''
ip_new = '''            glassesIp = candidateIp;
            log("Glasses P2P IP accepted = " + glassesIp);
            logP2pRoutes();
            if (oneTapLiveRequested) {
                log("ONE-TAP: P2P address ready; checking confirmed RTSP media session /ch0");
                main.postDelayed(this::oneTapCheckCh0AndLaunch, 700);
            } else {
                main.postDelayed(this::runBaseProbeSuite, 700);
            }
            return;'''
s = require_replace(s, ip_old, ip_new, "accepted IP one-tap route")

fallback_old = '''            glassesIp = "192.168.49.96";
            log("No accepted BLE P2P IP after retries; using confirmed CY01 fallback " + glassesIp);
            main.postDelayed(this::runBaseProbeSuite, 500);'''
fallback_new = '''            glassesIp = "192.168.49.96";
            log("No accepted BLE P2P IP after retries; using confirmed CY01 fallback " + glassesIp);
            if (oneTapLiveRequested) main.postDelayed(this::oneTapCheckCh0AndLaunch, 500);
            else main.postDelayed(this::runBaseProbeSuite, 500);'''
s = require_replace(s, fallback_old, fallback_new, "fallback IP one-tap route")

# The field-proven v0.8.1 preparation schedules 240 s. One-tap gets a longer, still bounded safety window.
timer_old = "        main.postDelayed(autoStopRunnable, 240000);"
timer_new = '''        long safetyMs = oneTapLiveRequested ? 600000L : 240000L;
        log("Preview/P2P safety timeout armed for " + (safetyMs / 1000L) + " s");
        main.postDelayed(autoStopRunnable, safetyMs);'''
s = require_replace(s, timer_old, timer_new, "one-tap safety timeout")

# Insert the one-tap orchestration before the existing lab startLiveTest method.
marker = "    private void startLiveTest() {\n"
one_tap_methods = '''    private void startOneTapLive() {
        if (oneTapLiveRequested || oneTapLaunchInProgress) {
            log("ONE-TAP LIVE is already running");
            return;
        }
        oneTapLiveRequested = true;
        oneTapLaunchInProgress = false;
        oneTapRearmSent = false;
        log("ONE-TAP LIVE requested: BLE -> preview -> P2P -> DESCRIBE /ch0 -> raw H.264 decoder");
        status("ONE-TAP: connecting CY01...");
        if (bleReady) {
            startLiveTest();
        } else {
            scanAndConnect();
        }
    }

    private void oneTapCheckCh0AndLaunch() {
        if (!oneTapLiveRequested || oneTapLaunchInProgress) return;
        if (!p2pConnected) {
            log("ONE-TAP /ch0 check deferred: P2P is not connected");
            return;
        }
        oneTapLaunchInProgress = true;
        final String ip = glassesIp != null ? glassesIp : "192.168.49.96";
        io.execute(() -> {
            String statusLine = describeCh0Status(ip);
            log("ONE-TAP DESCRIBE /ch0 -> " + statusLine);
            if (statusLine.startsWith("RTSP/1.0 200")) {
                main.post(() -> launchRawDecoderAuto("/ch0 already ready; no re-arm needed"));
                return;
            }

            if (!oneTapRearmSent && bleReady) {
                oneTapRearmSent = true;
                oneTapLaunchInProgress = false;
                main.post(() -> {
                    log("ONE-TAP: /ch0 not ready; sending the SAME verified preview re-arm [02 01 14 01]");
                    sendFrame(0x41, new byte[]{0x02, 0x01, 0x14, 0x01});
                    main.postDelayed(this::oneTapCheckCh0AndLaunch, 5000);
                });
                return;
            }

            oneTapLaunchInProgress = false;
            log("ONE-TAP failed to obtain /ch0 media session after safe re-arm: " + statusLine);
            status("ONE-TAP: /ch0 unavailable; use COPY LOG");
        });
    }

    private String describeCh0Status(String ip) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(ip, 8554), 1500);
            socket.setSoTimeout(1800);
            String uri = "rtsp://" + ip + ":8554/ch0";
            String request = "DESCRIBE " + uri + " RTSP/1.0\\r\\n"
                    + "CSeq: 91\\r\\n"
                    + "Accept: application/sdp\\r\\n"
                    + "User-Agent: CY01StreamLab-OneTap/0.9\\r\\n\\r\\n";
            OutputStream os = socket.getOutputStream();
            os.write(request.getBytes(StandardCharsets.US_ASCII));
            os.flush();
            BufferedReader br = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.US_ASCII));
            String first = br.readLine();
            return first == null ? "EOF" : first;
        } catch (Exception e) {
            return errorText(e);
        }
    }

    private void launchRawDecoderAuto(String reason) {
        if (!p2pConnected) {
            oneTapLaunchInProgress = false;
            log("ONE-TAP raw launch cancelled: P2P dropped");
            return;
        }
        log("ONE-TAP /ch0 READY: " + reason);
        log("ONE-TAP launching raw RTP/H.264 decoder with AUTO_START=true");
        status("ONE-TAP: /ch0 ready; opening live video...");
        Intent intent = new Intent(MainActivityV03.this, RawRtspH264Activity.class);
        intent.putExtra("AUTO_START", true);
        intent.putExtra("ONE_TAP", true);
        startActivity(intent);
        oneTapLiveRequested = false;
        oneTapLaunchInProgress = false;
    }

'''
s = require_replace(s, marker, one_tap_methods + marker, "one-tap methods")

# Reset one-tap state when the user explicitly stops the preview/P2P session.
stop_marker = '''    private void stopPreviewAndP2p() {
        if (autoStopRunnable != null) {'''
stop_new = '''    private void stopPreviewAndP2p() {
        oneTapLiveRequested = false;
        oneTapLaunchInProgress = false;
        oneTapRearmSent = false;
        if (autoStopRunnable != null) {'''
s = require_replace(s, stop_marker, stop_new, "one-tap stop reset")
activity.write_text(s)

raw = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = raw.read_text()
r = r.replace("CY01 RAW RTSP/H264 v0.8 started", "CY01 LIVE v0.9 started")
r = r.replace("CY01 RAW /ch0 H264 v0.8", "CY01 LIVE VIDEO v0.9")
r = r.replace("CY01StreamLab-Raw/0.8", "CY01StreamLab-Raw/0.9")

raw_field = "    private int verboseNalBudget = 24;\n"
r = require_replace(r, raw_field, raw_field + "    private boolean autoStartRequested;\n    private boolean autoStartIssued;\n", "raw auto-start fields")

oncreate_old = '''        buildUi();
        log("CY01 LIVE v0.9 started");
        log("Target is confirmed media session: " + BASE_URI);'''
oncreate_new = '''        buildUi();
        autoStartRequested = getIntent().getBooleanExtra("AUTO_START", false);
        log("CY01 LIVE v0.9 started");
        log("Target is confirmed media session: " + BASE_URI);
        log("AUTO_START=" + autoStartRequested + " ONE_TAP=" + getIntent().getBooleanExtra("ONE_TAP", false));'''
r = require_replace(r, oncreate_old, oncreate_new, "raw onCreate auto-start")

surface_old = '''        log("Video surface ready=" + surfaceReady);
        status("RAW RTSP ready. Tap START RAW /ch0 TEST");
    }'''
surface_new = '''        log("Video surface ready=" + surfaceReady);
        if (autoStartRequested && !autoStartIssued && surfaceReady) {
            autoStartIssued = true;
            status("ONE-TAP: video surface ready; starting /ch0 automatically...");
            log("AUTO_START: Surface ready; starting raw /ch0 session automatically");
            main.postDelayed(this::startRawTest, 300);
        } else {
            status("RAW RTSP ready. Tap START RAW /ch0 TEST");
        }
    }'''
r = require_replace(r, surface_old, surface_new, "raw surface auto-start")
raw.write_text(r)

print("v0.9 one-tap preparation complete")
