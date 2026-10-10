from pathlib import Path
import runpy

# v2.5: field fix for RTSP-over-TCP parser. CY01 may emit ASCII RTSP control
# messages between interleaved RTP frames; v2.4 treated the first 'R'/'M' as fatal.
runpy.run_path("tools/prepare_v24_ci.py", run_name="__main__")

def rr(t,o,n,l):
    if o not in t: raise SystemExit(l+" not found")
    return t.replace(o,n,1)

g=Path("app/build.gradle"); s=g.read_text()
s=rr(s,"applicationId 'com.vk.cy01streamlab24'","applicationId 'com.vk.cy01streamlab25'","id")
s=rr(s,"versionCode 2400","versionCode 2500","code")
s=rr(s,"versionName '2.4.0'","versionName '2.5.0'","name"); g.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java"); s=p.read_text()
s=s.replace("CY01 Live v2.4 started","CY01 Live v2.5 started").replace("CY01 Live v2.4","CY01 Live v2.5").replace("CY01StreamLab-OneTap/2.4","CY01StreamLab-OneTap/2.5")
s=s.replace("v2.4: no explicit Android Network binding","v2.5: no explicit Android Network binding").replace("v2.4 will NOT bind sockets","v2.5 will NOT bind sockets")
p.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java"); r=p.read_text()
r=r.replace("CY01 LIVE v2.4 started","CY01 LIVE v2.5 started").replace("CY01 LIVE VIDEO v2.4","CY01 LIVE VIDEO v2.5").replace("CY01StreamLab-Raw/2.4","CY01StreamLab-Raw/2.5").replace("CY01 LIVE v2.4 compact report","CY01 LIVE v2.5 compact report").replace("MIC TEST v2.4:","MIC TEST v2.5:")

old='''                if (marker != '$') {
                    framingLossCount++;
                    throw new IllegalStateException("RTSP interleaved framing lost at marker=0x"
                            + Integer.toHexString(marker & 0xFF)
                            + "; refusing destructive byte-scan resync");
                }
'''
new='''                if (marker != '$') {
                    if (marker == 'R' || marker == 'S' || marker == 'O' || marker == 'G' || marker == 'M') {
                        ByteArrayOutputStream control = new ByteArrayOutputStream(1024);
                        control.write(marker);
                        int state = 0;
                        while (control.size() < 32768) {
                            int b = in.read();
                            if (b < 0) throw new EOFException("EOF in interleaved RTSP control message");
                            control.write(b);
                            if (state == 0 && b == '\\r') state = 1;
                            else if (state == 1 && b == '\\n') state = 2;
                            else if (state == 2 && b == '\\r') state = 3;
                            else if (state == 3 && b == '\\n') break;
                            else state = b == '\\r' ? 1 : 0;
                        }
                        String controlText = control.toString(StandardCharsets.US_ASCII.name());
                        String firstLine = controlText.split("\\r\\n", 2)[0];
                        log("RTSP interleaved control message: " + firstLine);
                        continue;
                    }
                    framingLossCount++;
                    throw new IllegalStateException("RTSP interleaved framing lost at marker=0x"
                            + Integer.toHexString(marker & 0xFF));
                }
'''
r=rr(r,old,new,"interleaved control parser")

# Preserve RTSP interleaved header bytes across socket timeouts. A timeout after
# consuming channel/length previously left the parser one or two bytes off.
r = rr(r,
'''                int channel = in.read();
                int hi = in.read();
                int lo = in.read();
                if (channel < 0 || hi < 0 || lo < 0) throw new EOFException("EOF in interleaved header");
                int length = (hi << 8) | lo;
''',
'''                byte[] frameHeader = readExactly(in, 3);
                int channel = frameHeader[0] & 0xff;
                int length = ((frameHeader[1] & 0xff) << 8) | (frameHeader[2] & 0xff);
''',
"timeout-safe interleaved frame header")

