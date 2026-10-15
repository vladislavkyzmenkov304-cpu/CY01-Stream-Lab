from pathlib import Path
import runpy

# Build on field-tested v1.1.2 battery telemetry path.
runpy.run_path("tools/prepare_v112.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab112'", "applicationId 'com.vk.cy01streamlab12'", "v1.2 applicationId")
s = require_replace(s, "versionCode 1120", "versionCode 1200", "v1.2 versionCode")
s = require_replace(s, "versionName '1.1.2'", "versionName '1.2.0'", "v1.2 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Live v1.1.2 started", "CY01 Live v1.2 started")
s = s.replace("CY01 Live v1.1.2", "CY01 Live v1.2")
s = s.replace("v1.1.2: no explicit Android Network binding", "v1.2: no explicit Android Network binding")
s = s.replace("v1.1.2 will NOT bind sockets", "v1.2 will NOT bind sockets")
s = s.replace("CY01StreamLab-OneTap/1.1.2", "CY01StreamLab-OneTap/1.2")
activity.write_text(s)

raw = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = raw.read_text()
r = r.replace("CY01 LIVE v1.1.2 started", "CY01 LIVE v1.2 started")
r = r.replace("CY01 LIVE VIDEO v1.1.2", "CY01 LIVE VIDEO v1.2")
r = r.replace("CY01StreamLab-Raw/1.1.2", "CY01StreamLab-Raw/1.2")
r = r.replace("CY01 LIVE v1.1.2 compact report", "CY01 LIVE v1.2 compact report")

field = '''    private long interleavedResyncBytes;\n'''
field_new = field + '''    private long lastDecodedOutputMs;\n    private long decoderRecoveryCount;\n    private long lastStatsSampleMs;\n    private long lastStatsAuCount;\n    private long lastStatsDecodedCount;\n'''
r = require_replace(r, field, field_new, "v1.2 recovery fields")

reset = '''        interleavedResyncBytes = 0;\n        verboseNalBudget = 24;\n        streamStartMs = System.currentTimeMillis();\n        lastStatsLogMs = streamStartMs;\n'''
reset_new = '''        interleavedResyncBytes = 0;\n        lastDecodedOutputMs = 0L;\n        decoderRecoveryCount = 0L;\n        verboseNalBudget = 24;\n        streamStartMs = System.currentTimeMillis();\n        lastStatsLogMs = streamStartMs;\n        lastStatsSampleMs = streamStartMs;\n        lastStatsAuCount = 0L;\n        lastStatsDecodedCount = 0L;\n'''
r = require_replace(r, reset, reset_new, "v1.2 recovery reset")

configure_marker = '''            decoder = codec;\n            decoderConfigured = true;\n            log("MediaCodec AVC decoder configured from in-band SPS/PPS (initial hint 1280x960)");\n'''
configure_new = '''            decoder = codec;\n            decoderConfigured = true;\n            lastDecodedOutputMs = System.currentTimeMillis();\n            log("MediaCodec AVC decoder configured from in-band SPS/PPS (initial hint 1280x960)");\n'''
r = require_replace(r, configure_marker, configure_new, "v1.2 decoder configure timestamp")

output_marker = '''                decodedOutputCount++;\n                if (decodedOutputCount == 1) {\n'''
output_new = '''                decodedOutputCount++;\n                lastDecodedOutputMs = System.currentTimeMillis();\n                if (decodedOutputCount == 1) {\n'''
r = require_replace(r, output_marker, output_new, "v1.2 decoder output timestamp")

flush_marker = '''    private void flushAccessUnit(long rtpTimestamp) {\n        if (accessUnit.size() == 0) return;\n        byte[] au = accessUnit.toByteArray();\n        accessUnit.reset();\n        accessUnitCount++;\n'''
flush_new = '''    private void flushAccessUnit(long rtpTimestamp) {\n        if (accessUnit.size() == 0) return;\n        byte[] au = accessUnit.toByteArray();\n        accessUnit.reset();\n        accessUnitCount++;\n        if (decoderConfigured && decoder != null && lastDecodedOutputMs > 0L\n                && System.currentTimeMillis() - lastDecodedOutputMs > 3500L) {\n            recoverDecoderFromStall();\n            return;\n        }\n'''
r = require_replace(r, flush_marker, flush_new, "v1.2 decoder watchdog hook")

