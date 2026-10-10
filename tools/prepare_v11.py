from pathlib import Path
import runpy

# Build on the field-tested v1.0.1 one-tap/BLE-recovery path.
runpy.run_path("tools/prepare_v101.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab101'", "applicationId 'com.vk.cy01streamlab11'", "v1.1 applicationId")
s = require_replace(s, "versionCode 1010", "versionCode 1100", "v1.1 versionCode")
s = require_replace(s, "versionName '1.0.1'", "versionName '1.1.0'", "v1.1 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Live v1.0.1 started", "CY01 Live v1.1 started")
s = s.replace("CY01 Live v1.0.1", "CY01 Live v1.1")
s = s.replace("v1.0.1: no explicit Android Network binding", "v1.1: no explicit Android Network binding")
s = s.replace("v1.0.1 will NOT bind sockets", "v1.1 will NOT bind sockets")
s = s.replace("CY01StreamLab-OneTap/1.0.1", "CY01StreamLab-OneTap/1.1")

field = '''    private static final int MAX_ONE_TAP_SCAN_ATTEMPTS = 3;\n'''
field_new = field + '''    private Runnable liveBatteryPollRunnable;\n    public static volatile int latestBatteryPercent = -1;\n    public static volatile boolean latestBatteryCharging;\n    public static volatile int liveStartBatteryPercent = -1;\n    public static volatile long liveBatteryStartMs;\n'''
s = require_replace(s, field, field_new, "battery telemetry fields")

battery_old = '''        if (opcode == 0x42 && payload.length >= 2) {\n            log("Battery: " + (payload[0] & 0xFF) + "% charging=" + ((payload[1] & 0xFF) != 0));\n            return;\n        }\n'''
battery_new = '''        if (opcode == 0x42 && payload.length >= 2) {\n            int pct = payload[0] & 0xFF;\n            boolean charging = (payload[1] & 0xFF) != 0;\n            latestBatteryPercent = pct;\n            latestBatteryCharging = charging;\n            if (liveBatteryStartMs > 0 && liveStartBatteryPercent < 0) liveStartBatteryPercent = pct;\n            if (liveBatteryStartMs > 0) {\n                double minutes = Math.max(0.01, (System.currentTimeMillis() - liveBatteryStartMs) / 60000.0);\n                int drop = liveStartBatteryPercent >= 0 ? Math.max(0, liveStartBatteryPercent - pct) : 0;\n                if (!charging && drop > 0 && minutes >= 1.0) {\n                    double pctPerHour = drop * 60.0 / minutes;\n                    double estMinutes = pctPerHour > 0.01 ? (pct / pctPerHour) * 60.0 : 0.0;\n                    log(String.format(Locale.US,\n                            "LIVE BATTERY: %d%% drop=%d%% over %.1f min observedRate=%.1f%%/h estRemaining=%.0f min",\n                            pct, drop, minutes, pctPerHour, estMinutes));\n                } else {\n                    log("LIVE BATTERY: " + pct + "% charging=" + charging\n                            + " elapsed=" + String.format(Locale.US, "%.1f", minutes) + " min");\n                }\n                if (!charging && pct <= 15) {\n                    log("LIVE BATTERY LOW: " + pct + "% — no automatic stop; user remains in control");\n                }\n            } else {\n                log("Battery: " + pct + "% charging=" + charging);\n            }\n            return;\n        }\n'''
s = require_replace(s, battery_old, battery_new, "battery response telemetry")

marker = '''    private void startLiveTest() {\n'''
battery_methods = '''    private void startLiveBatteryMonitoring() {\n        stopLiveBatteryMonitoring();\n        latestBatteryPercent = -1;\n        latestBatteryCharging = false;\n        liveStartBatteryPercent = -1;\n        liveBatteryStartMs = System.currentTimeMillis();\n        log("LIVE BATTERY monitor armed: safe opcode 0x42 every 60 s");\n        liveBatteryPollRunnable = new Runnable() {\n            @Override\n            public void run() {\n                if (!bleReady || (!p2pConnected && !oneTapLiveRequested)) return;\n                sendFrame(0x42, new byte[0]);\n                main.postDelayed(this, 60000L);\n            }\n        };\n        main.post(liveBatteryPollRunnable);\n    }\n\n    private void stopLiveBatteryMonitoring() {\n        if (liveBatteryPollRunnable != null) {\n            main.removeCallbacks(liveBatteryPollRunnable);\n            liveBatteryPollRunnable = null;\n        }\n        liveBatteryStartMs = 0L;\n    }\n\n'''
s = require_replace(s, marker, battery_methods + marker, "battery monitoring methods")

preview_send = '''        log("Starting HeyCyan preview P2P command [02 01 14 01]");\n        sendFrame(0x41, new byte[]{0x02, 0x01, 0x14, 0x01});\n'''
preview_send_new = preview_send + '''        if (oneTapLiveRequested) startLiveBatteryMonitoring();\n'''
s = require_replace(s, preview_send, preview_send_new, "start battery monitor with LIVE")

stop_marker = '''    private void stopPreviewAndP2p() {\n        oneTapLiveRequested = false;\n'''
stop_new = '''    private void stopPreviewAndP2p() {\n        stopLiveBatteryMonitoring();\n        oneTapLiveRequested = false;\n'''
s = require_replace(s, stop_marker, stop_new, "stop battery monitor")

destroy_marker = '''        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);\n'''
destroy_new = '''        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);\n        stopLiveBatteryMonitoring();\n'''
s = require_replace(s, destroy_marker, destroy_new, "destroy battery monitor", count=1)
activity.write_text(s)