r = rr(r,
'''                int channel = in.read();
                int hi = in.read();
                int lo = in.read();
                if (channel < 0 || hi < 0 || lo < 0) {
                    throw new EOFException("EOF in early interleaved RTP header");
                }
                int length = (hi << 8) | lo;
''',
'''                byte[] earlyFrameHeader = readExactly(in, 3);
                int channel = earlyFrameHeader[0] & 0xff;
                int length = ((earlyFrameHeader[1] & 0xff) << 8) | (earlyFrameHeader[2] & 0xff);
''',
"timeout-safe early RTP frame header")
# Post-PLAY RTSP control messages are multiplexed with interleaved RTP.
# Skip only known keepalive line breaks; reject invalid start-lines,
# consume any declared RTSP body, and bound the control header size.
r = rr(r,
r'''                if (marker != '$') {
                    if (marker == 'R' || marker == 'S' || marker == 'O' || marker == 'G' || marker == 'M') {
''',
r'''                if (marker != '$') {
                    if (marker == '\r' || marker == '\n') continue;
                    if (marker == 'R' || marker == 'S' || marker == 'O' || marker == 'G' || marker == 'M') {
''',
"skip interleaved RTSP keepalive blank lines")

r = rr(r,
r'''                        String controlText = control.toString(StandardCharsets.US_ASCII.name());
''',
r'''                        if (control.size() >= 32768) {
                            throw new IllegalStateException("Post-PLAY RTSP control header exceeds 32768 bytes");
                        }
                        String controlText = control.toString(StandardCharsets.US_ASCII.name());
''',
"reject truncated RTSP control header")

r = rr(r,
r'''                        log("RTSP interleaved control message: " + firstLine);
                        continue;
''',
r'''                        if (!(firstLine.startsWith("RTSP/")
                                || firstLine.startsWith("OPTIONS ")
                                || firstLine.startsWith("GET_PARAMETER ")
                                || firstLine.startsWith("SET_PARAMETER ")
                                || firstLine.startsWith("REDIRECT ")
                                || firstLine.startsWith("ANNOUNCE ")
                                || firstLine.startsWith("RECORD ")
                                || firstLine.startsWith("PLAY_NOTIFY "))) {
                            framingLossCount++;
                            throw new IllegalStateException("Non-RTSP post-PLAY data at frame boundary: "
                                    + firstLine.substring(0, Math.min(firstLine.length(), 96)));
                        }
                        int controlBodyLength = 0;
                        for (String controlLine : controlText.split("\\r\\n")) {
                            int colon = controlLine.indexOf(':');
                            if (colon > 0 && controlLine.substring(0, colon).trim()
                                    .equalsIgnoreCase("Content-Length")) {
                                try {
                                    controlBodyLength = Integer.parseInt(controlLine.substring(colon + 1).trim());
                                } catch (NumberFormatException invalid) {
                                    throw new IllegalStateException("Invalid RTSP control Content-Length", invalid);
                                }
                            }
                        }
                        if (controlBodyLength < 0 || controlBodyLength > 1048576) {
                            throw new IllegalStateException("RTSP control body out of bounds: " + controlBodyLength);
                        }
                        if (controlBodyLength != 0) readExactly(in, controlBodyLength);
                        log("RTSP interleaved control message: " + firstLine
                                + " bodyBytes=" + controlBodyLength);
                        continue;
''',
"consume control RTSP body and validate start line")

p.write_text(r)
print("v2.5 prepared: bounded RTSP control multiplex parser and timeout-safe interleaved headers")

# v2.5.2 field repair: preserve LIVE, terminate damaged reads, bounded reconnect.
g=Path('app/build.gradle'); s=g.read_text().replace('versionCode 2500','versionCode 2502').replace("versionName '2.5.0'", "versionName '2.5.2'"); g.write_text(s)
p=Path('app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java'); s=p.read_text(); s=s.replace('CY01 Live v2.5.1','CY01 Live v2.5.2').replace('CY01 Live v2.5 started','CY01 Live v2.5.2 started'); p.write_text(s)
p=Path('app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java'); r=p.read_text()
r=r.replace('CY01 LIVE v2.5', 'CY01 LIVE v2.5.2')
r=rr(r, '    private volatile boolean running;', '''    private volatile boolean running;
    private volatile long streamEndMs;
    private volatile int stopEpoch;
    private int transportRetries;
    private String previousTransportFailure = "none";''', 'recovery fields')
r=rr(r, '    private void startRawTest() {', '''    private void startRawTest() {
        if (running) return;
        transportRetries = 0;
        startRawSession();
    }

    private void startRawSession() {''', 'manual start')
