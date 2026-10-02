from pathlib import Path
import runpy

# Build on v1.2 decoder-recovery path; add only read-only video capability queries.
runpy.run_path("tools/prepare_v12.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab12'", "applicationId 'com.vk.cy01streamlab13'", "v1.3 applicationId")
s = require_replace(s, "versionCode 1200", "versionCode 1300", "v1.3 versionCode")
s = require_replace(s, "versionName '1.2.0'", "versionName '1.3.0'", "v1.3 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Live v1.2 started", "CY01 Live v1.3 started")
s = s.replace("CY01 Live v1.2", "CY01 Live v1.3")
s = s.replace("v1.2: no explicit Android Network binding", "v1.3: no explicit Android Network binding")
s = s.replace("v1.2 will NOT bind sockets", "v1.3 will NOT bind sockets")
s = s.replace("CY01StreamLab-OneTap/1.2", "CY01StreamLab-OneTap/1.3")

button_marker = '        box.addView(button("READ CAPABILITIES", v -> sendFrame(0x47, new byte[]{0x01, 0x00})));\n'
button_new = button_marker + '        box.addView(button("READ VIDEO CAPS (SAFE)", v -> readVideoCapsSafe()));\n'
s = require_replace(s, button_marker, button_new, "video caps button")

method_marker = "    private void startOneTapLive() {\n"
method = '''    private void readVideoCapsSafe() {
        if (!bleReady) {
            log("READ VIDEO CAPS blocked: connect CY01 over BLE first");
            return;
        }
        log("SAFE READ-ONLY VIDEO CAPS: query video settings [01 02]");
        sendFrame(0x41, new byte[]{0x01, 0x02});
        main.postDelayed(() -> {
            if (!bleReady) return;
            log("SAFE READ-ONLY VIDEO CAPS: query landscape resolutions [01 08 02]");
            sendFrame(0x41, new byte[]{0x01, 0x08, 0x02});
        }, 700L);
        main.postDelayed(() -> {
            if (!bleReady) return;
            log("SAFE READ-ONLY VIDEO CAPS: query portrait resolutions [01 08 04]");
            sendFrame(0x41, new byte[]{0x01, 0x08, 0x04});
        }, 1400L);
        main.postDelayed(() -> log("SAFE VIDEO CAPS query sequence finished; use COPY LOG"), 2600L);
    }

'''
s = require_replace(s, method_marker, method + method_marker, "video caps method")
activity.write_text(s)

raw = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = raw.read_text()
r = r.replace("CY01 LIVE v1.2 started", "CY01 LIVE v1.3 started")
r = r.replace("CY01 LIVE VIDEO v1.2", "CY01 LIVE VIDEO v1.3")
r = r.replace("CY01StreamLab-Raw/1.2", "CY01StreamLab-Raw/1.3")
r = r.replace("CY01 LIVE v1.2 compact report", "CY01 LIVE v1.3 compact report")
raw.write_text(r)

print("v1.3 safe video-capability query preparation complete")
