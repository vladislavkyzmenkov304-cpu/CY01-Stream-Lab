from pathlib import Path
import runpy

# Build on v1.4 RTSP microphone test; harden Wi-Fi Direct peer discovery.
runpy.run_path("tools/prepare_v14.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab14'", "applicationId 'com.vk.cy01streamlab142'", "v1.4.2 applicationId")
s = require_replace(s, "versionCode 1400", "versionCode 1420", "v1.4.2 versionCode")
s = require_replace(s, "versionName '1.4.0'", "versionName '1.4.2'", "v1.4.2 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Live v1.4 started", "CY01 Live v1.4.2 started")
s = s.replace("CY01 Live v1.4", "CY01 Live v1.4.2")
s = s.replace("v1.4: no explicit Android Network binding", "v1.4.2: no explicit Android Network binding")
s = s.replace("v1.4 will NOT bind sockets", "v1.4.2 will NOT bind sockets")
s = s.replace("CY01StreamLab-OneTap/1.4", "CY01StreamLab-OneTap/1.4.2")

field = "    private Runnable p2pConnectWatchdog;\n"
field_new = field + "    private Runnable p2pDiscoveryWatchdog;\n"
s = require_replace(s, field, field_new, "p2p discovery watchdog field")

success_old = '''            @Override
            public void onSuccess() {
                log("Wi-Fi Direct discovery started, attempt=" + attempt);
                main.postDelayed(MainActivityV03.this::requestPeers, 500);
                main.postDelayed(MainActivityV03.this::requestPeers, 1200);
            }'''
success_new = '''            @Override
            public void onSuccess() {
                log("Wi-Fi Direct discovery started, attempt=" + attempt);
                main.postDelayed(MainActivityV03.this::requestPeers, 500);
                main.postDelayed(MainActivityV03.this::requestPeers, 1200);
                armP2pDiscoveryWatchdog(attempt);
            }'''
s = require_replace(s, success_old, success_new, "arm discovery watchdog after discoverPeers success")

marker = "    private String p2pReason(int reason) {\n"
methods = '''    private void armP2pDiscoveryWatchdog(int attempt) {
        if (p2pDiscoveryWatchdog != null) main.removeCallbacks(p2pDiscoveryWatchdog);
        p2pDiscoveryWatchdog = () -> {
            if (p2pConnected || p2pConnectIssued || p2pManager == null || p2pChannel == null) return;
            log("P2P discovery watchdog: no CY01 peer after 6 s on attempt=" + attempt
                    + "; checking for an already-formed group");
            p2pManager.requestConnectionInfo(p2pChannel, info -> {
                if (info != null && info.groupFormed) {
                    log("P2P discovery watchdog found an already-formed group; resuming normal flow");
                    onConnectionInfo(info);
                    return;
                }
                if (p2pConnected || p2pConnectIssued) return;
                if (p2pDiscoveryAttempt >= 5) {
                    log("P2P discovery watchdog: retries exhausted without CY01 peer");
                    status("LIVE: CY01 Wi-Fi Direct peer not found; tap STOP, then LIVE to retry");
                    return;
                }
                log("P2P discovery watchdog: peer list still empty; restarting discovery");
                requestPeers();
                discoverP2pAttempt();
            });
        };
        main.postDelayed(p2pDiscoveryWatchdog, 6000L);
    }

    private void cancelP2pDiscoveryWatchdog(String reason) {
        if (p2pDiscoveryWatchdog == null) return;
        main.removeCallbacks(p2pDiscoveryWatchdog);
        p2pDiscoveryWatchdog = null;
        log("P2P discovery watchdog cancelled: " + reason);
    }

'''
s = require_replace(s, marker, methods + marker, "insert p2p discovery watchdog methods")

peer_marker = '''            log("Wi-Fi Direct peer found: " + name + " / " + device.deviceAddress);
            if (p2pConnected || p2pConnectIssued) return;

            p2pConnectIssued = true;'''
peer_new = '''            log("Wi-Fi Direct peer found: " + name + " / " + device.deviceAddress);
            if (p2pConnected || p2pConnectIssued) return;

            cancelP2pDiscoveryWatchdog("CY01 peer found");
            p2pConnectIssued = true;'''
s = require_replace(s, peer_marker, peer_new, "cancel discovery watchdog on peer")

formed_marker = '''        if (p2pConnectWatchdog != null) {
            main.removeCallbacks(p2pConnectWatchdog);
            p2pConnectWatchdog = null;
            log("P2P connect watchdog cancelled: group formed");
        }

'''
formed_new = formed_marker + '''        cancelP2pDiscoveryWatchdog("group formed");

'''
s = require_replace(s, formed_marker, formed_new, "cancel discovery watchdog on group formed")

retry_marker = '''        if (p2pConnectWatchdog != null) {
            main.removeCallbacks(p2pConnectWatchdog);
            p2pConnectWatchdog = null;
        }
        main.postDelayed(() -> beginP2pDiscovery("connect watchdog retry"), 900);'''
retry_new = '''        if (p2pConnectWatchdog != null) {
            main.removeCallbacks(p2pConnectWatchdog);
            p2pConnectWatchdog = null;
        }
        cancelP2pDiscoveryWatchdog("connect watchdog retry");
        main.postDelayed(() -> beginP2pDiscovery("connect watchdog retry"), 900);'''
s = require_replace(s, retry_marker, retry_new, "reset discovery watchdog on connect retry")

stop_marker = '''        if (p2pConnectWatchdog != null) {
            main.removeCallbacks(p2pConnectWatchdog);
            p2pConnectWatchdog = null;
        }
        if (bleReady) {'''
stop_new = '''        if (p2pConnectWatchdog != null) {
            main.removeCallbacks(p2pConnectWatchdog);
            p2pConnectWatchdog = null;
        }
        cancelP2pDiscoveryWatchdog("STOP");
        if (bleReady) {'''
s = require_replace(s, stop_marker, stop_new, "cancel discovery watchdog on stop")

destroy_old = '''        stopLiveBatteryMonitoring();
        if (p2pConnectWatchdog != null) main.removeCallbacks(p2pConnectWatchdog);'''
destroy_new = '''        stopLiveBatteryMonitoring();
        if (p2pConnectWatchdog != null) main.removeCallbacks(p2pConnectWatchdog);
        if (p2pDiscoveryWatchdog != null) main.removeCallbacks(p2pDiscoveryWatchdog);'''
s = require_replace(s, destroy_old, destroy_new, "cancel discovery watchdog on destroy")

activity.write_text(s)

raw = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = raw.read_text()
r = r.replace("CY01 LIVE v1.4 started", "CY01 LIVE v1.4.2 started")
r = r.replace("CY01 LIVE VIDEO v1.4", "CY01 LIVE VIDEO v1.4.2")
r = r.replace("CY01StreamLab-Raw/1.4", "CY01StreamLab-Raw/1.4.2")
r = r.replace("CY01 LIVE v1.4 compact report", "CY01 LIVE v1.4.2 compact report")
raw.write_text(r)

print("v1.4.2 Wi-Fi Direct discovery recovery preparation complete")