r=rr(r, '        resetStreamState();', '        stopEpoch++;\n        resetStreamState();', 'invalidate pending retry')
r=rr(r, '        streamStartMs = System.currentTimeMillis();', '        streamEndMs = 0L;\n        streamStartMs = System.currentTimeMillis();', 'reset end time')
r=rr(r, '        Socket socket = null;\n        try {', '        Socket socket = null;\n        boolean retryTransport = false;\n        final int epoch = stopEpoch;\n        try {', 'retry session scope')
r=rr(r, '                    log("RAW SESSION ERROR: " + errorText(e));', '''                    retryTransport = true;
                    previousTransportFailure = errorText(e);
                    log("RAW SESSION ERROR: " + previousTransportFailure);''', 'retry on failed connection')
r=rr(r, '        } finally {\n            running = false;', '        } finally {\n            streamEndMs = System.currentTimeMillis();\n            running = false;', 'freeze end')
r=rr(r, '                    + " NAL[IDR]=" + nalCounts[5]);\n        }', '''                    + " NAL[IDR]=" + nalCounts[5]);
            if (retryTransport && epoch == stopEpoch && !micTransitionExpected) {
                preserveGoodSessionSummary();
                if (transportRetries < 2) {
                    transportRetries++;
                    log("RTSP reconnect scheduled: attempt=" + transportRetries + "/2; previous=" + previousTransportFailure);
                    main.postDelayed(() -> {
                        if (epoch == stopEpoch && !running && surfaceReady && !isFinishing()) {
                            startRawSession();
                        }
                    }, 1000L * transportRetries);
                } else {
                    status("Соединение потеряно. Две попытки восстановления завершились ошибкой.");
                }
            }
        }''', 'bounded recovery')
# Only an idle timeout BEFORE the next marker can safely restart the loop.
r=rr(r, '                int marker = in.read();', '''                int marker;
                try {
                    marker = in.read();
                } catch (SocketTimeoutException idle) {
                    timeoutCount++;
                    drainDecoder();
                    if (timeoutCount >= 4) throw new EOFException("RTSP idle for four read deadlines");
                    continue;
                }
                timeoutCount = 0;''', 'idle boundary')
r=rr(r, '''                timeoutCount++;
                if (timeoutCount <= 3 || timeoutCount % 5 == 0) {
                    log("Waiting for RTP... socket timeout #" + timeoutCount);
                }''', '''                // Never resume at a marker after abandoning a partially consumed frame.
                throw new java.io.IOException("Incomplete RTSP frame/control message; reconnect required", timeout);''', 'partial timeout terminal')
r=r.replace("marker == 'G' || marker == 'M'", "marker == 'G' || marker == 'M' || marker == 'A' || marker == 'P'")
# The old control action deliberately removed P2P and produced zero audio in field logs.
# Do not repeat that destructive experiment as a normal microphone operation.
a=r.index('    private void startCombinedMicTest() {'); b=r.index('    private void pollCameraRecoveryReady()',a)
r=r[:a]+'''    private void startCombinedMicTest() {
        log("MICROPHONE MODE unavailable: simultaneous glasses audio is not established; LIVE preserved; no BLE mode switch sent");
        status("Микрофон очков пока недоступен. Видео продолжает работать.");
    }

'''+r[b:]
r=r.replace('START MIC TEST 10s', 'МИКРОФОН — НЕДОСТУПЕН')
r=r.replace('LIVE ready. Tap МИКРОФОН — НЕДОСТУПЕН, speak continuously, then inspect/play sample.', 'Видео работает. Микрофон очков пока недоступен.')
r=rr(r, '    private void stopRawTest() {', '    private void stopRawTest() {\n        stopEpoch++;\n        if (streamEndMs == 0L) streamEndMs = System.currentTimeMillis();', 'cancel retry')
r=rr(r, '    private void preserveGoodSessionSummary() {\n        if (!firstRendered || decodedOutputCount <= 0) return;\n        long now = System.currentTimeMillis();', '    private void preserveGoodSessionSummary() {\n        if (!firstRendered || decodedOutputCount <= 0) return;\n        long now = streamEndMs > 0L ? streamEndMs : System.currentTimeMillis();', 'freeze previous stats')
r=rr(r, '    private String buildCompactDiagnosticReport() {\n        long now = System.currentTimeMillis();', '    private String buildCompactDiagnosticReport() {\n        long now = streamEndMs > 0L ? streamEndMs : System.currentTimeMillis();', 'freeze report stats')
r=rr(r, '        String result = summary + diagnosticSnapshot();', '        summary += "transportRetries=" + transportRetries + " previousTransportFailure=" + previousTransportFailure + "\\n";\n        String result = summary + diagnosticSnapshot();', 'preserve failure report')
p.write_text(r)
print('v2.5.2 prepared: LIVE-safe mic guard, bounded RTSP reconnect, frozen end statistics')

