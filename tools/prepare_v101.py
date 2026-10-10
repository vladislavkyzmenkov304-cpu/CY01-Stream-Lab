from pathlib import Path
import runpy

# Build on v1.0 stable live path, then harden BLE discovery recovery.
runpy.run_path("tools/prepare_v10.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab10'", "applicationId 'com.vk.cy01streamlab101'", "v1.0.1 applicationId")
s = require_replace(s, "versionCode 1000", "versionCode 1010", "v1.0.1 versionCode")
s = require_replace(s, "versionName '1.0.0'", "versionName '1.0.1'", "v1.0.1 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Live v1.0 started", "CY01 Live v1.0.1 started")
s = s.replace("CY01 Live v1.0", "CY01 Live v1.0.1")
s = s.replace("v1.0: no explicit Android Network binding", "v1.0.1: no explicit Android Network binding")
s = s.replace("v1.0 will NOT bind sockets", "v1.0.1 will NOT bind sockets")
s = s.replace("CY01StreamLab-OneTap/1.0", "CY01StreamLab-OneTap/1.0.1")

field = '''    private boolean oneTapRearmSent;\n'''
field_new = field + '''    private int oneTapScanAttempt;\n    private static final int MAX_ONE_TAP_SCAN_ATTEMPTS = 3;\n'''
s = require_replace(s, field, field_new, "one-tap scan fields")

# Increment and log each automatic scan attempt.
scan_start = '''        scanning = true;\n        log("Scanning for CY01...");\n        scanner.startScan(scanCallback);\n'''
scan_start_new = '''        scanning = true;\n        if (oneTapLiveRequested) {\n            oneTapScanAttempt++;\n            log("LIVE BLE scan attempt=" + oneTapScanAttempt + "/" + MAX_ONE_TAP_SCAN_ATTEMPTS);\n        }\n        log("Scanning for CY01...");\n        scanner.startScan(scanCallback);\n'''
s = require_replace(s, scan_start, scan_start_new, "scan attempt logging")

# Replace the old terminal timeout with bounded automatic retry and, importantly, clear the
# one-tap state when discovery ultimately fails so LIVE is immediately usable again.
timeout_old = '''                scanning = false;\n                log("Scan timeout: CY01 not found");\n'''
timeout_new = '''                scanning = false;\n                if (oneTapLiveRequested && oneTapScanAttempt < MAX_ONE_TAP_SCAN_ATTEMPTS) {\n                    log("LIVE scan timeout: CY01 not found on attempt " + oneTapScanAttempt\n                            + "; retrying automatically");\n                    status("LIVE: CY01 not found yet; retrying BLE scan...");\n                    main.postDelayed(this::scanAndConnect, 1200);\n                } else {\n                    log("Scan timeout: CY01 not found");\n                    failOneTapDiscovery("CY01 not found after BLE scan retries");\n                }\n'''
s = require_replace(s, timeout_old, timeout_new, "scan timeout recovery")

# A scan API failure should follow the same retry/reset policy.
failed_old = '''        public void onScanFailed(int errorCode) {\n            scanning = false;\n            log("BLE scan failed: " + errorCode);\n        }\n'''
failed_new = '''        public void onScanFailed(int errorCode) {\n            scanning = false;\n            log("BLE scan failed: " + errorCode);\n            if (oneTapLiveRequested && oneTapScanAttempt < MAX_ONE_TAP_SCAN_ATTEMPTS) {\n                status("LIVE: BLE scan error; retrying...");\n                main.postDelayed(MainActivityV03.this::scanAndConnect, 1200);\n            } else {\n                failOneTapDiscovery("BLE scan failed: " + errorCode);\n            }\n        }\n'''
s = require_replace(s, failed_old, failed_new, "scan failure recovery")

# Once the device is actually found, the scan-retry counter has served its purpose.
found_marker = '''            log("Found " + name + " / " + device.getAddress());\n            status("BLE: connecting | P2P: " + (p2pConnected ? "connected" : "disconnected"));\n'''
found_new = '''            log("Found " + name + " / " + device.getAddress());\n            oneTapScanAttempt = 0;\n            status("BLE: connecting | P2P: " + (p2pConnected ? "connected" : "disconnected"));\n'''
s = require_replace(s, found_marker, found_new, "scan counter reset on found")

# Reset the counter at the beginning of a fresh LIVE request.
live_reset = '''        oneTapLiveRequested = true;\n        oneTapLaunchInProgress = false;\n        oneTapRearmSent = false;\n'''
live_reset_new = '''        oneTapLiveRequested = true;\n        oneTapLaunchInProgress = false;\n        oneTapRearmSent = false;\n        oneTapScanAttempt = 0;\n'''
s = require_replace(s, live_reset, live_reset_new, "fresh LIVE scan reset")

# Add a single state-reset helper before startOneTapLive().
marker = '''    private void startOneTapLive() {\n'''
helper = '''    private void failOneTapDiscovery(String reason) {\n        if (!oneTapLiveRequested && !oneTapLaunchInProgress) return;\n        oneTapLiveRequested = false;\n        oneTapLaunchInProgress = false;\n        oneTapRearmSent = false;\n        oneTapScanAttempt = 0;\n        log("LIVE discovery stopped cleanly: " + reason);\n        status("LIVE: CY01 not found. Tap LIVE to retry.");\n    }\n\n'''
s = require_replace(s, marker, helper + marker, "one-tap discovery reset helper")

# Explicit STOP also resets scan retry state.
stop_reset = '''        oneTapRearmSent = false;\n        if (autoStopRunnable != null) {\n'''
stop_reset_new = '''        oneTapRearmSent = false;\n        oneTapScanAttempt = 0;\n        if (autoStopRunnable != null) {\n'''
s = require_replace(s, stop_reset, stop_reset_new, "stop scan reset")

activity.write_text(s)

raw = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = raw.read_text()
r = r.replace("CY01 LIVE v1.0 started", "CY01 LIVE v1.0.1 started")
r = r.replace("CY01 LIVE VIDEO v1.0", "CY01 LIVE VIDEO v1.0.1")
r = r.replace("CY01StreamLab-Raw/1.0", "CY01StreamLab-Raw/1.0.1")
r = r.replace("CY01 LIVE v1.0 compact report", "CY01 LIVE v1.0.1 compact report")
raw.write_text(r)

print("v1.0.1 BLE discovery recovery preparation complete")
