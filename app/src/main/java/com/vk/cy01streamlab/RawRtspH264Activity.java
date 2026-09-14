package com.vk.cy01streamlab;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.media.MediaCodec;
import android.media.MediaFormat;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Minimal CY01-specific RTSP/RTP/H.264 path that intentionally bypasses Media3's SDP parser.
 *
 * The CY01 /ch0 SDP advertises H264/90000 but omits the H.264 fmtp attribute. Media3 rejects
 * that SDP before SETUP. This activity performs RTSP itself, requests RTP-over-RTSP/TCP,
 * depacketizes H.264 (single NAL, STAP-A, FU-A), learns SPS/PPS in-band and feeds MediaCodec.
 */
public class RawRtspH264Activity extends Activity implements SurfaceHolder.Callback {

    private static final String HOST = "192.168.49.96";
    private static final int PORT = 8554;
    private static final String BASE_URI = "rtsp://" + HOST + ":" + PORT + "/ch0";
    private static final byte[] START_CODE = new byte[]{0, 0, 0, 1};

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final ByteArrayOutputStream fuBuffer = new ByteArrayOutputStream(256 * 1024);
    private final ByteArrayOutputStream accessUnit = new ByteArrayOutputStream(2 * 1024 * 1024);
    private final int[] nalCounts = new int[32];

    private TextView statusView;
    private TextView logView;
    private SurfaceView surfaceView;
    private volatile boolean running;
    private volatile Socket rtspSocket;
    private volatile boolean surfaceReady;
    private Surface surface;
    private MediaCodec decoder;
    private byte[] sps;
    private byte[] pps;
    private boolean decoderConfigured;
    private boolean firstRendered;
    private boolean firstRtp;
    private boolean firstH264;
    private int cSeq = 1;
    private String sessionId;
    private int fuTimestamp;
    private boolean fuActive;
    private long currentAuTimestamp = -1;
    private long baseRtpTimestamp = -1;
    private long rtpPacketCount;
    private long accessUnitCount;
    private long decodedOutputCount;
    private int verboseNalBudget = 24;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        buildUi();
        log("CY01 RAW RTSP/H264 v0.8 started");
        log("Target is confirmed media session: " + BASE_URI);
        log("Purpose: bypass Media3 'missing attribute fmtp' and inspect/decode in-band H.264 directly");
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p = dp(12);
        root.setPadding(p, p, p, p);

        TextView title = new TextView(this);
        title.setText("CY01 RAW /ch0 H264 v0.8");
        title.setTextSize(22f);
        root.addView(title);

        statusView = new TextView(this);
        statusView.setText("Waiting for video surface...");
        statusView.setTextSize(15f);
        statusView.setPadding(0, dp(6), 0, dp(8));
        root.addView(statusView);

