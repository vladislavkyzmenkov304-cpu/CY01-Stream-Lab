from pathlib import Path
import runpy

# Build on v1.3 (which itself includes v1.2 decoder recovery + battery telemetry).
runpy.run_path("tools/prepare_v13.py", run_name="__main__")


def require_replace(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, count)


gradle = Path("app/build.gradle")
s = gradle.read_text()
s = require_replace(s, "applicationId 'com.vk.cy01streamlab13'", "applicationId 'com.vk.cy01streamlab14'", "v1.4 applicationId")
s = require_replace(s, "versionCode 1300", "versionCode 1400", "v1.4 versionCode")
s = require_replace(s, "versionName '1.3.0'", "versionName '1.4.0'", "v1.4 versionName")
gradle.write_text(s)

activity = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = activity.read_text()
s = s.replace("CY01 Live v1.3 started", "CY01 Live v1.4 started")
s = s.replace("CY01 Live v1.3", "CY01 Live v1.4")
s = s.replace("v1.3: no explicit Android Network binding", "v1.4: no explicit Android Network binding")
s = s.replace("v1.3 will NOT bind sockets", "v1.4 will NOT bind sockets")
s = s.replace("CY01StreamLab-OneTap/1.3", "CY01StreamLab-OneTap/1.4")
activity.write_text(s)

raw = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = raw.read_text()
r = r.replace("CY01 LIVE v1.3 started", "CY01 LIVE v1.4 started")
r = r.replace("CY01 LIVE VIDEO v1.3", "CY01 LIVE VIDEO v1.4")
r = r.replace("CY01StreamLab-Raw/1.3", "CY01StreamLab-Raw/1.4")
r = r.replace("CY01 LIVE v1.3 compact report", "CY01 LIVE v1.4 compact report")

r = require_replace(r, "import android.media.MediaFormat;\n", "import android.media.MediaFormat;\nimport android.media.MediaPlayer;\n", "MediaPlayer import")
r = require_replace(r, "import java.io.EOFException;\n", "import java.io.EOFException;\nimport java.io.File;\nimport java.io.FileOutputStream;\n", "file imports")

field = '''    private long lastStatsDecodedCount;\n'''
field_new = field + '''    private long audioRtpPacketCount;\n    private long audioAacFrameCount;\n    private long audioAacByteCount;\n    private boolean firstAudioRtp;\n    private boolean firstAacFrame;\n    private File micSampleFile;\n    private FileOutputStream micSampleOut;\n    private long micCaptureDeadlineMs;\n    private long micSampleBytes;\n    private MediaPlayer micPlayer;\n'''
r = require_replace(r, field, field_new, "v1.4 audio fields")

button_old = '''        root.addView(button("COPY RAW LOG", v -> copyLog()));\n        root.addView(button("STOP RAW TEST", v -> stopRawTest()));\n'''
button_new = '''        root.addView(button("COPY RAW LOG", v -> copyLog()));\n        root.addView(button("PLAY MIC SAMPLE", v -> playMicSample()));\n        root.addView(button("STOP RAW TEST", v -> stopRawTest()));\n'''
r = require_replace(r, button_old, button_new, "mic playback button")

reset_old = '''        lastStatsDecodedCount = 0L;\n        for (int i = 0; i < nalCounts.length; i++) nalCounts[i] = 0;\n'''
reset_new = '''        lastStatsDecodedCount = 0L;\n        audioRtpPacketCount = 0L;\n        audioAacFrameCount = 0L;\n        audioAacByteCount = 0L;\n        firstAudioRtp = false;\n        firstAacFrame = false;\n        micSampleBytes = 0L;\n        closeMicCapture();\n        micSampleFile = new File(getExternalFilesDir(null), "cy01_mic_sample.aac");\n        if (micSampleFile.exists()) micSampleFile.delete();\n        for (int i = 0; i < nalCounts.length; i++) nalCounts[i] = 0;\n'''
r = require_replace(r, reset_old, reset_new, "v1.4 audio reset")

