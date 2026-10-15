from pathlib import Path
import runpy

# v2.4: field-driven transport framing fix + explicit mic-mode handoff.
# Base on the last proven v2.2 preparation chain, then apply v2.4 directly.
runpy.run_path("tools/prepare_v22.py", run_name="__main__")

def rr(text, old, new, label, count=1):
    if old not in text:
        raise SystemExit(label + " not found")
    return text.replace(old, new, count)

# Version/package bump.
g = Path("app/build.gradle")
s = g.read_text()
s = rr(s, "applicationId 'com.vk.cy01streamlab22'", "applicationId 'com.vk.cy01streamlab24'", "v2.4 app id")
s = rr(s, "versionCode 2200", "versionCode 2400", "v2.4 version code")
s = rr(s, "versionName '2.2.0'", "versionName '2.4.0'", "v2.4 version name")
g.write_text(s)

# Main BLE/P2P orchestrator.
p = Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java")
s = p.read_text()
s = s.replace("CY01 Live v2.2 started", "CY01 Live v2.4 started")
s = s.replace("CY01 Live v2.2", "CY01 Live v2.4")
s = s.replace("CY01StreamLab-OneTap/2.2", "CY01StreamLab-OneTap/2.4")
s = s.replace("v2.2: no explicit Android Network binding", "v2.4: no explicit Android Network binding")
s = s.replace("v2.2 will NOT bind sockets", "v2.4 will NOT bind sockets")

old_exclusive = """    private void startExclusiveBleMicProbe(long durationMs) {
        if (!bleReady) {
            log("BLE MIC EXCLUSIVE blocked: BLE channel is not ready");
            return;
        }
        log("BLE MIC EXCLUSIVE: stopping preview mode [02 01 15 01] before speech recognition");
        sendFrame(0x41, new byte[]{0x02, 0x01, 0x15, 0x01});
        main.postDelayed(() -> {
            log("BLE MIC EXCLUSIVE: preview stop settling complete; starting speech recognition");
            startBleMicProbe(durationMs);
        }, 900L);
    }
"""
new_exclusive = """    private void startExclusiveBleMicProbe(long durationMs) {
        if (!bleReady) {
            log("BLE MIC EXCLUSIVE blocked: BLE channel is not ready");
            return;
        }

        log("BLE MIC EXCLUSIVE: stopping live preview before speech recognition");
        sendFrame(0x41, new byte[]{0x02, 0x01, 0x15, 0x01});

        final Runnable enterMicMode = () -> {
            if (!bleReady) {
                log("BLE MIC EXCLUSIVE aborted: BLE channel dropped during Wi-Fi handoff");
                return;
            }
            log("BLE MIC EXCLUSIVE: disabling Wi-Fi transfer mode [02 01 09]");
            sendFrame(0x41, new byte[]{0x02, 0x01, 0x09});
            main.postDelayed(() -> {
                if (!bleReady) {
                    log("BLE MIC EXCLUSIVE aborted: BLE channel dropped before speech command");
                    return;
                }
                log("BLE MIC EXCLUSIVE: P2P released; starting speech recognition [02 01 07]");
                startBleMicProbe(durationMs);
            }, 450L);
        };

        if (p2pManager != null && p2pChannel != null && p2pConnected) {
            log("BLE MIC EXCLUSIVE: releasing active Wi-Fi Direct group before microphone mode");
            p2pManager.removeGroup(p2pChannel, new WifiP2pManager.ActionListener() {
                @Override public void onSuccess() {
                    p2pConnected = false;
                    log("BLE MIC EXCLUSIVE: Wi-Fi Direct group released");
                    main.postDelayed(enterMicMode, 250L);
                }
                @Override public void onFailure(int reason) {
                    log("BLE MIC EXCLUSIVE: removeGroup=" + p2pReason(reason)
                            + " (" + reason + "); continuing with transfer-stop command");
                    main.postDelayed(enterMicMode, 250L);
                }
            });
        } else {
            main.postDelayed(enterMicMode, 250L);
        }
    }
"""
s = rr(s, old_exclusive, new_exclusive, "v2.4 mic P2P handoff")

