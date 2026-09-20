from pathlib import Path


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab'", "applicationId 'com.vk.cy01streamlab7'", "applicationId")
s = s.replace("applicationIdSuffix '.debug'", "")
s = require_replace(s, "versionCode 2", "versionCode 700", "versionCode")
s = require_replace(s, "versionName '0.2.0'", "versionName '0.7.0'", "versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Stream Lab v0.3 started", "CY01 Stream Lab v0.7 started")
s = s.replace("CY01 Stream Lab v0.3", "CY01 Stream Lab v0.7")
s = s.replace("v0.3: no explicit Android Network binding", "v0.7: no explicit Android Network binding")
s = s.replace("v0.3 will NOT bind sockets", "v0.7 will NOT bind sockets")

needle = '        box.addView(button("PROBE NOW", v -> runBaseProbeSuite()));\n'
insert = (
    needle
    + '        box.addView(button("3. SHOW RTSP VIDEO", v -> startActivity(new Intent(MainActivityV03.this, RtspPlayerActivity.class))));\n'
    + '        box.addView(button("4. SAFE RE-ARM PREVIEW + RTSP", v -> rearmPreviewAndOpenPlayer()));\n'
)
s = require_replace(s, needle, insert, "PROBE NOW insertion")

s = s.replace("Preview auto-stops after 60 seconds.", "Preview auto-stops after 240 seconds.")
s = s.replace("main.postDelayed(autoStopRunnable, 60000);", "main.postDelayed(autoStopRunnable, 240000);")

field = "    private Runnable autoStopRunnable;\n"
s = require_replace(s, field, field + "    private Runnable p2pConnectWatchdog;\n", "watchdog field")

old_fallback = '''        log("Waiting up to 5 s for the 0x14 ACK before fallback P2P discovery");

        main.postDelayed(() -> {
            if (!previewAckSeen && !p2pConnected) {
                log("No preview ACK after 5 s; using fallback P2P discovery");
                beginP2pDiscovery("fallback timer");
            }
        }, 5000);'''
new_fallback = '''        log("Waiting up to 7 s for the 0x14 ACK before fallback P2P discovery");

        main.postDelayed(() -> {
            if (!previewAckSeen && !p2pConnected) {
                log("No preview ACK after 7 s; using fallback P2P discovery");
                beginP2pDiscovery("fallback timer");
            }
        }, 7000);'''
s = require_replace(s, old_fallback, new_fallback, "fallback timer")

old_connect_success = '''                public void onSuccess() {
                    log("Wi-Fi Direct connect requested");
                }'''
new_connect_success = '''                public void onSuccess() {
                    log("Wi-Fi Direct connect requested; watchdog armed for 8 s");
                    armP2pConnectWatchdog();
                }'''
s = require_replace(s, old_connect_success, new_connect_success, "connect success")

marker = "    private void requestConnectionInfo() {\n"
watchdog_method = '''    private void armP2pConnectWatchdog() {
        if (p2pConnectWatchdog != null) main.removeCallbacks(p2pConnectWatchdog);
        p2pConnectWatchdog = () -> {
            if (p2pConnected || p2pManager == null || p2pChannel == null) return;
            log("P2P connect watchdog: group not formed after 8 s; checking connection state");
            p2pManager.requestConnectionInfo(p2pChannel, info -> {
                if (info != null && info.groupFormed) {
                    log("P2P watchdog found a formed group; resuming normal flow");
                    onConnectionInfo(info);
                    return;
                }
                log("P2P watchdog confirmed no group; cancelling stalled negotiation");
                p2pManager.cancelConnect(p2pChannel, new WifiP2pManager.ActionListener() {
                    @Override
                    public void onSuccess() {
                        log("Stalled P2P negotiation cancelled; retrying discovery");
                        retryP2pAfterStall();
                    }

                    @Override
                    public void onFailure(int reason) {
                        log("cancelConnect result=" + p2pReason(reason) + " (" + reason + "); retrying anyway");
                        retryP2pAfterStall();
                    }
                });
            });
        };
        main.postDelayed(p2pConnectWatchdog, 8000);
    }

    private void retryP2pAfterStall() {
        p2pConnectIssued = false;
        p2pConnected = false;
        p2pSessionHandled = false;
        p2pDiscoveryStarted = false;
        if (p2pConnectWatchdog != null) {
            main.removeCallbacks(p2pConnectWatchdog);
            p2pConnectWatchdog = null;
        }
        main.postDelayed(() -> beginP2pDiscovery("connect watchdog retry"), 900);
    }

    private void rearmPreviewAndOpenPlayer() {
        if (!p2pConnected) {
            log("SAFE RE-ARM blocked: P2P group is not connected");
            return;
        }
        if (!bleReady) {
            log("SAFE RE-ARM blocked: BLE channel is not ready");
            return;
        }
        log("TWO-PHASE TEST: re-sending the SAME verified preview command [02 01 14 01] after P2P is already formed");
        log("No unknown BLE command is used. Waiting 5 s after re-arm before opening RTSP diagnostics.");
        sendFrame(0x41, new byte[]{0x02, 0x01, 0x14, 0x01});
        main.postDelayed(() -> {
            if (!p2pConnected) {
                log("SAFE RE-ARM result: P2P dropped before RTSP player launch");
                return;
            }
            log("SAFE RE-ARM +5 s: opening RTSP player for post-command DESCRIBE comparison");
            startActivity(new Intent(MainActivityV03.this, RtspPlayerActivity.class));
        }, 5000);
    }

'''
s = require_replace(s, marker, watchdog_method + marker, "requestConnectionInfo marker")