setup_old = '''            sessionId = parseSessionId(setup.header("session"));\n            log("RTSP Session=" + sessionId);\n            if (sessionId == null || sessionId.isEmpty()) throw new IllegalStateException("SETUP response has no Session header");\n\n            Map<String, String> playHeaders = new HashMap<>();\n'''
setup_new = '''            sessionId = parseSessionId(setup.header("session"));\n            log("RTSP Session=" + sessionId);\n            if (sessionId == null || sessionId.isEmpty()) throw new IllegalStateException("SETUP response has no Session header");\n\n            String audioTrackUri = buildTrackUri(contentBase, "track2");\n            log("Audio control URI = " + audioTrackUri + " (CY01 SDP: MPEG4-GENERIC/8000 mono)");\n            Map<String, String> audioSetupHeaders = new HashMap<>();\n            audioSetupHeaders.put("Transport", "RTP/AVP/TCP;unicast;interleaved=2-3");\n            audioSetupHeaders.put("Session", sessionId);\n            RtspResponse audioSetup = transact(in, out, "SETUP", audioTrackUri, audioSetupHeaders);\n            log("SETUP track2 AUDIO TCP interleaved -> " + audioSetup.statusLine);\n            log("AUDIO SETUP Transport=" + audioSetup.header("transport"));\n            boolean audioTrackReady = audioSetup.code == 200;\n            if (!audioTrackReady) log("MIC TEST: track2 setup failed; video will continue without microphone capture");\n\n            Map<String, String> playHeaders = new HashMap<>();\n'''
r = require_replace(r, setup_old, setup_new, "audio track SETUP")

play_old = '''            if (play.code != 200) throw new IllegalStateException("PLAY failed: " + play.statusLine);\n\n            status("PLAY accepted. Waiting for interleaved H.264 RTP...");\n            readInterleaved(in);\n'''
play_new = '''            if (play.code != 200) throw new IllegalStateException("PLAY failed: " + play.statusLine);\n\n            if (audioTrackReady) {\n                startMicCapture(12000L);\n                log("MIC TEST armed: speak normally for the first ~10 seconds; 12-second AAC sample will be saved automatically");\n            }\n            status(audioTrackReady\n                    ? "LIVE video + microphone track2. Speak for 10 s, then tap PLAY MIC SAMPLE."\n                    : "PLAY accepted. Video only; microphone track2 SETUP failed.");\n            readInterleaved(in);\n'''
r = require_replace(r, play_old, play_new, "audio capture start")

interleaved_old = '''                if (channel == 0) handleRtp(packet);\n                // channel 1 is RTCP and intentionally ignored in this video-only proof.\n'''
interleaved_new = '''                if (channel == 0) handleRtp(packet);\n                else if (channel == 2) handleAudioRtp(packet);\n                // channel 1 = video RTCP, channel 3 = audio RTCP; both intentionally ignored.\n'''
r = require_replace(r, interleaved_old, interleaved_new, "audio RTP channel")

