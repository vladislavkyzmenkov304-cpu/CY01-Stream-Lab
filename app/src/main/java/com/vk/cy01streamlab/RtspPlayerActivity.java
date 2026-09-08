package com.vk.cy01streamlab;

import android.app.Activity;
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
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.rtsp.RtspMediaSource;
import androidx.media3.ui.PlayerView;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
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
        log("CY01 RTSP Player v0.4 started");
        log("Target: rtsp://" + HOST + ":" + PORT + " ; RTP over RTSP/TCP forced");
        autoDetectAndPlay();
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p = dp(12);
        root.setPadding(p, p, p, p);

        TextView title = new TextView(this);
        title.setText("CY01 LIVE VIDEO");
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
        log("Sending DESCRIBE to candidate RTSP paths");

        io.execute(() -> {
            String selected = null;
            String fallback200 = null;
            try {
                for (String path : PATHS) {
                    DescribeResult result = describe(path);
                    log("DESCRIBE " + path + " -> " + result.statusLine
                            + (result.body.isEmpty() ? "" : " | " + compact(result.body)));
                    if (result.code == 200 && fallback200 == null) fallback200 = path;
                    if (result.code == 200 && looksLikeSdp(result.body)) {
                        selected = path;
                        log("SDP video description found at " + path);
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
                runOnUiThread(() -> startPlayer(chosen));
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
                    + "User-Agent: CY01StreamLab/0.4\r\n\r\n";
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
                    try { contentLength = Integer.parseInt(line.substring(line.indexOf(':') + 1).trim()); }
                    catch (Exception ignored) {}
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
        return s.contains("v=0") && (s.contains("m=video") || s.contains("a=control:"));
    }

    private void startPlayer(String path) {
        releasePlayer();
        String uri = "rtsp://" + HOST + ":" + PORT + path;
        status("RTSP: connecting " + path);
        log("Starting Media3 player: " + uri);

        player = new ExoPlayer.Builder(this).build();
        playerView.setPlayer(player);
        player.addListener(new Player.Listener() {
            @Override
            public void onPlaybackStateChanged(int playbackState) {
                if (playbackState == Player.STATE_BUFFERING) {
                    status("RTSP: buffering...");
                    log("Player state = BUFFERING");
                } else if (playbackState == Player.STATE_READY) {
                    status("RTSP: LIVE VIDEO READY");
                    log("PLAYER READY: RTSP media decoded by Android");
                } else if (playbackState == Player.STATE_ENDED) {
                    status("RTSP: stream ended");
                    log("Player state = ENDED");
                }
            }

            @Override
            public void onPlayerError(PlaybackException error) {
                status("RTSP player error: " + error.errorCodeName);
                log("PLAYER ERROR: " + error.errorCodeName + " - " + safeMessage(error));
            }
        });

        MediaItem item = MediaItem.fromUri(uri);
        RtspMediaSource source = new RtspMediaSource.Factory()
                .setForceUseRtpTcp()
                .setTimeoutMs(5000)
                .createMediaSource(item);
        player.setMediaSource(source);
        player.prepare();
        player.play();
    }

    private void releasePlayer() {
        if (player != null) {
            try { player.stop(); } catch (Exception ignored) {}
            try { player.release(); } catch (Exception ignored) {}
            player = null;
        }
        if (playerView != null) playerView.setPlayer(null);
    }

    private String compact(String text) {
        String s = text.replace('\r', ' ').replace('\n', ' ').replaceAll("\\s+", " ").trim();
        return s.length() > 220 ? s.substring(0, 220) + "..." : s;
    }

    private String safeMessage(Throwable t) {
        String m = t.getMessage();
        return m == null || m.isEmpty() ? "no message" : m;
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