marker = '''    private void drainDecoder() {\n'''
recovery_method = '''    private void recoverDecoderFromStall() {\n        decoderRecoveryCount++;\n        long stalledMs = lastDecodedOutputMs > 0L\n                ? Math.max(0L, System.currentTimeMillis() - lastDecodedOutputMs) : -1L;\n        log("DECODER STALL detected: no output for " + stalledMs\n                + " ms while RTP/access units continue; recovery #" + decoderRecoveryCount);\n        status("Video decoder stalled; recovering automatically...");\n        releaseDecoder();\n        // Keep the latest in-band SPS/PPS. The CY01 repeats SPS/PPS/IDR roughly every keyframe cycle,\n        // so a fresh MediaCodec instance can rejoin the already-running RTSP/RTP session.\n        if (sps != null && pps != null && surface != null && surface.isValid()) {\n            configureDecoder();\n            log("DECODER RECOVERY #" + decoderRecoveryCount\n                    + " reconfigured MediaCodec; waiting for next IDR/keyframe");\n        } else {\n            log("DECODER RECOVERY #" + decoderRecoveryCount\n                    + " waiting for SPS/PPS or valid Surface before reconfigure");\n        }\n    }\n\n'''
r = require_replace(r, marker, recovery_method + marker, "v1.2 decoder recovery method")

stats_old = '''        double fps = decodedOutputCount / seconds;\n        double mbps = (rtpPayloadByteCount * 8.0) / seconds / 1_000_000.0;\n        int battery = MainActivityV03.latestBatteryPercent;\n        String batteryText = battery >= 0 ? (battery + "%") : "?";\n        log(String.format(Locale.US,\n                "LIVE STATS: %.1fs RTP=%d AU=%d decoded=%d avgFPS=%.1f video=%.2fMbps battery=%s SPS=%d PPS=%d IDR=%d resyncBytes=%d",\n                seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps, mbps, batteryText,\n                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes));\n'''
stats_new = '''        double fps = decodedOutputCount / seconds;\n        double mbps = (rtpPayloadByteCount * 8.0) / seconds / 1_000_000.0;\n        long sampleMs = Math.max(1L, now - lastStatsSampleMs);\n        double sourceFps10s = (accessUnitCount - lastStatsAuCount) * 1000.0 / sampleMs;\n        double decodedFps10s = (decodedOutputCount - lastStatsDecodedCount) * 1000.0 / sampleMs;\n        lastStatsSampleMs = now;\n        lastStatsAuCount = accessUnitCount;\n        lastStatsDecodedCount = decodedOutputCount;\n        int battery = MainActivityV03.latestBatteryPercent;\n        String batteryText = battery >= 0 ? (battery + "%") : "?";\n        log(String.format(Locale.US,\n                "LIVE STATS: %.1fs RTP=%d AU=%d decoded=%d avgFPS=%.1f sourceFPS10s=%.1f decodedFPS10s=%.1f video=%.2fMbps battery=%s SPS=%d PPS=%d IDR=%d resyncBytes=%d recoveries=%d",\n                seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps, sourceFps10s, decodedFps10s,\n                mbps, batteryText, nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount));\n'''
r = require_replace(r, stats_old, stats_new, "v1.2 window fps stats")

report_old = '''                        + "batteryStart=%d%% batteryNow=%d%% charging=%s\\n"\n                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d\\n\\n",\n'''
report_new = '''                        + "batteryStart=%d%% batteryNow=%d%% charging=%s\\n"\n                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d decoderRecoveries=%d\\n\\n",\n'''
r = require_replace(r, report_old, report_new, "v1.2 report recovery label")
report_args_old = '''                startBattery, battery, MainActivityV03.latestBatteryCharging,\n                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes);\n'''
report_args_new = '''                startBattery, battery, MainActivityV03.latestBatteryCharging,\n                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount);\n'''
r = require_replace(r, report_args_old, report_args_new, "v1.2 report recovery arg")

raw.write_text(r)
print("v1.2 decoder stall recovery preparation complete")
