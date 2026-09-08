package com.vk.cy01streamlab;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.media3.common.MediaItem;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.common.VideoSize;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.rtsp.RtspMediaSource;
import androidx.media3.ui.PlayerView;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class RtspPlayerActivity extends Activity {

    private static final String HOST = "192.168.49.96";
    private static final int PORT = 8554;
    private static final String[] PATHS = {
            "/testStream",
            "/testH264VideoStreamer",
            "/xxx.mov",
            "/h264",
            "/live",
            "/stream",
            "/"
    };

    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private PlayerView playerView;
    private TextView statusView;
    private TextView logView;
    private ExoPlayer player;
    private volatile boolean detecting;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        buildUi();
        log("CY01 RTSP Player v0.5 started");
        log("Target: rtsp://" + HOST + ":" + PORT);
        log("New primary path: /testStream (the stock live555 testH264VideoStreamer session name)");
        log("Proof rule: READY is not enough; LIVE is confirmed only after EVENT_RENDERED_FIRST_FRAME");
        autoDetectAndPlay();
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p = dp(12);
        root.setPadding(p, p, p, p);

        TextView title = new TextView(this);
        title.setText("CY01 LIVE VIDEO v0.5");
        title.setTextSize(23f);
        title.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(title);

        statusView = new TextView(this);
        statusView.setText("RTSP: preparing...");
        statusView.setTextSize(16f);
        statusView.setPadding(0, dp(6), 0, dp(8));
        root.addView(statusView);

        playerView = new PlayerView(this);
        playerView.setUseController(true);
        playerView.setKeepContentOnPlayerReset(true);
        LinearLayout.LayoutParams playerParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(300));
        root.addView(playerView, playerParams);

        root.addView(button("AUTO DETECT + PLAY", v -> autoDetectAndPlay()));
        root.addView(button("COPY PLAYER LOG", v -> copyPlayerLog()));
        root.addView(button("STOP PLAYER", v -> releasePlayer()));
        root.addView(button("CLOSE", v -> finish()));

        ScrollView scroll = new ScrollView(this);
        logView = new TextView(this);
        logView.setTextIsSelectable(true);
        logView.setTextSize(12f);
        logView.setPadding(0, dp(8), 0, dp(24));
        scroll.addView(logView);
        LinearLayout.LayoutParams logParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f);
        root.addView(scroll, logParams);

        setContentView(root);
    }

    private Button button(String text, View.OnClickListener listener) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setOnClickListener(listener);
        return b;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void autoDetectAndPlay() {
        if (detecting) {
            log("RTSP auto-detect already running");
            return;
        }
        detecting = true;
        status("RTSP: searching for SDP...");
        log("Sending DESCRIBE to candidate RTSP paths; /testStream is first");

        io.execute(() -> {
            String selected = null;
            String fallback200 = null;
            try {
                for (String path : PATHS) {
                    DescribeResult result = describe(path);
                    log("DESCRIBE " + path + " -> " + result.statusLine);
                    if (!result.body.isEmpty()) {
                        logSdpDetails(path, result.body);
                    }
                    if (result.code == 200 && fallback200 == null) fallback200 = path;
                    if (result.code == 200 && looksLikeSdp(result.body)) {
                        selected = path;
                        log("SDP VIDEO DESCRIPTION FOUND at " + path);
                        break;
                    }
                }

                if (selected == null) selected = fallback200;
                if (selected == null) {
                    status("RTSP: no playable DESCRIBE response");
                    log("No candidate returned RTSP 200. Keep P2P connected and retry.");
                    return;
                }

                final String chosen = selected;
                runOnUiThread(() -> startPlayer(chosen, true));
            } finally {
                detecting = false;
            }
        });
    }

    private DescribeResult describe(String path) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(HOST, PORT), 1200);
            socket.setSoTimeout(1800);

            String uri = "rtsp://" + HOST + ":" + PORT + path;
            String request = "DESCRIBE " + uri + " RTSP/1.0\r\n"
                    + "CSeq: 2\r\n"
                    + "Accept: application/sdp\r\n"
                    + "User-Agent: CY01StreamLab/0.5\r\n\r\n";
            OutputStream os = socket.getOutputStream();
            os.write(request.getBytes(StandardCharsets.US_ASCII));
            os.flush();

            InputStream in = socket.getInputStream();
            BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.US_ASCII));
            String first = br.readLine();
            if (first == null) return new DescribeResult(0, "EOF", "");

            int code = parseStatusCode(first);
            int contentLength = 0;
            String line;
            while ((line = br.readLine()) != null && !line.isEmpty()) {
                String lower = line.toLowerCase(Locale.ROOT);
                if (lower.startsWith("content-length:")) {
                    try {
                        contentLength = Integer.parseInt(line.substring(line.indexOf(':') + 1).trim());
                    } catch (Exception ignored) {}
                }
            }

            StringBuilder body = new StringBuilder();
            if (contentLength > 0) {
                char[] chars = new char[Math.min(contentLength, 8192)];
                int remaining = chars.length;
                while (remaining > 0) {
                    int n = br.read(chars, chars.length - remaining, remaining);
                    if (n <= 0) break;
                    remaining -= n;
                }
                body.append(chars, 0, chars.length - remaining);
            }
            return new DescribeResult(code, first, body.toString());
        } catch (Exception e) {
            return new DescribeResult(0, e.getClass().getSimpleName() + " - " + safeMessage(e), "");
        }
    }

    private int parseStatusCode(String firstLine) {
        try {
            String[] parts = firstLine.split(" ");
            return parts.length >= 2 ? Integer.parseInt(parts[1]) : 0;
        } catch (Exception e) {
            return 0;
        }
    }

    private boolean looksLikeSdp(String body) {
        if (body == null) return false;
        String s = body.toLowerCase(Locale.ROOT);
        return s.contains("v=0") && s.contains("m=video");
    }

    private void logSdpDetails(String path, String body) {
        log("SDP RAW " + path + " | " + compact(body));
        String[] lines = body.replace("\r", "").split("\n");
        for (String line : lines) {
            String lower = line.toLowerCase(Locale.ROOT);
            if (lower.startsWith("c=")
                    || lower.startsWith("m=video")
                    || lower.startsWith("a=rtpmap:")
                    || lower.startsWith("a=fmtp:")
                    || lower.startsWith("a=control:")
                    || lower.startsWith("a=source-filter:")) {
                log("SDP " + path + " | " + line.trim());
            }
        }
        if (looksMulticast(body)) {
            log("SDP transport hint: MULTICAST destination detected. Media3 supports UDP unicast or interleaved TCP, not RTP multicast.");
        } else {
            log("SDP transport hint: no multicast destination detected in SDP");
        }
    }

    private boolean looksMulticast(String body) {
        String[] lines = body.replace("\r", "").split("\n");
        for (String line : lines) {
            String s = line.trim();
            if (!s.startsWith("c=IN IP4 ")) continue;
            String address = s.substring("c=IN IP4 ".length()).trim();
            int slash = address.indexOf('/');
            if (slash >= 0) address = address.substring(0, slash);
            String[] parts = address.split("\\.");
            if (parts.length == 4) {
                try {
                    int first = Integer.parseInt(parts[0]);
                    if (first >= 224 && first <= 239) return true;
                } catch (Exception ignored) {}
            }
        }
        return body.toLowerCase(Locale.ROOT).contains("a=source-filter:");
    }

    private void startPlayer(String path, boolean forceTcp) {
        releasePlayer();
        String uri = "rtsp://" + HOST + ":" + PORT + path;
        String transport = forceTcp ? "TCP interleaved" : "UDP-first";
        status("RTSP: connecting " + path + " via " + transport);
        log("Starting Media3 player: " + uri + " transport=" + transport);

        final ExoPlayer created = new ExoPlayer.Builder(this).build();
        player = created;
        playerView.setPlayer(created);
        created.addListener(new Player.Listener() {
            @Override
            public void onPlaybackStateChanged(int playbackState) {
                if (player != created) return;
                if (playbackState == Player.STATE_BUFFERING) {
                    status("RTSP: buffering " + path + " via " + transport + "...");
                    log("Player state = BUFFERING path=" + path + " transport=" + transport);
                } else if (playbackState == Player.STATE_READY) {
                    status("RTSP: session READY; waiting for first video frame...");
                    log("PLAYER READY path=" + path + " transport=" + transport
                            + ": session prepared; rendered frame not yet confirmed");
                } else if (playbackState == Player.STATE_ENDED) {
                    status("RTSP: stream ended");
                    log("Player state = ENDED path=" + path + " transport=" + transport);
                }
            }

            @Override
            public void onVideoSizeChanged(VideoSize videoSize) {
                if (player != created) return;
                log("VIDEO SIZE path=" + path + " transport=" + transport + " -> "
                        + videoSize.width + "x" + videoSize.height);
            }

            @Override
            public void onEvents(Player callbackPlayer, Player.Events events) {
                if (player != created) return;
                if (events.contains(Player.EVENT_RENDERED_FIRST_FRAME)) {
                    VideoSize size = callbackPlayer.getVideoSize();
                    status("RTSP: LIVE VIDEO CONFIRMED " + path);
                    log("FIRST VIDEO FRAME RENDERED path=" + path + " transport=" + transport
                            + " size=" + size.width + "x" + size.height
                            + " -- definitive local decode/display proof");
                }
            }

            @Override
            public void onPlayerError(PlaybackException error) {
                if (player != created) return;
                status("RTSP error " + error.errorCode + " on " + path + " via " + transport);
                log("PLAYER ERROR path=" + path + " transport=" + transport
                        + " code=" + error.errorCode + " - " + throwableChain(error));
                if (forceTcp) {
                    log("Retrying same RTSP path with UDP-first transport for classification");
                    playerView.postDelayed(() -> {
                        if (player == created) startPlayer(path, false);
                    }, 700);
                } else {
                    tryNextPath(path, created);
                }
            }
        });

        MediaItem item = MediaItem.fromUri(uri);
        RtspMediaSource source = new RtspMediaSource.Factory()
                .setForceUseRtpTcp(forceTcp)
                .setTimeoutMs(5000)
                .createMediaSource(item);
        created.setMediaSource(source);
        created.prepare();
        created.play();
    }

    private void tryNextPath(String failedPath, ExoPlayer failedPlayer) {
        int index = -1;
        for (int i = 0; i < PATHS.length; i++) {
            if (PATHS[i].equals(failedPath)) {
                index = i;
                break;
            }
        }
        if (index < 0 || index + 1 >= PATHS.length) {
            log("No further RTSP path candidates after " + failedPath);
            return;
        }
        String next = PATHS[index + 1];
        log("Scheduling automatic fallback: " + failedPath + " -> " + next);
        playerView.postDelayed(() -> {
            if (player == failedPlayer) startPlayer(next, true);
        }, 700);
    }

    private void copyPlayerLog() {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (clipboard == null) {
            log("Clipboard service unavailable");
            return;
        }
        clipboard.setPrimaryClip(ClipData.newPlainText("CY01 RTSP player log", logView.getText()));
        log("Player log copied to clipboard");
    }

    private void releasePlayer() {
        if (player != null) {
            ExoPlayer old = player;
            player = null;
            try { old.stop(); } catch (Exception ignored) {}
            try { old.release(); } catch (Exception ignored) {}
        }
        if (playerView != null) playerView.setPlayer(null);
    }

    private String compact(String text) {
        String s = text.replace('\r', ' ').replace('\n', ' ').replaceAll("\\s+", " ").trim();
        return s.length() > 1000 ? s.substring(0, 1000) + "..." : s;
    }

    private String safeMessage(Throwable t) {
        String m = t.getMessage();
        return m == null || m.isEmpty() ? "no message" : m;
    }

    private String throwableChain(Throwable t) {
        StringBuilder sb = new StringBuilder();
        Throwable cur = t;
        int depth = 0;
        while (cur != null && depth < 6) {
            if (depth > 0) sb.append(" <- ");
            sb.append(cur.getClass().getSimpleName()).append(": ").append(safeMessage(cur));
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
        releasePlayer();
        io.shutdownNow();
        super.onDestroy();
    }

    private static final class DescribeResult {
        final int code;
        final String statusLine;
        final String body;

        DescribeResult(int code, String statusLine, String body) {
            this.code = code;
            this.statusLine = statusLine;
            this.body = body == null ? "" : body;
        }
    }
}