# v2.6.3: use Android's Bluetooth communication input without BLE camera-mode commands.
g=Path('app/build.gradle');s=g.read_text().replace('versionCode 2502','versionCode 2603').replace("versionName '2.5.2'", "versionName '2.6.3'");g.write_text(s)
p=Path('app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java');s=p.read_text().replace('CY01 Live v2.5.2','CY01 Live v2.6.3');p.write_text(s)
p=Path('app/src/main/AndroidManifest.xml');s=p.read_text();s=s.replace('    <application','    <uses-permission android:name="android.permission.RECORD_AUDIO" />\n    <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />\n\n    <application',1);p.write_text(s)
p=Path('app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java');r=p.read_text()
r=r.replace('CY01 LIVE v2.5.2','CY01 LIVE v2.6.3').replace('CY01 LIVE VIDEO v2.5','CY01 LIVE VIDEO v2.6.3')
r=rr(r,'    private TextView statusView;', '    private GlassesAudioInput glassesAudio;\n    private TextView statusView;', 'audio input field')
r=rr(r,'        buildUi();','        buildUi();\n        glassesAudio = new GlassesAudioInput(this, text -> { log(text); status(text); });','create audio controller')
a=r.index('    private void startCombinedMicTest() {');b=r.index('    private void pollCameraRecoveryReady()',a)
r=r[:a]+'''    private void startCombinedMicTest() {
        glassesAudio.toggle();
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code == GlassesAudioInput.PERMISSION_REQUEST) {
            boolean granted = results.length > 0;
            for (int result : results) granted &= result == android.content.pm.PackageManager.PERMISSION_GRANTED;
            if (granted && !isFinishing()) glassesAudio.toggle();
            else status("Для микрофона нужно разрешение на запись звука и Bluetooth. Видео продолжает работать.");
        }
    }

    @Override
    protected void onStop() {
        if (glassesAudio != null) glassesAudio.stop();
        super.onStop();
    }

'''+r[b:]
r=r.replace('МИКРОФОН — НЕДОСТУПЕН','МИКРОФОН BLUETOOTH — ВКЛ / ВЫКЛ')
r=r.replace('root.addView(button("PLAY MIC SAMPLE", v -> playMicSample()));','root.addView(button("ПРОСЛУШАТЬ ПОСЛЕДНИЕ 10 СЕКУНД", v -> glassesAudio.playRecent()));')
r=r.replace('MIC TEST ready: RTSP track2 SETUP succeeded but capture waits for МИКРОФОН BLUETOOTH — ВКЛ / ВЫКЛ', 'Audio: RTSP track2 negotiated; Bluetooth microphone is a separate user-activated route')
r=r.replace('Видео работает. Микрофон очков пока недоступен.', 'Видео работает. Микрофон можно подключить кнопкой Bluetooth.')
r=rr(r,'    private void stopRawTest() {','    private void stopRawTest() {\n        if (glassesAudio != null) glassesAudio.stop();','stop audio on explicit video stop')
r=rr(r,'        String result = summary + diagnosticSnapshot();','        summary += (glassesAudio == null ? "bluetoothMic=not_initialized" : glassesAudio.snapshot()) + "\\n";\n        String result = summary + diagnosticSnapshot();','audio report')
# Record protocol metadata only, never video payload, at the next framing loss.
r=rr(r,'    private volatile long streamEndMs;','    private String lastWireFrame = "none";\n    private volatile long streamEndMs;','wire metadata')
r=rr(r,'        framingLossCount = 0L;','        framingLossCount = 0L;\n        lastWireFrame = "none";','wire metadata reset')
r=rr(r,'+ Integer.toHexString(marker & 0xFF));','+ Integer.toHexString(marker & 0xFF) + "; previous=" + lastWireFrame);','framing context')
r=rr(r,'''                byte[] packet = readExactly(in, length);
                handleInterleavedPacket(channel, packet);''','''                byte[] packet = readExactly(in, length);
                lastWireFrame = "channel=" + channel + " length=" + length
                        + (packet.length >= 4 ? " v=" + ((packet[0] & 255) >> 6)
                        + " pt=" + (packet[1] & 255) + " word2=" + (((packet[2]&255)<<8)|(packet[3]&255)) : " short");
                handleInterleavedPacket(channel, packet);''','wire frame metadata')