        surfaceView = new SurfaceView(this);
        surfaceView.getHolder().addCallback(this);
        root.addView(surfaceView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(300)));

        root.addView(button("START RAW /ch0 TEST", v -> startRawTest()));
        root.addView(button("COPY RAW LOG", v -> copyLog()));
        root.addView(button("STOP RAW TEST", v -> stopRawTest()));
        root.addView(button("CLOSE", v -> finish()));

        ScrollView scroll = new ScrollView(this);
        logView = new TextView(this);
        logView.setTextIsSelectable(true);
        logView.setTextSize(12f);
        logView.setPadding(0, dp(8), 0, dp(24));
        scroll.addView(logView);
        root.addView(scroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));

        setContentView(root);
    }

    private Button button(String text, android.view.View.OnClickListener listener) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setOnClickListener(listener);
        return b;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    public void surfaceCreated(SurfaceHolder holder) {
        surface = holder.getSurface();
        surfaceReady = surface != null && surface.isValid();
        log("Video surface ready=" + surfaceReady);
        status("RAW RTSP ready. Tap START RAW /ch0 TEST");
    }

    @Override
    public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {
        surface = holder.getSurface();
        surfaceReady = surface != null && surface.isValid();
    }

    @Override
    public void surfaceDestroyed(SurfaceHolder holder) {
        surfaceReady = false;
        surface = null;
        stopRawTest();
    }

    private void startRawTest() {
        if (running) {
            log("Raw test already running");
            return;
        }
        if (!surfaceReady || surface == null || !surface.isValid()) {
            log("Raw test blocked: video Surface is not ready");
            return;
        }
        resetStreamState();
        running = true;
        status("Connecting RTSP /ch0...");
        io.execute(this::runRtspSession);
    }

    private void resetStreamState() {
        releaseDecoder();
        sps = null;
        pps = null;
        decoderConfigured = false;
        firstRendered = false;
        firstRtp = false;
        firstH264 = false;
        cSeq = 1;
        sessionId = null;
        fuBuffer.reset();
        accessUnit.reset();
        fuActive = false;
        currentAuTimestamp = -1;
        baseRtpTimestamp = -1;
        rtpPacketCount = 0;
        accessUnitCount = 0;
        decodedOutputCount = 0;
        verboseNalBudget = 24;
        for (int i = 0; i < nalCounts.length; i++) nalCounts[i] = 0;
    }

    private void runRtspSession() {
        Socket socket = null;
        try {
            socket = new Socket();
            rtspSocket = socket;
            socket.connect(new InetSocketAddress(HOST, PORT), 1800);
            socket.setSoTimeout(2500);
            log("TCP " + HOST + ":" + PORT + " connected for raw RTSP");

            InputStream in = socket.getInputStream();
            OutputStream out = socket.getOutputStream();

            RtspResponse options = transact(in, out, "OPTIONS", BASE_URI, null);
            log("OPTIONS /ch0 -> " + options.statusLine + " Public=" + options.header("public"));

            Map<String, String> describeHeaders = new HashMap<>();
            describeHeaders.put("Accept", "application/sdp");
            RtspResponse describe = transact(in, out, "DESCRIBE", BASE_URI, describeHeaders);
            log("DESCRIBE /ch0 -> " + describe.statusLine);
            if (describe.code != 200) throw new IllegalStateException("DESCRIBE failed: " + describe.statusLine);
            String sdp = new String(describe.body, StandardCharsets.US_ASCII);
            log("SDP confirms H264=" + sdp.contains("H264/90000")
                    + " video-fmtp=" + hasVideoFmtp(sdp)
                    + " audio=" + sdp.contains("MPEG4-GENERIC"));
            String contentBase = describe.header("content-base");
            String trackUri = buildTrackUri(contentBase, "track1");
            log("Video control URI = " + trackUri);

            Map<String, String> setupHeaders = new HashMap<>();
            setupHeaders.put("Transport", "RTP/AVP/TCP;unicast;interleaved=0-1");
            RtspResponse setup = transact(in, out, "SETUP", trackUri, setupHeaders);
            log("SETUP track1 TCP interleaved -> " + setup.statusLine);
            log("SETUP Transport=" + setup.header("transport"));
            if (setup.code != 200) throw new IllegalStateException("SETUP failed: " + setup.statusLine);
            sessionId = parseSessionId(setup.header("session"));
            log("RTSP Session=" + sessionId);
            if (sessionId == null || sessionId.isEmpty()) throw new IllegalStateException("SETUP response has no Session header");

            Map<String, String> playHeaders = new HashMap<>();
            playHeaders.put("Session", sessionId);
            playHeaders.put("Range", "npt=0.000-");
            RtspResponse play = transact(in, out, "PLAY", BASE_URI, playHeaders);
            log("PLAY /ch0 -> " + play.statusLine + " RTP-Info=" + play.header("rtp-info"));
            if (play.code != 200) throw new IllegalStateException("PLAY failed: " + play.statusLine);

            status("PLAY accepted. Waiting for interleaved H.264 RTP...");
            readInterleaved(in);
        } catch (Exception e) {
            if (running) {
                log("RAW SESSION ERROR: " + errorText(e));
                status("RAW error: " + e.getClass().getSimpleName());
            }
        } finally {
            running = false;
            if (socket != null) try { socket.close(); } catch (Exception ignored) {}
            if (rtspSocket == socket) rtspSocket = null;
            log("Raw session ended. RTP packets=" + rtpPacketCount
                    + " accessUnits=" + accessUnitCount
                    + " decoderOutputs=" + decodedOutputCount
                    + " NAL[SPS]=" + nalCounts[7]
                    + " NAL[PPS]=" + nalCounts[8]
                    + " NAL[IDR]=" + nalCounts[5]);
        }
    }

    private RtspResponse transact(InputStream in, OutputStream out, String method, String uri,
                                  Map<String, String> extraHeaders) throws Exception {
        StringBuilder request = new StringBuilder();
        request.append(method).append(' ').append(uri).append(" RTSP/1.0\r\n");
        request.append("CSeq: ").append(cSeq++).append("\r\n");
        request.append("User-Agent: CY01StreamLab-Raw/0.8\r\n");
        if (extraHeaders != null) {
            for (Map.Entry<String, String> e : extraHeaders.entrySet()) {
                request.append(e.getKey()).append(": ").append(e.getValue()).append("\r\n");
            }
        }
        request.append("\r\n");
        out.write(request.toString().getBytes(StandardCharsets.US_ASCII));
        out.flush();
        return readRtspResponse(in);
    }

    private RtspResponse readRtspResponse(InputStream in) throws Exception {
        ByteArrayOutputStream headerBytes = new ByteArrayOutputStream(2048);
        int state = 0;
        while (true) {
            int b = in.read();
            if (b < 0) throw new EOFException("EOF while reading RTSP headers");
            headerBytes.write(b);
            if (state == 0 && b == '\r') state = 1;
            else if (state == 1 && b == '\n') state = 2;
            else if (state == 2 && b == '\r') state = 3;
            else if (state == 3 && b == '\n') break;
            else state = b == '\r' ? 1 : 0;
            if (headerBytes.size() > 32768) throw new IllegalStateException("RTSP headers too large");
        }

        String headerText = headerBytes.toString(StandardCharsets.US_ASCII.name());
        String[] lines = headerText.split("\\r\\n");
        String statusLine = lines.length == 0 ? "" : lines[0];
        int code = parseStatusCode(statusLine);
        Map<String, String> headers = new HashMap<>();
        for (int i = 1; i < lines.length; i++) {
            int colon = lines[i].indexOf(':');
            if (colon <= 0) continue;
            headers.put(lines[i].substring(0, colon).trim().toLowerCase(Locale.ROOT),
                    lines[i].substring(colon + 1).trim());
        }
        int contentLength = 0;
        try { contentLength = Integer.parseInt(headers.getOrDefault("content-length", "0")); }
        catch (Exception ignored) {}
        byte[] body = readExactly(in, contentLength);
        return new RtspResponse(code, statusLine, headers, body);
    }

    private byte[] readExactly(InputStream in, int length) throws Exception {
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

    private void readInterleaved(InputStream in) throws Exception {
        int timeoutCount = 0;
        while (running) {
            try {
                int marker = in.read();
                if (marker < 0) throw new EOFException("RTSP/RTP socket closed");
                if (marker != '$') {
                    // Unexpected server-side RTSP text after PLAY. Read the rest of the line only.
                    ByteArrayOutputStream line = new ByteArrayOutputStream();
                    line.write(marker);
                    int b;
                    while ((b = in.read()) >= 0 && b != '\n' && line.size() < 1024) line.write(b);
                    log("Post-PLAY RTSP text: " + line.toString(StandardCharsets.US_ASCII.name()).trim());
                    continue;
                }

                int channel = in.read();
                int hi = in.read();
                int lo = in.read();
                if (channel < 0 || hi < 0 || lo < 0) throw new EOFException("EOF in interleaved header");
                int length = (hi << 8) | lo;
                byte[] packet = readExactly(in, length);
                if (channel == 0) handleRtp(packet);
                // channel 1 is RTCP and intentionally ignored in this video-only proof.
            } catch (SocketTimeoutException timeout) {
                timeoutCount++;
                if (timeoutCount <= 3 || timeoutCount % 5 == 0) {
                    log("Waiting for RTP... socket timeout #" + timeoutCount);
                }
            }
        }
    }

    private void handleRtp(byte[] packet) {
        if (packet.length < 12) return;
        int b0 = packet[0] & 0xFF;
        int b1 = packet[1] & 0xFF;
        if ((b0 >> 6) != 2) return;
        boolean padding = (b0 & 0x20) != 0;
        boolean extension = (b0 & 0x10) != 0;
        int cc = b0 & 0x0F;
        boolean rtpMarker = (b1 & 0x80) != 0;
        int payloadType = b1 & 0x7F;
        int seq = ((packet[2] & 0xFF) << 8) | (packet[3] & 0xFF);
        long timestamp = ((long) (packet[4] & 0xFF) << 24)
                | ((long) (packet[5] & 0xFF) << 16)
                | ((long) (packet[6] & 0xFF) << 8)
                | (long) (packet[7] & 0xFF);

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
        if (end <= off) return;

        rtpPacketCount++;
        if (!firstRtp) {
            firstRtp = true;
            log("FIRST RTP VIDEO PACKET: PT=" + payloadType + " seq=" + seq
                    + " timestamp=" + timestamp + " payloadBytes=" + (end - off));
            status("RTP VIDEO RECEIVED. Looking for H.264 SPS/PPS/IDR...");
        }

        if (currentAuTimestamp != -1 && currentAuTimestamp != timestamp && accessUnit.size() > 0 && !fuActive) {
            flushAccessUnit(currentAuTimestamp);
        }
        if (currentAuTimestamp == -1 || currentAuTimestamp != timestamp) currentAuTimestamp = timestamp;

        int nalType = packet[off] & 0x1F;
        if (nalType >= 1 && nalType <= 23) {
            handleCompleteNal(copyOfRange(packet, off, end));
        } else if (nalType == 24) {
            parseStapA(packet, off, end);
        } else if (nalType == 28) {
            parseFuA(packet, off, end, (int) timestamp, seq);
        } else if (verboseNalBudget > 0) {
            verboseNalBudget--;
            log("Unsupported/unused H264 RTP aggregation type=" + nalType + " seq=" + seq);
        }

        if (rtpMarker && !fuActive) flushAccessUnit(timestamp);
    }

    private void parseStapA(byte[] packet, int off, int end) {
        int p = off + 1;
        while (p + 2 <= end) {
            int n = ((packet[p] & 0xFF) << 8) | (packet[p + 1] & 0xFF);
            p += 2;
            if (n <= 0 || p + n > end) break;
            handleCompleteNal(copyOfRange(packet, p, p + n));
            p += n;
        }
    }

    private void parseFuA(byte[] packet, int off, int end, int timestamp, int seq) {
        if (off + 2 > end) return;
        int indicator = packet[off] & 0xFF;
        int header = packet[off + 1] & 0xFF;
        boolean start = (header & 0x80) != 0;
        boolean finish = (header & 0x40) != 0;
        int originalType = header & 0x1F;

        if (start) {
            fuBuffer.reset();
            fuBuffer.write((indicator & 0xE0) | originalType);
            fuTimestamp = timestamp;
            fuActive = true;
        } else if (!fuActive || fuTimestamp != timestamp) {
            if (verboseNalBudget > 0) {
                verboseNalBudget--;
                log("Dropping orphan FU-A fragment seq=" + seq + " type=" + originalType);
            }
            return;
        }

        if (fuActive && end > off + 2) fuBuffer.write(packet, off + 2, end - (off + 2));
        if (finish && fuActive) {
            byte[] nal = fuBuffer.toByteArray();
            fuBuffer.reset();
            fuActive = false;
            handleCompleteNal(nal);
        }
    }

    private void handleCompleteNal(byte[] nal) {
        if (nal == null || nal.length == 0) return;
        int type = nal[0] & 0x1F;
        if (type >= 0 && type < nalCounts.length) nalCounts[type]++;
        if (!firstH264) {
            firstH264 = true;
            log("FIRST COMPLETE H264 NAL: type=" + type + " bytes=" + nal.length);
        }
        if (type == 7) {
            sps = nal.clone();
            log("H264 SPS received in-band, bytes=" + nal.length);
        } else if (type == 8) {
            pps = nal.clone();
            log("H264 PPS received in-band, bytes=" + nal.length);
        } else if (type == 5) {
            log("H264 IDR keyframe NAL received, bytes=" + nal.length);
        } else if (verboseNalBudget > 0) {
            verboseNalBudget--;
            log("H264 NAL type=" + type + " bytes=" + nal.length);
        }

        try {
            accessUnit.write(START_CODE);
            accessUnit.write(nal);
        } catch (Exception ignored) {}

        if (!decoderConfigured && sps != null && pps != null) configureDecoder();
    }

    private void configureDecoder() {
        if (decoderConfigured || sps == null || pps == null || surface == null || !surface.isValid()) return;
        try {
            MediaFormat format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, 1280, 960);
            format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 2 * 1024 * 1024);
            format.setByteBuffer("csd-0", ByteBuffer.wrap(withStartCode(sps)));
            format.setByteBuffer("csd-1", ByteBuffer.wrap(withStartCode(pps)));
            MediaCodec codec = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
            codec.setOnFrameRenderedListener((mc, presentationTimeUs, nanoTime) -> {
                if (!firstRendered) {
                    firstRendered = true;
                    log("FIRST VIDEO FRAME RENDERED by MediaCodec at ptsUs=" + presentationTimeUs
                            + " -- definitive CY01 live camera decode/display proof");
                    status("LIVE VIDEO CONFIRMED from CY01 /ch0");
                }
            }, main);
            codec.configure(format, surface, null, 0);
            codec.start();
            decoder = codec;
            decoderConfigured = true;
            log("MediaCodec AVC decoder configured from in-band SPS/PPS (initial hint 1280x960)");
            status("H.264 SPS/PPS found. Decoder running; waiting for frame...");
        } catch (Exception e) {
            log("MediaCodec configure failed: " + errorText(e));
        }
    }

    private void flushAccessUnit(long rtpTimestamp) {
        if (accessUnit.size() == 0) return;
        byte[] au = accessUnit.toByteArray();
        accessUnit.reset();
        accessUnitCount++;
        if (!decoderConfigured || decoder == null) {
            if (accessUnitCount <= 5) log("Access unit dropped before decoder config, bytes=" + au.length);
            return;
        }
        try {
            if (baseRtpTimestamp < 0) baseRtpTimestamp = rtpTimestamp;
            long delta = (rtpTimestamp - baseRtpTimestamp) & 0xFFFFFFFFL;
            long ptsUs = (delta * 1_000_000L) / 90_000L;
            int index = decoder.dequeueInputBuffer(10_000);
            if (index >= 0) {
                ByteBuffer input = decoder.getInputBuffer(index);
                if (input == null) return;
                input.clear();
                if (au.length > input.remaining()) {
                    log("Decoder input too small: au=" + au.length + " capacity=" + input.remaining());
                    decoder.queueInputBuffer(index, 0, 0, ptsUs, 0);
                } else {
                    input.put(au);
                    decoder.queueInputBuffer(index, 0, au.length, ptsUs, 0);
                }
            }
            drainDecoder();
        } catch (Exception e) {
            log("Decoder queue/drain error: " + errorText(e));
        }
    }

    private void drainDecoder() {
        if (decoder == null) return;
        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        for (int i = 0; i < 8; i++) {
            int out = decoder.dequeueOutputBuffer(info, 0);
            if (out >= 0) {
                decodedOutputCount++;
                if (decodedOutputCount == 1) {
                    log("FIRST DECODED VIDEO OUTPUT buffer ptsUs=" + info.presentationTimeUs
                            + "; releasing to Surface");
                }
                decoder.releaseOutputBuffer(out, true);
            } else if (out == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                log("Decoder output format changed: " + decoder.getOutputFormat());
            } else {
                break;
            }
        }
    }

    private byte[] withStartCode(byte[] nal) {
        byte[] out = new byte[START_CODE.length + nal.length];
        System.arraycopy(START_CODE, 0, out, 0, START_CODE.length);
        System.arraycopy(nal, 0, out, START_CODE.length, nal.length);
        return out;
    }

    private byte[] copyOfRange(byte[] src, int start, int end) {
        int n = Math.max(0, end - start);
        byte[] out = new byte[n];
        System.arraycopy(src, start, out, 0, n);
        return out;
    }

    private boolean hasVideoFmtp(String sdp) {
        boolean inVideo = false;
        for (String raw : sdp.replace("\r", "").split("\n")) {
            String line = raw.trim();
            if (line.startsWith("m=")) inVideo = line.startsWith("m=video");
            if (inVideo && line.startsWith("a=fmtp:")) return true;
        }
        return false;
    }

    private String buildTrackUri(String contentBase, String control) {
        String base = contentBase;
        if (base == null || base.isEmpty()) base = BASE_URI + "/";
        if (!base.endsWith("/")) base += "/";
        return base + control;
    }

    private String parseSessionId(String sessionHeader) {
        if (sessionHeader == null) return null;
        int semi = sessionHeader.indexOf(';');
        return (semi >= 0 ? sessionHeader.substring(0, semi) : sessionHeader).trim();
    }

    private int parseStatusCode(String statusLine) {
        try {
            String[] p = statusLine.split(" ");
            return p.length >= 2 ? Integer.parseInt(p[1]) : 0;
        } catch (Exception e) {
            return 0;
        }
    }

    private void stopRawTest() {
        running = false;
        Socket s = rtspSocket;
        rtspSocket = null;
        if (s != null) try { s.close(); } catch (Exception ignored) {}
        releaseDecoder();
        status("RAW test stopped");
    }

    private void releaseDecoder() {
        MediaCodec c = decoder;
        decoder = null;
        decoderConfigured = false;
        if (c != null) {
            try { c.stop(); } catch (Exception ignored) {}
            try { c.release(); } catch (Exception ignored) {}
        }
    }

    private void copyLog() {
        ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (cm == null) return;
        cm.setPrimaryClip(ClipData.newPlainText("CY01 RAW RTSP H264 log", logView.getText()));
        log("Raw log copied to clipboard");
    }

    private String errorText(Throwable e) {
        StringBuilder sb = new StringBuilder();
        Throwable cur = e;
        int depth = 0;
        while (cur != null && depth < 6) {
            if (depth > 0) sb.append(" <- ");
            sb.append(cur.getClass().getSimpleName());
            String m = cur.getMessage();
            if (m != null && !m.isEmpty()) sb.append(": ").append(m);
            cur = cur.getCause();
            depth++;
        }
        return sb.toString();
    }

    private void status(String text) {
        runOnUiThread(() -> statusView.setText(text));
    }

    private void log(String text) {
        String time = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        runOnUiThread(() -> logView.append(time + "  " + text + "\n"));
    }

    @Override
    protected void onDestroy() {
        stopRawTest();
        io.shutdownNow();
        super.onDestroy();
    }

    private static final class RtspResponse {
        final int code;
        final String statusLine;
        final Map<String, String> headers;
        final byte[] body;

        RtspResponse(int code, String statusLine, Map<String, String> headers, byte[] body) {
            this.code = code;
            this.statusLine = statusLine;
            this.headers = headers;
            this.body = body;
        }

        String header(String name) {
            String v = headers.get(name.toLowerCase(Locale.ROOT));
            return v == null ? "" : v;
        }
    }
}