raw = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = raw.read_text()
r = r.replace("CY01 LIVE v1.0.1 started", "CY01 LIVE v1.1 started")
r = r.replace("CY01 LIVE VIDEO v1.0.1", "CY01 LIVE VIDEO v1.1")
r = r.replace("CY01StreamLab-Raw/1.0.1", "CY01StreamLab-Raw/1.1")
r = r.replace("CY01 LIVE v1.0.1 compact report", "CY01 LIVE v1.1 compact report")

field_raw = '''    private long decodedOutputCount;\n'''
field_raw_new = field_raw + '''    private long rtpPayloadByteCount;\n    private long interleavedResyncBytes;\n'''
r = require_replace(r, field_raw, field_raw_new, "raw bitrate fields")

reset_raw = '''        decodedOutputCount = 0;\n        verboseNalBudget = 24;\n'''
reset_raw_new = '''        decodedOutputCount = 0;\n        rtpPayloadByteCount = 0;\n        interleavedResyncBytes = 0;\n        verboseNalBudget = 24;\n'''
r = require_replace(r, reset_raw, reset_raw_new, "raw bitrate reset")

stray_old = '''                if (marker != '$') {\n                    // Unexpected server-side RTSP text after PLAY. Read the rest of the line only.\n                    ByteArrayOutputStream line = new ByteArrayOutputStream();\n                    line.write(marker);\n                    int b;\n                    while ((b = in.read()) >= 0 && b != '\\n' && line.size() < 1024) line.write(b);\n                    log("Post-PLAY RTSP text: " + line.toString(StandardCharsets.US_ASCII.name()).trim());\n                    continue;\n                }\n\n                int channel = in.read();\n'''
stray_new = '''                if (marker != '$') {\n                    // We expect only RFC2326 interleaved RTP/RTCP after PLAY. If framing is ever\n                    // lost, do not interpret binary H.264 as text (which previously flooded logs);\n                    // scan forward to the next interleaved frame marker and continue.\n                    long skipped = 1;\n                    int b = marker;\n                    while (running && b >= 0 && b != '$' && skipped < 65536) {\n                        b = in.read();\n                        if (b != '$') skipped++;\n                    }\n                    interleavedResyncBytes += skipped;\n                    if (interleavedResyncBytes == skipped || interleavedResyncBytes % 65536 < skipped) {\n                        log("RTSP interleaved resync: skipped binary/non-framed bytes=" + skipped\n                                + " total=" + interleavedResyncBytes);\n                    }\n                    if (b < 0) throw new EOFException("RTSP/RTP socket closed during resync");\n                    if (b != '$') continue;\n                }\n\n                int channel = in.read();\n'''
r = require_replace(r, stray_old, stray_new, "interleaved resync hardening")

payload_count_marker = '''        if (end <= off) return;\n\n        rtpPacketCount++;\n'''
payload_count_new = '''        if (end <= off) return;\n\n        rtpPacketCount++;\n        rtpPayloadByteCount += (end - off);\n'''
r = require_replace(r, payload_count_marker, payload_count_new, "RTP payload byte counting")

stats_old = '''        double fps = decodedOutputCount / seconds;\n        log(String.format(Locale.US,\n                "LIVE STATS: %.1fs RTP=%d AU=%d decoded=%d avgFPS=%.1f SPS=%d PPS=%d IDR=%d",\n                seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps,\n                nalCounts[7], nalCounts[8], nalCounts[5]));\n'''
stats_new = '''        double fps = decodedOutputCount / seconds;\n        double mbps = (rtpPayloadByteCount * 8.0) / seconds / 1_000_000.0;\n        int battery = MainActivityV03.latestBatteryPercent;\n        String batteryText = battery >= 0 ? (battery + "%") : "?";\n        log(String.format(Locale.US,\n                "LIVE STATS: %.1fs RTP=%d AU=%d decoded=%d avgFPS=%.1f video=%.2fMbps battery=%s SPS=%d PPS=%d IDR=%d resyncBytes=%d",\n                seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps, mbps, batteryText,\n                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes));\n'''
r = require_replace(r, stats_old, stats_new, "stats bitrate+battery")

report_old = '''        double fps = seconds > 0.0 ? decodedOutputCount / seconds : 0.0;\n        String summary = String.format(Locale.US,\n                "CY01 LIVE v1.1 compact report\\n"\n                        + "running=%s firstRendered=%s session=%s\\n"\n                        + "duration=%.1fs RTP=%d accessUnits=%d decoderOutputs=%d avgFPS=%.1f\\n"\n                        + "NAL SPS=%d PPS=%d IDR=%d\\n\\n",\n                running, firstRendered, sessionId == null ? "" : sessionId,\n                seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps,\n                nalCounts[7], nalCounts[8], nalCounts[5]);\n'''
report_new = '''        double fps = seconds > 0.0 ? decodedOutputCount / seconds : 0.0;\n        double mbps = seconds > 0.0 ? (rtpPayloadByteCount * 8.0) / seconds / 1_000_000.0 : 0.0;\n        int battery = MainActivityV03.latestBatteryPercent;\n        int startBattery = MainActivityV03.liveStartBatteryPercent;\n        String summary = String.format(Locale.US,\n                "CY01 LIVE v1.1 compact report\\n"\n                        + "running=%s firstRendered=%s session=%s\\n"\n                        + "duration=%.1fs RTP=%d accessUnits=%d decoderOutputs=%d avgFPS=%.1f video=%.2fMbps\\n"\n                        + "batteryStart=%d%% batteryNow=%d%% charging=%s\\n"\n                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d\\n\\n",\n                running, firstRendered, sessionId == null ? "" : sessionId,\n                seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps, mbps,\n                startBattery, battery, MainActivityV03.latestBatteryCharging,\n                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes);\n'''
r = require_replace(r, report_old, report_new, "compact report battery+bitrate")
raw.write_text(r)

print("v1.1 battery telemetry and long-session hardening preparation complete")