p.write_text(r)

print('v2.6.3 prepared: explicit Bluetooth microphone route independent of BLE preview control')

# Measure actual render timestamps, not delayed/batched UI callback arrival times.
r=rr(r, '                long renderedNow = System.currentTimeMillis();', '                if (mc != decoder || !running) return;\n                long renderedNow = nanoTime / 1_000_000L;', 'actual frame render timestamps')
r=rr(r, '        String result = summary + diagnosticSnapshot();', '        summary += "renderGapClock=MediaCodec.nanoTime\\n";\n        String result = summary + diagnosticSnapshot();', 'render clock report')
p.write_text(r)

# v2.6.3: bounded, validated boundary recovery plus truthful frozen-frame status.
r=rr(r, 'InputStream in = socket.getInputStream();', 'InputStream in = new java.io.BufferedInputStream(socket.getInputStream(), 65536);', 'buffer socket reads')
r=rr(r, '    private void readInterleaved(InputStream in) throws Exception {', '    private void readInterleaved(InputStream in) throws Exception {\n        in = new java.io.PushbackInputStream(in, RtpBoundaryRecovery.CAPACITY);', 'recovery replay buffer')
r=rr(r, '                    throw new IllegalStateException("RTSP interleaved framing lost at marker=0x"', '                    if (recoverFraming(in, marker)) continue;\n                    throw new IllegalStateException("RTSP interleaved framing lost at marker=0x"', 'validated recovery at binary boundary')
r=rr(r, '    private TextView statusView;', '    private TextView audioStatusView;\n    private TextView statusView;', 'separate audio status')
r=rr(r, 'text -> { log(text); status(text); }', 'text -> { log(text); audioStatusView.setText(text); }', 'audio must not hide video errors')
r=rr(r, '        root.addView(statusView);', '        root.addView(statusView);\n        audioStatusView = new TextView(this);\n        audioStatusView.setText("Микрофон выключен");\n        root.addView(audioStatusView);', 'audio status view')
r=r.replace('ПРОСЛУШАТЬ ПОСЛЕДНИЕ 10 СЕКУНД', 'ПРОСЛУШАТЬ ЗАПИСЬ')
r=rr(r, '    private String lastWireFrame = "none";', '    private long wireSsrc = -1L, boundaryRecoveries, boundarySkippedBytes;\n    private int wireSeq = -1, wirePt = -1, nextFuSeq = -1;\n    private boolean waitingRecoveryIdr;\n    private long lastRenderCallbackMs, maxRenderCallbackGapMs;\n    private String lastWireFrame = "none";', 'recovery state')
r=rr(r, '        lastWireFrame = "none";', '        lastWireFrame = "none";\n        wireSsrc=-1L; wireSeq=-1; wirePt=-1; nextFuSeq=-1; waitingRecoveryIdr=false;\n        boundaryRecoveries=0; boundarySkippedBytes=0;\n        lastRenderCallbackMs=0; maxRenderCallbackGapMs=0;', 'reset recovery state')
r=rr(r, '        if (channel == 0) handleRtp(packet);', '        if (channel == 0) {\n            if(packet.length>=12 && ((packet[0]&255)>>6)==2) {\n                wireSsrc=((long)(packet[8]&255)<<24)|((long)(packet[9]&255)<<16)|((long)(packet[10]&255)<<8)|(packet[11]&255);\n                wireSeq=((packet[2]&255)<<8)|(packet[3]&255); wirePt=packet[1]&127;\n            }\n            handleRtp(packet);\n        }', 'remember video RTP identity')
r=rr(r, '        if (start) {\n            fuBuffer.reset();', '        if (!start && fuActive && seq != nextFuSeq) { fuBuffer.reset(); fuActive=false; return; }\n        nextFuSeq=(seq+1)&65535;\n        if (start) {\n            fuBuffer.reset();', 'reject missing FU fragments')
r=rr(r, '        int type = nal[0] & 0x1F;', '        int type = nal[0] & 0x1F;\n        if (waitingRecoveryIdr && type >= 1 && type <= 4) return;\n        if (type == 5) waitingRecoveryIdr=false;', 'wait for clean keyframe')
r=rr(r, '                long renderedNow = nanoTime / 1_000_000L;', '                long callbackNow=android.os.SystemClock.elapsedRealtime();\n                if(lastRenderCallbackMs>0) maxRenderCallbackGapMs=Math.max(maxRenderCallbackGapMs, callbackNow-lastRenderCallbackMs);\n                lastRenderCallbackMs=callbackNow;\n                long renderedNow = nanoTime / 1_000_000L;', 'callback liveness independent of codec clock')
r=rr(r, '        String result = summary + diagnosticSnapshot();', '        summary += "boundaryRecoveries="+boundaryRecoveries+" boundarySkippedBytes="+boundarySkippedBytes+" waitingIdr="+waitingRecoveryIdr+"\\n";\n        summary += "renderCallbackMaxGapMs="+maxRenderCallbackGapMs+" renderCallbackAgeMs="+(lastRenderCallbackMs==0 ? -1 : android.os.SystemClock.elapsedRealtime()-lastRenderCallbackMs)+"\\n";\n        String result = summary + diagnosticSnapshot();', 'recovery and liveness report')
# Method is outside the extracted legacy parser fixture; its pure-Java scanner is tested separately.
where=r.index('    private void startCombinedMicTest()')
r=r[:where]+'    private boolean recoverFraming(InputStream in, int marker) throws Exception {\n        if(wireSsrc<0 || wireSeq<0) return false;\n        log("RTSP boundary lost: marker=0x"+Integer.toHexString(marker)+"; previous="+lastWireFrame);\n        int skipped=RtpBoundaryRecovery.recover((java.io.PushbackInputStream)in, marker, wireSsrc, wireSeq, wirePt);\n        boundaryRecoveries++; boundarySkippedBytes+=skipped;\n        accessUnit.reset(); fuBuffer.reset(); fuActive=false; currentAuTimestamp=-1; nextFuSeq=-1;\n        waitingRecoveryIdr=true;\n        releaseDecoder();\n        log("RTSP boundary recovered using two consecutive RTP frames; skipped="+skipped+"; waiting for IDR");\n        status("Поток восстановлен. Ожидание ключевого кадра.");\n        return true;\n    }\n\n'+r[where:]
p.write_text(r)

