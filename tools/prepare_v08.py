from pathlib import Path
import runpy

# Reuse the already field-tested v0.7 P2P/re-arm preparation first.
runpy.run_path("tools/prepare_v07.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab7'", "applicationId 'com.vk.cy01streamlab8'", "v0.8 applicationId")
s = require_replace(s, "versionCode 700", "versionCode 800", "v0.8 versionCode")
s = require_replace(s, "versionName '0.7.0'", "versionName '0.8.0'", "v0.8 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Stream Lab v0.7 started", "CY01 Stream Lab v0.8 started")
s = s.replace("CY01 Stream Lab v0.7", "CY01 Stream Lab v0.8")
s = s.replace("v0.7: no explicit Android Network binding", "v0.8: no explicit Android Network binding")
s = s.replace("v0.7 will NOT bind sockets", "v0.8 will NOT bind sockets")
needle = '        box.addView(button("4. SAFE RE-ARM PREVIEW + RTSP", v -> rearmPreviewAndOpenPlayer()));\n'
insert = needle + '        box.addView(button("5. RAW /ch0 H264 DECODER", v -> startActivity(new Intent(MainActivityV03.this, RawRtspH264Activity.class))));\n'
s = require_replace(s, needle, insert, "raw decoder button")
activity.write_text(s)

player = Path("app/src/main/java/com/vk/cy01streamlab/RtspPlayerActivity.java")
p = player.read_text()
p = p.replace("CY01 RTSP Player v0.7 started", "CY01 RTSP Player v0.8 started")
p = p.replace("CY01 LIVE VIDEO v0.7", "CY01 LIVE VIDEO v0.8")
p = p.replace("CY01StreamLab/0.7", "CY01StreamLab/0.8")
player.write_text(p)

print("v0.8 preparation complete")