marker = '''    private void handleRtp(byte[] packet) {\n'''
audio_methods = r'''    private void startMicCapture(long durationMs) {
        closeMicCapture();
        try {
            if (micSampleFile == null) micSampleFile = new File(getExternalFilesDir(null), "cy01_mic_sample.aac");
            micSampleOut = new FileOutputStream(micSampleFile, false);
            micCaptureDeadlineMs = System.currentTimeMillis() + durationMs;
            micSampleBytes = 0L;
            log("MIC CAPTURE started: " + micSampleFile.getAbsolutePath() + " durationMs=" + durationMs);
        } catch (Exception e) {
            log("MIC CAPTURE start failed: " + errorText(e));
            closeMicCapture();
        }
    }

    private synchronized void closeMicCapture() {
        FileOutputStream out = micSampleOut;
        micSampleOut = null;
        micCaptureDeadlineMs = 0L;
        if (out != null) {
            try { out.flush(); } catch (Exception ignored) {}
            try { out.close(); } catch (Exception ignored) {}
        }
    }

    private void finishMicCaptureIfDue() {
        if (micSampleOut == null || micCaptureDeadlineMs <= 0L) return;
        if (System.currentTimeMillis() < micCaptureDeadlineMs) return;
        closeMicCapture();
        log("MIC CAPTURE complete: frames=" + audioAacFrameCount
                + " sampleBytes=" + micSampleBytes
                + " file=" + (micSampleFile == null ? "" : micSampleFile.getAbsolutePath()));
        status("Mic sample captured. Tap PLAY MIC SAMPLE to hear the glasses microphone.");
    }

    private void handleAudioRtp(byte[] packet) {
        if (packet == null || packet.length < 12) return;
        int b0 = packet[0] & 0xFF;
        int b1 = packet[1] & 0xFF;
        if ((b0 >> 6) != 2) return;
        int payloadType = b1 & 0x7F;
        if (payloadType != 97) return;
        boolean padding = (b0 & 0x20) != 0;
        boolean extension = (b0 & 0x10) != 0;
        int cc = b0 & 0x0F;
        int off = 12 + cc * 4;
        if (off > packet.length) return;
        if (extension) {
            if (off + 4 > packet.length) return;
            int words = ((packet[off + 2] & 0xFF) << 8) | (packet[off + 3] & 0xFF);
            off += 4 + words * 4;
            if (off > packet.length) return;
        }
        int end = packet.length;
        if (padding && end > off) {
            int pad = packet[end - 1] & 0xFF;
            if (pad > 0 && pad <= end - off) end -= pad;
        }
        if (end - off < 4) return;

        audioRtpPacketCount++;
        if (!firstAudioRtp) {
            firstAudioRtp = true;
            log("FIRST MICROPHONE RTP AUDIO packet: PT=97 payloadBytes=" + (end - off));
        }

        int auHeaderBits = ((packet[off] & 0xFF) << 8) | (packet[off + 1] & 0xFF);
        int auHeaderBytes = (auHeaderBits + 7) / 8;
        if (auHeaderBits < 16 || off + 2 + auHeaderBytes > end) return;
        int h = ((packet[off + 2] & 0xFF) << 8) | (packet[off + 3] & 0xFF);
        int auSize = (h >> 3) & 0x1FFF; // RFC3640 sizeLength=13, indexLength=3
        int dataOff = off + 2 + auHeaderBytes;
        if (auSize <= 0 || dataOff + auSize > end) return;

        audioAacFrameCount++;
        audioAacByteCount += auSize;
        if (!firstAacFrame) {
            firstAacFrame = true;
            log("MICROPHONE AAC FRAME CONFIRMED from CY01 track2: bytes=" + auSize + " sampleRate=8000 mono");
        }

        FileOutputStream out = micSampleOut;
        if (out != null && System.currentTimeMillis() <= micCaptureDeadlineMs) {
            try {
                byte[] adts = buildAdtsHeader(auSize);
                out.write(adts);
                out.write(packet, dataOff, auSize);
                micSampleBytes += adts.length + auSize;
            } catch (Exception e) {
                log("MIC CAPTURE write failed safely: " + errorText(e));
                closeMicCapture();
            }
        }
        finishMicCaptureIfDue();
    }

    private byte[] buildAdtsHeader(int aacPayloadSize) {
        final int profile = 1;      // AAC LC in ADTS (AudioObjectType 2 minus 1)
        final int freqIdx = 11;     // 8000 Hz
        final int chanCfg = 1;      // mono
        int frameLength = aacPayloadSize + 7;
        byte[] h = new byte[7];
        h[0] = (byte) 0xFF;
        h[1] = (byte) 0xF1;
        h[2] = (byte) ((profile << 6) | (freqIdx << 2) | (chanCfg >> 2));
        h[3] = (byte) (((chanCfg & 3) << 6) | ((frameLength >> 11) & 0x03));
        h[4] = (byte) ((frameLength >> 3) & 0xFF);
        h[5] = (byte) (((frameLength & 7) << 5) | 0x1F);
        h[6] = (byte) 0xFC;
        return h;
    }

    private void playMicSample() {
        if (micSampleOut != null) {
            log("PLAY MIC SAMPLE blocked: automatic mic capture is still running; wait a few seconds");
            return;
        }
        if (micSampleFile == null || !micSampleFile.exists() || micSampleFile.length() < 16) {
            log("PLAY MIC SAMPLE: no captured AAC sample yet");
            status("No mic sample yet. Start LIVE and speak for the first 10 seconds.");
            return;
        }
        try {
            stopMicPlayback();
            MediaPlayer p = new MediaPlayer();
            micPlayer = p;
            p.setDataSource(micSampleFile.getAbsolutePath());
            p.setOnCompletionListener(mp -> {
                log("MIC SAMPLE playback completed");
                stopMicPlayback();
            });
            p.setOnErrorListener((mp, what, extra) -> {
                log("MIC SAMPLE playback error what=" + what + " extra=" + extra);
                stopMicPlayback();
                return true;
            });
            p.prepare();
            p.start();
            log("MIC SAMPLE playback started, bytes=" + micSampleFile.length());
            status("Playing captured glasses microphone sample...");
        } catch (Exception e) {
            log("MIC SAMPLE playback failed: " + errorText(e));
            stopMicPlayback();
        }
    }

    private void stopMicPlayback() {
        MediaPlayer p = micPlayer;
        micPlayer = null;
        if (p != null) {
            try { p.stop(); } catch (Exception ignored) {}
            try { p.release(); } catch (Exception ignored) {}
        }
    }

'''
r = require_replace(r, marker, audio_methods + marker, "v1.4 audio methods")

