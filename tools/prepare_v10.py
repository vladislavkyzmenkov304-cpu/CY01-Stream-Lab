from pathlib import Path
import runpy

# Build on the field-proven v0.9 one-tap live path.
runpy.run_path("tools/prepare_v09.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab9'", "applicationId 'com.vk.cy01streamlab10'", "v1.0 applicationId")
s = require_replace(s, "versionCode 900", "versionCode 1000", "v1.0 versionCode")
s = require_replace(s, "versionName '0.9.0'", "versionName '1.0.0'", "v1.0 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Stream Lab v0.9 started", "CY01 Live v1.0 started")
s = s.replace("CY01 Stream Lab v0.9", "CY01 Live v1.0")
s = s.replace("v0.9: no explicit Android Network binding", "v1.0: no explicit Android Network binding")
s = s.replace("v0.9 will NOT bind sockets", "v1.0 will NOT bind sockets")
s = s.replace('button("LIVE — ONE TAP"', 'button("LIVE"')
s = s.replace(
    "LIVE — ONE TAP automates BLE → preview → Wi-Fi Direct → /ch0 → raw H.264 decode. It probes /ch0 before re-arm and re-sends only the already verified [02 01 14 01] if needed. No firmware flashing, OTA, reset, restart or BLE brute force. Manual lab controls remain below.",
    "LIVE automates BLE → preview → Wi-Fi Direct → /ch0 → H.264 decode. Physical CY01 testing confirmed that /ch0 is normally ready without re-arm; the verified [02 01 14 01] re-arm remains only as a fallback. Long-session logging is bounded. No firmware flashing, OTA, reset, restart or BLE brute force."
)
s = s.replace("ONE-TAP LIVE requested", "LIVE requested")
s = s.replace("ONE-TAP LIVE is already running", "LIVE is already running")
s = s.replace("CY01StreamLab-OneTap/0.9", "CY01StreamLab-OneTap/1.0")
# v1.0 keeps a bounded development safety window, but makes it long enough for stability tests.
s = require_replace(s, "long safetyMs = oneTapLiveRequested ? 600000L : 240000L;", "long safetyMs = oneTapLiveRequested ? 1800000L : 240000L;", "v1.0 safety window")
activity.write_text(s)

raw = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = raw.read_text()
r = r.replace("CY01 LIVE v0.9 started", "CY01 LIVE v1.0 started")
r = r.replace("CY01 LIVE VIDEO v0.9", "CY01 LIVE VIDEO v1.0")
r = r.replace("CY01StreamLab-Raw/0.9", "CY01StreamLab-Raw/1.0")

field_block = '''    private int verboseNalBudget = 24;
    private boolean autoStartRequested;
    private boolean autoStartIssued;
'''
field_new = '''    private int verboseNalBudget = 24;
    private boolean autoStartRequested;
    private boolean autoStartIssued;
    private static final int MAX_LOG_CHARS = 24000;
    private static final int MAX_CLIPBOARD_CHARS = 30000;
    private final StringBuilder diagnosticLog = new StringBuilder(MAX_LOG_CHARS + 4096);
    private long streamStartMs;
    private long lastStatsLogMs;
'''
r = require_replace(r, field_block, field_new, "v1.0 bounded log fields")

reset_marker = '''        decodedOutputCount = 0;
        verboseNalBudget = 24;
        for (int i = 0; i < nalCounts.length; i++) nalCounts[i] = 0;
'''
reset_new = '''        decodedOutputCount = 0;
        verboseNalBudget = 24;
        streamStartMs = System.currentTimeMillis();
        lastStatsLogMs = streamStartMs;
        for (int i = 0; i < nalCounts.length; i++) nalCounts[i] = 0;
'''
r = require_replace(r, reset_marker, reset_new, "v1.0 stats reset")

nal_old = '''        if (type == 7) {
            sps = nal.clone();
            log("H264 SPS received in-band, bytes=" + nal.length);
        } else if (type == 8) {
            pps = nal.clone();
            log("H264 PPS received in-band, bytes=" + nal.length);
        } else if (type == 5) {
            log("H264 IDR keyframe NAL received, bytes=" + nal.length);
        } else if (verboseNalBudget > 0) {
'''
nal_new = '''        if (type == 7) {
            sps = nal.clone();
            if (nalCounts[7] <= 2) log("H264 SPS received in-band, bytes=" + nal.length);
        } else if (type == 8) {
            pps = nal.clone();
            if (nalCounts[8] <= 2) log("H264 PPS received in-band, bytes=" + nal.length);
        } else if (type == 5) {
            if (nalCounts[5] <= 2) log("H264 IDR keyframe NAL received, bytes=" + nal.length);
        } else if (verboseNalBudget > 0) {
'''
r = require_replace(r, nal_old, nal_new, "v1.0 repetitive NAL suppression")