formed_marker = '        String owner = info.groupOwnerAddress == null ? "?" : info.groupOwnerAddress.getHostAddress();'
formed_insert = '''        if (p2pConnectWatchdog != null) {
            main.removeCallbacks(p2pConnectWatchdog);
            p2pConnectWatchdog = null;
            log("P2P connect watchdog cancelled: group formed");
        }

''' + formed_marker
s = require_replace(s, formed_marker, formed_insert, "formed group marker")

stop_marker = '''        if (bleReady) {
            log("Stopping preview [02 01 15 01]");'''
stop_insert = '''        if (p2pConnectWatchdog != null) {
            main.removeCallbacks(p2pConnectWatchdog);
            p2pConnectWatchdog = null;
        }
        if (bleReady) {
            log("Stopping preview [02 01 15 01]");'''
s = require_replace(s, stop_marker, stop_insert, "stop marker")

destroy_marker = "        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);"
s = require_replace(
    s,
    destroy_marker,
    destroy_marker + "\n        if (p2pConnectWatchdog != null) main.removeCallbacks(p2pConnectWatchdog);",
    "destroy marker",
)
activity.write_text(s)

player = Path("app/src/main/java/com/vk/cy01streamlab/RtspPlayerActivity.java")
p = player.read_text()
p = p.replace("CY01 RTSP Player v0.5 started", "CY01 RTSP Player v0.7 started")
p = p.replace("CY01 LIVE VIDEO v0.5", "CY01 LIVE VIDEO v0.7")
p = p.replace("User-Agent: CY01StreamLab/0.5", "User-Agent: CY01StreamLab/0.7")
p = p.replace('            "/h264",\n', '            "/h264",\n            "/video",\n            "/ch0",\n')

detect_field = "    private volatile boolean detecting;\n"
p = require_replace(p, detect_field, detect_field + "    private volatile boolean mediaSessionFound;\n", "player detecting field")

startup = '''        log("Proof rule: READY is not enough; LIVE is confirmed only after EVENT_RENDERED_FIRST_FRAME");
        autoDetectAndPlay();'''
startup_new = '''        log("Proof rule: READY is not enough; LIVE is confirmed only after EVENT_RENDERED_FIRST_FRAME");
        log("v0.7 automatically retries DESCRIBE at +10 s and +25 s if no media session exists yet");
        autoDetectAndPlay();
        playerView.postDelayed(() -> {
            if (!mediaSessionFound) {
                log("AUTO DELAYED RETRY +10 s");
                autoDetectAndPlay();
            }
        }, 10000);
        playerView.postDelayed(() -> {
            if (!mediaSessionFound) {
                log("AUTO DELAYED RETRY +25 s");
                autoDetectAndPlay();
            }
        }, 25000);'''
p = require_replace(p, startup, startup_new, "player startup")

selected_marker = '''                final String chosen = selected;
                runOnUiThread(() -> startPlayer(chosen, true));'''
selected_new = '''                mediaSessionFound = true;
                final String chosen = selected;
                log("MEDIA SESSION FOUND: " + chosen + "; starting decoder");
                runOnUiThread(() -> startPlayer(chosen, true));'''
p = require_replace(p, selected_marker, selected_new, "player selected block")
player.write_text(p)

print("v0.7 preparation complete")