# v2.6.3: decouple socket intake, pace Surface frames, recover only from codec input blockage.
r=rr(r, '    private TextView audioStatusView;', '    private BufferedSocketInput socketPump;\n    private final VideoPresentationClock presentationClock=new VideoPresentationClock();\n    private long decoderInputTimeouts, lastBoundaryRecoveryMs;\n    private int boundaryRecoveryBurst;\n    private TextView audioStatusView;', 'pipeline state')
r=rr(r, '        Socket socket = null;', '        Socket socket = null;\n        BufferedSocketInput pump = null;', 'reader lifecycle')
r=rr(r, '            socket.connect(new InetSocketAddress', '            socket.setReceiveBufferSize(1024*1024);\n            socket.connect(new InetSocketAddress', 'receive buffer request')
r=rr(r, '            InputStream in = new java.io.BufferedInputStream(socket.getInputStream(), 65536);', '            pump=new BufferedSocketInput(socket.getInputStream());\n            socketPump=pump;\n            InputStream in = new java.io.BufferedInputStream(pump, 65536);\n            log("Independent TCP reader active; receiveBuffer="+socket.getReceiveBufferSize()+" renderBufferMs=250");', 'independent socket reader')
r=rr(r, '            if (socket != null) try { socket.close(); } catch (Exception ignored) {}', '            if (pump != null) try { pump.close(); } catch (Exception ignored) {}\n            if (socket != null) try { socket.close(); } catch (Exception ignored) {}', 'stop socket reader')
r=rr(r, '        boundaryRecoveries=0; boundarySkippedBytes=0;', '        boundaryRecoveries=0; boundarySkippedBytes=0;\n        socketPump=null; decoderInputTimeouts=0; boundaryRecoveryBurst=0; lastBoundaryRecoveryMs=0;\n        presentationClock.reset(); presentationClock.rebuffers=0; presentationClock.lateDrops=0;', 'reset pipeline stats')
r=rr(r, '        if (decoderConfigured && decoder != null && lastDecodedOutputMs > 0L\n                && System.currentTimeMillis() - lastDecodedOutputMs > 3500L) {\n            recoverDecoderFromStall();\n            return;\n        }\n', '', 'network idle is not decoder failure')
r=rr(r, '            int index = decoder.dequeueInputBuffer(10_000);', '            // Drain before waiting for an input slot; never silently lose a predictive frame.\n            drainDecoder();\n            long inputDeadline=android.os.SystemClock.elapsedRealtime()+2000L;\n            int index=-1;\n            while(running && index<0) {\n                index=decoder.dequeueInputBuffer(5_000);\n                if(index>=0)break;\n                drainDecoder();\n                if(android.os.SystemClock.elapsedRealtime()>=inputDeadline) {\n                    decoderInputTimeouts++;\n                    recoverDecoderFromStall();\n                    return;\n                }\n            }\n            if(!running)return;', 'bounded input wait without frame loss')
r=rr(r, '        log("DECODER STALL detected: no output for " + stalledMs\n                + " ms while RTP/access units continue; recovery #" + decoderRecoveryCount);', '        log("DECODER INPUT blocked for 2000 ms; lastOutputAgeMs=" + stalledMs\n                + "; recovery #" + decoderRecoveryCount);\n        waitingRecoveryIdr=true; accessUnit.reset(); fuBuffer.reset(); fuActive=false;', 'accurate codec stall recovery')
r=rr(r, '                decoder.releaseOutputBuffer(out, true);', '                long renderAt=presentationClock.schedule(info.presentationTimeUs,System.nanoTime());\n                if(renderAt<0) decoder.releaseOutputBuffer(out,false);\n                else decoder.releaseOutputBuffer(out,renderAt);', 'timestamp based Surface pacing')
r=rr(r, '    private void releaseDecoder() {', '    private void releaseDecoder() {\n        presentationClock.reset();', 'reset pacing on decoder replacement')
r=rr(r, '        if(wireSsrc<0 || wireSeq<0) return false;', '        if(wireSsrc<0 || wireSeq<0) return false;\n        long now=android.os.SystemClock.elapsedRealtime();\n        boundaryRecoveryBurst=now-lastBoundaryRecoveryMs<3000L ? boundaryRecoveryBurst+1 : 1;\n        lastBoundaryRecoveryMs=now;\n        if(boundaryRecoveryBurst>=3) throw new java.io.IOException("Repeated malformed frames; reconnecting TCP");', 'stop repeated repair of a corrupted stream')
r=rr(r, '        String result = summary + diagnosticSnapshot();', '        summary += "renderBufferMs=250 renderRebuffers="+presentationClock.rebuffers+" lateOutputDrops="+presentationClock.lateDrops+" decoderInputTimeouts="+decoderInputTimeouts+"\\n";\n        summary += (socketPump==null ? "socketReader=not_started" : socketPump.snapshot())+"\\n";\n        String result = summary + diagnosticSnapshot();', 'pipeline report')
p.write_text(r)