flush_old = '''            drainDecoder();
        } catch (Exception e) {
'''
flush_new = '''            drainDecoder();
            maybeLogSessionStats();
        } catch (Exception e) {
'''
r = require_replace(r, flush_old, flush_new, "v1.0 periodic stats hook")

copy_old = '''    private void copyLog() {
        ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (cm == null) return;
        cm.setPrimaryClip(ClipData.newPlainText("CY01 RAW RTSP H264 log", logView.getText()));
        log("Raw log copied to clipboard");
    }
'''
copy_new = '''    private void maybeLogSessionStats() {
        long now = System.currentTimeMillis();
        if (streamStartMs <= 0) streamStartMs = now;
        if (now - lastStatsLogMs < 10000L) return;
        lastStatsLogMs = now;
        double seconds = Math.max(0.001, (now - streamStartMs) / 1000.0);
        double fps = decodedOutputCount / seconds;
        log(String.format(Locale.US,
                "LIVE STATS: %.1fs RTP=%d AU=%d decoded=%d avgFPS=%.1f SPS=%d PPS=%d IDR=%d",
                seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps,
                nalCounts[7], nalCounts[8], nalCounts[5]));
    }

    private synchronized String diagnosticSnapshot() {
        return diagnosticLog.toString();
    }

    private synchronized void appendDiagnosticLine(String line) {
        diagnosticLog.append(line).append('\\n');
        if (diagnosticLog.length() <= MAX_LOG_CHARS) return;
        int target = diagnosticLog.length() - MAX_LOG_CHARS;
        int newline = diagnosticLog.indexOf("\\n", target);
        int cut = newline >= 0 ? newline + 1 : target;
        diagnosticLog.delete(0, Math.min(cut, diagnosticLog.length()));
    }

    private String buildCompactDiagnosticReport() {
        long now = System.currentTimeMillis();
        double seconds = streamStartMs > 0 ? Math.max(0.0, (now - streamStartMs) / 1000.0) : 0.0;
        double fps = seconds > 0.0 ? decodedOutputCount / seconds : 0.0;
        String summary = String.format(Locale.US,
                "CY01 LIVE v1.0 compact report\\n"
                        + "running=%s firstRendered=%s session=%s\\n"
                        + "duration=%.1fs RTP=%d accessUnits=%d decoderOutputs=%d avgFPS=%.1f\\n"
                        + "NAL SPS=%d PPS=%d IDR=%d\\n\\n",
                running, firstRendered, sessionId == null ? "" : sessionId,
                seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps,
                nalCounts[7], nalCounts[8], nalCounts[5]);
        String result = summary + diagnosticSnapshot();
        if (result.length() > MAX_CLIPBOARD_CHARS) {
            result = summary + "[older diagnostic lines trimmed]\\n" +
                    result.substring(result.length() - (MAX_CLIPBOARD_CHARS - summary.length() - 40));
        }
        return result;
    }

    private void copyLog() {
        ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (cm == null) return;
        try {
            String report = buildCompactDiagnosticReport();
            cm.setPrimaryClip(ClipData.newPlainText("CY01 LIVE compact report", report));
            log("Compact diagnostic report copied, chars=" + report.length());
        } catch (Exception e) {
            log("Clipboard copy failed safely: " + errorText(e));
            status("Could not copy report; live video remains running");
        }
    }
'''
r = require_replace(r, copy_old, copy_new, "v1.0 compact clipboard report")

log_old = '''    private void log(String text) {
        String time = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        runOnUiThread(() -> logView.append(time + "  " + text + "\\n"));
    }
'''
log_new = '''    private void log(String text) {
        String time = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        String line = time + "  " + text;
        appendDiagnosticLine(line);
        String snapshot = diagnosticSnapshot();
        runOnUiThread(() -> {
            if (logView != null) logView.setText(snapshot);
        });
    }
'''
r = require_replace(r, log_old, log_new, "v1.0 bounded visible log")
raw.write_text(r)

print("v1.0 stable one-tap preparation complete")