old_73 = """        if (opcode == 0x73) {
            if (payload.length >= 2 && (payload[0] & 0xFF) == 0x03 && (payload[1] & 0xFF) == 0x01) {
                bleMicStartedEvent = true;
                log("BLE MICROPHONE START EVENT confirmed: cmd 0x73 payload=03-01");
            }
            return;
        }
"""
new_73 = """        if (opcode == 0x73) {
            if (bleMicProbeRunning) {
                log("BLE MIC DATA_REPORT 0x73 payload=" + hex(payload));
            }
            boolean micStarted = false;
            for (int i = 0; i + 1 < payload.length; i++) {
                if ((payload[i] & 0xFF) == 0x03 && (payload[i + 1] & 0xFF) == 0x01) {
                    micStarted = true;
                    break;
                }
            }
            if (micStarted) {
                bleMicStartedEvent = true;
                log("BLE MICROPHONE START EVENT confirmed: cmd 0x73 contains 03-01");
            }
            return;
        }
"""
s = rr(s, old_73, new_73, "v2.4 robust 0x73 event parser")
p.write_text(s)

# Raw RTSP/RTP/H264 path.
p = Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java")
r = p.read_text()
r = r.replace("CY01 LIVE v2.2 started", "CY01 LIVE v2.4 started")
r = r.replace("CY01 LIVE VIDEO v2.2", "CY01 LIVE VIDEO v2.4")
r = r.replace("CY01StreamLab-Raw/2.2", "CY01StreamLab-Raw/2.4")
r = r.replace("CY01 LIVE v2.2 compact report", "CY01 LIVE v2.4 compact report")
r = r.replace("MIC TEST v2.2:", "MIC TEST v2.4:")

# Root-cause fix: do not abandon an interleaved RTP payload when SO_TIMEOUT fires
# after some bytes were already received. v2.3 field logs showed byte-scan resyncs
# immediately before hard freezes; losing the partial frame shifts the TCP parser.
old_read = """    private byte[] readExactly(InputStream in, int length) throws Exception {
        if (length <= 0) return new byte[0];
        byte[] data = new byte[length];
        int off = 0;
        while (off < length) {
            int n = in.read(data, off, length - off);
            if (n < 0) throw new EOFException("EOF after " + off + "/" + length + " bytes");
            off += n;
        }
        return data;
    }
"""
new_read = """    private byte[] readExactly(InputStream in, int length) throws Exception {
        if (length <= 0) return new byte[0];
        byte[] data = new byte[length];
        int off = 0;
        int timeoutCount = 0;
        while (off < length) {
            try {
                int n = in.read(data, off, length - off);
                if (n < 0) throw new EOFException("EOF after " + off + "/" + length + " bytes");
                off += n;
                timeoutCount = 0;
            } catch (SocketTimeoutException timeout) {
                timeoutCount++;
                if (off > 0) {
                    partialFrameTimeoutCount++;
                    partialFrameTimeoutBytes = Math.max(partialFrameTimeoutBytes, off);
                    if (partialFrameTimeoutCount <= 5) {
                        log("RTSP partial-frame timeout preserved: " + off + "/" + length
                                + " bytes; continuing same interleaved frame");
                    }
                }
                if (timeoutCount >= 4) {
                    throw new SocketTimeoutException("Timed out completing framed read "
                            + off + "/" + length + " bytes");
                }
            }
        }
        return data;
    }
"""
r = rr(r, old_read, new_read, "v2.4 partial-frame-safe readExactly")

field = """    private long interleavedResyncBytes;
"""
field_new = field + """    private long partialFrameTimeoutCount;
    private long partialFrameTimeoutBytes;
    private long framingLossCount;
"""
r = rr(r, field, field_new, "v2.4 transport diagnostics fields")

reset = """        interleavedResyncBytes = 0;
"""
reset_new = reset + """        partialFrameTimeoutCount = 0L;
        partialFrameTimeoutBytes = 0L;
        framingLossCount = 0L;
"""
r = rr(r, reset, reset_new, "v2.4 transport diagnostics reset")