# Permit the requested endurance run without the old 30-minute LIVE auto-stop.
mainFile=Path('app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java')
mainSource=mainFile.read_text()
assert 'oneTapLiveRequested ? 1800000L : 240000L' in mainSource
mainFile.write_text(mainSource.replace('oneTapLiveRequested ? 1800000L : 240000L', 'oneTapLiveRequested ? 7200000L : 240000L'))

# Exercise the actual generated parser with synthetic byte streams in Cloud.
# No device identifiers or field payloads enter this public fixture.
import shutil, subprocess, tempfile
if shutil.which('javac'):
    methods=r[r.index('    private byte[] readExactly('):r.index('    private boolean recoverFraming(')]
    harness=r'''import java.io.*;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
public class ParserCheck {
 boolean running=true; long partialFrameTimeoutCount, partialFrameTimeoutBytes, framingLossCount;
 String lastWireFrame="none"; int packets; byte[] last;
 boolean recoverFraming(InputStream in,int marker) { return false; }
 void log(String s) {} void drainDecoder() {}
 void handleInterleavedPacket(int channel, byte[] bytes) { packets++; last=bytes; }
 static class Feed extends InputStream {
  byte[] data; int pos, at, remaining;
  Feed(byte[] d,int a,int count) {data=d;at=a;remaining=count;}
  public int read() throws IOException {
   if(pos==at && remaining-- > 0) throw new SocketTimeoutException("injected");
   return pos<data.length ? data[pos++]&255 : -1;
  }
  public int read(byte[] b,int off,int len) throws IOException {
   int v=read(); if(v<0)return -1; b[off]=(byte)v;return 1;
  }
 }
 void consume(Feed f) throws Exception {try {readInterleaved(f);}catch(EOFException expected){}}
 public static void main(String[] args) throws Exception {
  byte[] frame=new byte[]{36,0,0,3,10,20,30};
  for(int i=0;i<frame.length;i++){
   ParserCheck c=new ParserCheck(); c.consume(new Feed(frame,i,1));
   if(c.packets!=1 || c.last[2]!=30)throw new AssertionError("lost alignment at "+i);
  }
  ParserCheck c=new ParserCheck();
  try{c.readInterleaved(new Feed(frame,5,4));throw new AssertionError("partial deadline swallowed");}
  catch(IOException expected){if(expected instanceof EOFException)throw new AssertionError(expected);}
  if(c.packets!=0)throw new AssertionError("truncated frame delivered");
  String control="RTSP/1.0 200 OK\r\nContent-Length: 3\r\n\r\nabc";
  ByteArrayOutputStream b=new ByteArrayOutputStream();b.write(control.getBytes(StandardCharsets.US_ASCII));b.write(frame);
  c=new ParserCheck();c.consume(new Feed(b.toByteArray(),-1,0));
  if(c.packets!=1)throw new AssertionError("body boundary");
  c=new ParserCheck();
  try{c.readInterleaved(new Feed(new byte[]{(byte)0xd3},-1,0));throw new AssertionError("invalid marker accepted");}
  catch(IllegalStateException expected){if(c.framingLossCount!=1)throw new AssertionError("counter");}
  c=new ParserCheck();c.consume(new Feed(frame,0,4));if(c.packets!=0)throw new AssertionError("idle deadline");
  System.out.println("Parser regression checks PASS: timeout offsets, incomplete frame, RTSP body, invalid marker, idle deadline");
 }
'''+methods+'\n}\n'
    with tempfile.TemporaryDirectory() as tmp:
        f=Path(tmp)/'ParserCheck.java';f.write_text(harness.replace('RtpBoundaryRecovery.CAPACITY', '196640'))
        subprocess.run(['javac',str(f)],check=True)
        subprocess.run(['java','-cp',tmp,'ParserCheck'],check=True)
else:
    print('Parser runtime checks require javac; Cloud build executes them before assembling APK')

if shutil.which('javac'):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['javac','-d',tmp,'app/src/main/java/com/vk/cy01streamlab/RtpBoundaryRecovery.java','tools/RtpBoundaryRecoveryCheck.java'],check=True)
        subprocess.run(['java','-cp',tmp,'com.vk.cy01streamlab.RtpBoundaryRecoveryCheck'],check=True)

if shutil.which('javac'):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['javac','-d',tmp,'app/src/main/java/com/vk/cy01streamlab/BufferedSocketInput.java','app/src/main/java/com/vk/cy01streamlab/VideoPresentationClock.java','tools/VideoPipelineCheck.java'],check=True)
        subprocess.run(['java','-cp',tmp,'com.vk.cy01streamlab.VideoPipelineCheck'],check=True)
