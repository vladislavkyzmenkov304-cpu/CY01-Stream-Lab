from pathlib import Path
import runpy

# Build on v1.1 and fix the field-observed battery monitor lifecycle bug.
runpy.run_path("tools/prepare_v11.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab11'", "applicationId 'com.vk.cy01streamlab112'", "v1.1.2 applicationId")
s = require_replace(s, "versionCode 1100", "versionCode 1120", "v1.1.2 versionCode")
s = require_replace(s, "versionName '1.1.0'", "versionName '1.1.2'", "v1.1.2 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Live v1.1 started", "CY01 Live v1.1.2 started")
s = s.replace("CY01 Live v1.1", "CY01 Live v1.1.2")
s = s.replace("v1.1: no explicit Android Network binding", "v1.1.2: no explicit Android Network binding")
s = s.replace("v1.1 will NOT bind sockets", "v1.1.2 will NOT bind sockets")
s = s.replace("CY01StreamLab-OneTap/1.1", "CY01StreamLab-OneTap/1.1.2")

# v1.1 accidentally inserted stopLiveBatteryMonitoring() at the first autoStopRunnable site,
# which is inside startLiveTest(), immediately after arming the monitor. Remove only that copy.
wrong_stop = '''        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);\n        stopLiveBatteryMonitoring();\n        if (p2pConnectWatchdog != null) {\n'''
fixed_stop = '''        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);\n        if (p2pConnectWatchdog != null) {\n'''
s = require_replace(s, wrong_stop, fixed_stop, "remove accidental immediate battery monitor stop")

# Make the monitor tolerant of temporary BLE unavailability and avoid racing the preview write.
old_run = '''        liveBatteryPollRunnable = new Runnable() {\n            @Override\n            public void run() {\n                if (!bleReady || (!p2pConnected && !oneTapLiveRequested)) return;\n                sendFrame(0x42, new byte[0]);\n                main.postDelayed(this, 60000L);\n            }\n        };\n        main.post(liveBatteryPollRunnable);\n'''
new_run = '''        liveBatteryPollRunnable = new Runnable() {\n            @Override\n            public void run() {\n                if (!p2pConnected && !oneTapLiveRequested) return;\n                if (!bleReady) {\n                    log("LIVE BATTERY poll deferred: BLE channel temporarily unavailable");\n                    main.postDelayed(this, 10000L);\n                    return;\n                }\n                sendFrame(0x42, new byte[0]);\n                main.postDelayed(this, 60000L);\n            }\n        };\n        main.postDelayed(liveBatteryPollRunnable, 800L);\n'''
s = require_replace(s, old_run, new_run, "robust battery poll runnable")

# Stop polling on real activity destruction as well. This is deliberately targeted to onDestroy,
# not the earlier startLiveTest auto-stop reset site.
on_destroy_old = '''    @Override\n    protected void onDestroy() {\n        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);\n'''
on_destroy_new = '''    @Override\n    protected void onDestroy() {\n        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);\n        stopLiveBatteryMonitoring();\n'''
s = require_replace(s, on_destroy_old, on_destroy_new, "battery monitor stop in onDestroy")
activity.write_text(s)

raw = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = raw.read_text()
r = r.replace("CY01 LIVE v1.1 started", "CY01 LIVE v1.1.2 started")
r = r.replace("CY01 LIVE VIDEO v1.1", "CY01 LIVE VIDEO v1.1.2")
r = r.replace("CY01StreamLab-Raw/1.1", "CY01StreamLab-Raw/1.1.2")
r = r.replace("CY01 LIVE v1.1 compact report", "CY01 LIVE v1.1.2 compact report")
raw.write_text(r)

print("v1.1.2 battery monitor lifecycle fix preparation complete")