stats_old = '''                "LIVE STATS: %.1fs RTP=%d AU=%d decoded=%d avgFPS=%.1f sourceFPS10s=%.1f decodedFPS10s=%.1f video=%.2fMbps battery=%s SPS=%d PPS=%d IDR=%d resyncBytes=%d recoveries=%d",\n                seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps, sourceFps10s, decodedFps10s,\n                mbps, batteryText, nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount));\n'''
stats_new = '''                "LIVE STATS: %.1fs RTP=%d AU=%d decoded=%d avgFPS=%.1f sourceFPS10s=%.1f decodedFPS10s=%.1f video=%.2fMbps battery=%s audioRTP=%d audioAAC=%d SPS=%d PPS=%d IDR=%d resyncBytes=%d recoveries=%d",\n                seconds, rtpPacketCount, accessUnitCount, decodedOutputCount, fps, sourceFps10s, decodedFps10s,\n                mbps, batteryText, audioRtpPacketCount, audioAacFrameCount, nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount));\n'''
r = require_replace(r, stats_old, stats_new, "v1.4 audio stats")

report_old = '''                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d decoderRecoveries=%d\\n\\n",\n'''
report_new = '''                        + "audioRTP=%d audioAAC=%d audioBytes=%d micSampleBytes=%d\\n"\n                        + "NAL SPS=%d PPS=%d IDR=%d resyncBytes=%d decoderRecoveries=%d\\n\\n",\n'''
r = require_replace(r, report_old, report_new, "v1.4 report audio label")
report_args_old = '''                startBattery, battery, MainActivityV03.latestBatteryCharging,\n                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount);\n'''
report_args_new = '''                startBattery, battery, MainActivityV03.latestBatteryCharging,\n                audioRtpPacketCount, audioAacFrameCount, audioAacByteCount, micSampleBytes,\n                nalCounts[7], nalCounts[8], nalCounts[5], interleavedResyncBytes, decoderRecoveryCount);\n'''
r = require_replace(r, report_args_old, report_args_new, "v1.4 report audio args")

stop_old = '''    private void stopRawTest() {\n        running = false;\n'''
stop_new = '''    private void stopRawTest() {\n        closeMicCapture();\n        stopMicPlayback();\n        running = false;\n'''
r = require_replace(r, stop_old, stop_new, "v1.4 stop mic resources")

raw.write_text(r)
print("v1.4 RTSP microphone capture/playback preparation complete")