# Never scan arbitrary H264/AAC bytes for '$'. If framing is truly lost, fail the
# session cleanly instead of manufacturing a new boundary from binary payload.
old_resync = """                if (marker != '$') {
                    // We expect only RFC2326 interleaved RTP/RTCP after PLAY. If framing is ever
                    // lost, do not interpret binary H.264 as text (which previously flooded logs);
                    // scan forward to the next interleaved frame marker and continue.
                    long skipped = 1;
                    int b = marker;
                    while (running && b >= 0 && b != '$' && skipped < 65536) {
                        b = in.read();
                        if (b != '$') skipped++;
                    }
                    interleavedResyncBytes += skipped;
                    if (interleavedResyncBytes == skipped || interleavedResyncBytes % 65536 < skipped) {
                        log("RTSP interleaved resync: skipped binary/non-framed bytes=" + skipped
                                + " total=" + interleavedResyncBytes);
                    }
                    if (b < 0) throw new EOFException("RTSP/RTP socket closed during resync");
                    if (b != '$') continue;
                }
"""
new_resync = """                if (marker != '$') {
                    framingLossCount++;
                    throw new IllegalStateException("RTSP interleaved framing lost at marker=0x"
                            + Integer.toHexString(marker & 0xFF)
                            + "; refusing destructive byte-scan resync");
                }
"""
r = rr(r, old_resync, new_resync, "v2.4 remove destructive resync")

# Make mic mode explicit in the UI instead of displaying a misleading frozen camera frame.
mic_note = """        log("MIC TEST v2.4: M02S camera/mic are exclusive; RTSP EOF is expected during BLE mic window");
        preserveGoodSessionSummary();
"""
mic_note_new = """        log("MIC TEST v2.4: M02S camera/mic are exclusive; RTSP EOF is expected during BLE mic window");
        preserveGoodSessionSummary();
        main.post(() -> {
            if (surfaceView != null) surfaceView.setAlpha(0f);
            status("MICROPHONE MODE: camera is intentionally paused by the glasses.");
        });
"""
r = rr(r, mic_note, mic_note_new, "v2.4 mic visual state")

recovery_log = """            log("MIC->CAMERA recovery handoff complete; restarting RTSP at " + baseUri);
"""
recovery_log_new = """            if (surfaceView != null) surfaceView.setAlpha(1f);
            log("MIC->CAMERA recovery handoff complete; restarting RTSP at " + baseUri);
"""
r = rr(r, recovery_log, recovery_log_new, "v2.4 restore video surface")

timeout_log = """            log("MIC->CAMERA recovery timed out waiting for rebuilt /ch0 route");
"""
timeout_log_new = """            if (surfaceView != null) surfaceView.setAlpha(1f);
            log("MIC->CAMERA recovery timed out waiting for rebuilt /ch0 route");
"""
r = rr(r, timeout_log, timeout_log_new, "v2.4 recovery timeout surface")

# Extend compact report so the next physical run distinguishes transport timeouts
# from actual decoder stalls.
old_report = """                        + "smooth rtpMaxGapMs=%d rtpGap100=%d frameMaxGapMs=%d frameGap100=%d frameStall250=%d earlyFrames=%d earlyBytes=%d\\n"
                        + "previousGood=%s\\n"
"""
new_report = """                        + "smooth rtpMaxGapMs=%d rtpGap100=%d frameMaxGapMs=%d frameGap100=%d frameStall250=%d earlyFrames=%d earlyBytes=%d\\n"
                        + "transport partialTimeouts=%d partialMaxBytes=%d framingLoss=%d\\n"
                        + "previousGood=%s\\n"
"""
r = rr(r, old_report, new_report, "v2.4 transport report labels")

old_args = """                renderedStallOver250Count, earlyInterleavedFrameCount, earlyInterleavedByteCount,
                previousGoodSession.isEmpty() ? "none" : previousGoodSession,
"""
new_args = """                renderedStallOver250Count, earlyInterleavedFrameCount, earlyInterleavedByteCount,
                partialFrameTimeoutCount, partialFrameTimeoutBytes, framingLossCount,
                previousGoodSession.isEmpty() ? "none" : previousGoodSession,
"""
r = rr(r, old_args, new_args, "v2.4 transport report args")

p.write_text(r)
print("v2.4 prepared: partial-frame-safe RTSP + explicit mic P2P handoff + mic UI state")
