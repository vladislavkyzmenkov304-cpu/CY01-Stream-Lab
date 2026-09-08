package com.vk.cy01streamlab;

import android.Manifest;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.wifi.p2p.WifiP2pConfig;
import android.net.wifi.p2p.WifiP2pDevice;
import android.net.wifi.p2p.WifiP2pDeviceList;
import android.net.wifi.p2p.WifiP2pInfo;
import android.net.wifi.p2p.WifiP2pManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {

    private static final UUID SERVICE_UUID = UUID.fromString("de5bf728-d711-4e47-af26-65e3012a5dc7");
    private static final UUID WRITE_UUID = UUID.fromString("de5bf72a-d711-4e47-af26-65e3012a5dc7");
    private static final UUID NOTIFY_UUID = UUID.fromString("de5bf729-d711-4e47-af26-65e3012a5dc7");
    private static final UUID CCCD_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final ByteArrayOutputStream rx = new ByteArrayOutputStream();

    private TextView status;
    private TextView logView;
    private BluetoothAdapter btAdapter;
    private BluetoothLeScanner scanner;
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic writeChar;
    private BluetoothGattCharacteristic notifyChar;
    private boolean bleReady = false;
    private boolean scanning = false;

    private WifiP2pManager p2pManager;
    private WifiP2pManager.Channel p2pChannel;
    private boolean p2pConnectIssued = false;
    private boolean p2pConnected = false;
    private BroadcastReceiver p2pReceiver;

    private volatile String glassesIp = null;
    private volatile Network p2pNetwork = null;
    private Runnable autoStopRunnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();

        BluetoothManager bm = (BluetoothManager) getSystemService(BLUETOOTH_SERVICE);
        btAdapter = bm.getAdapter();
        p2pManager = (WifiP2pManager) getSystemService(WIFI_P2P_SERVICE);
        p2pChannel = p2pManager.initialize(this, getMainLooper(), () -> log("Wi-Fi Direct channel lost"));

        setupP2pReceiver();
        requestNeededPermissions();
        log("CY01 Stream Lab v0.1 started");
        log("Safe lab flow: BLE preview command -> Wi-Fi Direct -> HTTP/RTSP probes -> automatic stop");
    }

    private void buildUi() {
        ScrollView root = new ScrollView(this);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int p = dp(14);
        box.setPadding(p, p, p, p);
        root.addView(box);

        TextView title = new TextView(this);
        title.setText("CY01 Stream Lab");
        title.setTextSize(24f);
        box.addView(title);

        status = new TextView(this);
        status.setText("BLE: disconnected | P2P: disconnected");
        status.setTextSize(16f);
        status.setPadding(0, dp(8), 0, dp(8));
        box.addView(status);

        box.addView(button("1. CONNECT CY01", v -> scanAndConnect()));
        box.addView(button("READ BATTERY", v -> sendFrame(0x42, new byte[0])));
        box.addView(button("READ CAPABILITIES", v -> sendFrame(0x47, new byte[]{0x01, 0x00})));
        box.addView(button("2. START LIVE TEST", v -> startLiveTest()));
        box.addView(button("PROBE NOW", v -> runProbeSuite()));
        box.addView(button("STOP + DISCONNECT P2P", v -> stopPreviewAndP2p()));
        box.addView(button("ANDROID WIFI DIRECT SETTINGS", v -> openWifiDirectSettings()));

        TextView note = new TextView(this);
        note.setText("This build does not flash firmware, reset the glasses, or send OTA commands. Live preview is auto-stopped after 60 seconds.");
        note.setPadding(0, dp(8), 0, dp(8));
        box.addView(note);

        logView = new TextView(this);
        logView.setTextIsSelectable(true);
        logView.setTextSize(12f);
        logView.setPadding(0, dp(8), 0, dp(24));
        box.addView(logView);

        setContentView(root);
    }

    private Button button(String text, View.OnClickListener click) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setOnClickListener(click);
        return b;
    }

    private int dp(int n) {
        return Math.round(n * getResources().getDisplayMetrics().density);
    }

    private void requestNeededPermissions() {
        List<String> perms = new ArrayList<>();
        if (Build.VERSION.SDK_INT >= 31) {
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED)
                perms.add(Manifest.permission.BLUETOOTH_SCAN);
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED)
                perms.add(Manifest.permission.BLUETOOTH_CONNECT);
        }
        if (Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission(Manifest.permission.NEARBY_WIFI_DEVICES) != PackageManager.PERMISSION_GRANTED)
                perms.add(Manifest.permission.NEARBY_WIFI_DEVICES);
        } else {
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED)
                perms.add(Manifest.permission.ACCESS_FINE_LOCATION);
        }
        if (!perms.isEmpty()) requestPermissions(perms.toArray(new String[0]), 100);
    }

    private boolean haveBlePermissions() {
        if (Build.VERSION.SDK_INT < 31) return true;
        return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean haveWifiPermission() {
        if (Build.VERSION.SDK_INT >= 33)
            return checkSelfPermission(Manifest.permission.NEARBY_WIFI_DEVICES) == PackageManager.PERMISSION_GRANTED;
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private void scanAndConnect() {
        if (!haveBlePermissions()) {
            requestNeededPermissions();
            log("Bluetooth permission is required");
            return;
        }
        if (btAdapter == null || !btAdapter.isEnabled()) {
            log("Bluetooth is off");
            return;
        }
        if (gatt != null) {
            try { gatt.disconnect(); } catch (Exception ignored) {}
            try { gatt.close(); } catch (Exception ignored) {}
            gatt = null;
        }
        bleReady = false;
        scanner = btAdapter.getBluetoothLeScanner();
        if (scanner == null) {
            log("BLE scanner unavailable");
            return;
        }
        scanning = true;
        log("Scanning for CY01...");
        scanner.startScan(scanCallback);
        main.postDelayed(() -> {
            if (scanning) {
                scanner.stopScan(scanCallback);
                scanning = false;
                log("Scan timeout: CY01 not found");
            }
        }, 15000);
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            BluetoothDevice d = result.getDevice();
            String name = null;
            try { name = d.getName(); } catch (SecurityException ignored) {}
            if (name == null && result.getScanRecord() != null) name = result.getScanRecord().getDeviceName();
            if (name == null) return;
            String normalized = name.replace("_", " ").toUpperCase(Locale.ROOT);
            if (normalized.startsWith("CY 01") || normalized.startsWith("CY01")) {
                if (scanning) {
                    scanner.stopScan(this);
                    scanning = false;
                }
                log("Found " + name + " / " + d.getAddress());
                status("BLE: connecting | P2P: " + (p2pConnected ? "connected" : "disconnected"));
                gatt = d.connectGatt(MainActivity.this, false, gattCallback, BluetoothDevice.TRANSPORT_LE);
            }
        }

        @Override
        public void onScanFailed(int errorCode) {
            log("BLE scan failed: " + errorCode);
        }
    };

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt g, int statusCode, int newState) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                log("BLE connected; discovering services");
                g.discoverServices();
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                bleReady = false;
                log("BLE disconnected, status=" + statusCode);
                status("BLE: disconnected | P2P: " + (p2pConnected ? "connected" : "disconnected"));
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt g, int statusCode) {
            BluetoothGattService svc = g.getService(SERVICE_UUID);
            if (svc == null) {
                log("HeyCyan service de5bf728 not found");
                return;
            }
            writeChar = svc.getCharacteristic(WRITE_UUID);
            notifyChar = svc.getCharacteristic(NOTIFY_UUID);
            if (writeChar == null || notifyChar == null) {
                log("HeyCyan write/notify characteristic not found");
                return;
            }
            boolean local = g.setCharacteristicNotification(notifyChar, true);
            BluetoothGattDescriptor cccd = notifyChar.getDescriptor(CCCD_UUID);
            if (cccd == null) {
                log("CCCD descriptor missing");
                return;
            }
            cccd.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            boolean queued = g.writeDescriptor(cccd);
            log("Enable notifications: local=" + local + " queued=" + queued);
        }

        @Override
        public void onDescriptorWrite(BluetoothGatt g, BluetoothGattDescriptor descriptor, int statusCode) {
            if (CCCD_UUID.equals(descriptor.getUuid())) {
                bleReady = statusCode == BluetoothGatt.GATT_SUCCESS;
                log("BLE command channel ready=" + bleReady + " status=" + statusCode);
                status("BLE: " + (bleReady ? "ready" : "error") + " | P2P: " + (p2pConnected ? "connected" : "disconnected"));
            }
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt g, BluetoothGattCharacteristic characteristic) {
            if (NOTIFY_UUID.equals(characteristic.getUuid())) handleRx(characteristic.getValue());
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt g, BluetoothGattCharacteristic characteristic, byte[] value) {
            if (NOTIFY_UUID.equals(characteristic.getUuid())) handleRx(value);
        }
    };

    private synchronized void handleRx(byte[] chunk) {
        if (chunk == null || chunk.length == 0) return;
        try {
            if (rx.size() == 0 && (chunk[0] & 0xFF) != 0xBC) return;
            rx.write(chunk);
            byte[] data = rx.toByteArray();
            while (data.length >= 6) {
                if ((data[0] & 0xFF) != 0xBC) {
                    rx.reset();
                    return;
                }
                int payloadLen = (data[2] & 0xFF) | ((data[3] & 0xFF) << 8);
                int frameLen = 6 + payloadLen;
                if (data.length < frameLen) return;
                byte[] frame = Arrays.copyOfRange(data, 0, frameLen);
                processFrame(frame);
                data = Arrays.copyOfRange(data, frameLen, data.length);
                rx.reset();
                rx.write(data);
            }
        } catch (Exception e) {
            log("RX parse error: " + e.getMessage());
            rx.reset();
        }
    }

    private void processFrame(byte[] frame) {
        int opcode = frame[1] & 0xFF;
        int payloadLen = (frame[2] & 0xFF) | ((frame[3] & 0xFF) << 8);
        byte[] payload = Arrays.copyOfRange(frame, 6, 6 + payloadLen);

        if (opcode != 0x59 && opcode != 0x73) log("RX " + hex(frame));

        if (opcode == 0x42 && payload.length >= 2) {
            log("Battery: " + (payload[0] & 0xFF) + "% charging=" + ((payload[1] & 0xFF) != 0));
        } else if (opcode == 0x47) {
            if (payload.length > 6) {
                boolean liveReview = (payload[6] & 0x80) != 0;
                log("Capability supportLiveReview=" + liveReview + " (raw flag byte 0x" + String.format(Locale.US, "%02X", payload[6]) + ")");
            }
        } else if (opcode == 0x41 && payload.length >= 2) {
            if ((payload[0] & 0xFF) == 0x02 && (payload[1] & 0xFF) == 0x03 && payload.length >= 6) {
                glassesIp = (payload[2] & 0xFF) + "." + (payload[3] & 0xFF) + "." + (payload[4] & 0xFF) + "." + (payload[5] & 0xFF);
                log("Glasses P2P IP = " + glassesIp);
                main.postDelayed(this::runProbeSuite, 1200);
            }
        }
    }

    private void sendFrame(int opcode, byte[] payload) {
        if (!bleReady || gatt == null || writeChar == null) {
            log("BLE channel is not ready");
            return;
        }
        byte[] frame = buildFrame(opcode, payload);
        writeChar.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE);
        writeChar.setValue(frame);
        boolean ok = gatt.writeCharacteristic(writeChar);
        log("TX " + hex(frame) + " queued=" + ok);
    }

    private byte[] buildFrame(int opcode, byte[] payload) {
        int n = payload.length;
        int crc = n == 0 ? 0xFFFF : crc16Modbus(payload);
        byte[] out = new byte[6 + n];
        out[0] = (byte) 0xBC;
        out[1] = (byte) opcode;
        out[2] = (byte) (n & 0xFF);
        out[3] = (byte) ((n >> 8) & 0xFF);
        out[4] = (byte) (crc & 0xFF);
        out[5] = (byte) ((crc >> 8) & 0xFF);
        System.arraycopy(payload, 0, out, 6, n);
        return out;
    }

    private int crc16Modbus(byte[] data) {
        int crc = 0xFFFF;
        for (byte b : data) {
            crc ^= b & 0xFF;
            for (int i = 0; i < 8; i++) {
                if ((crc & 1) != 0) crc = (crc >> 1) ^ 0xA001;
                else crc >>= 1;
            }
        }
        return crc & 0xFFFF;
    }

    private void startLiveTest() {
        if (!bleReady) {
            log("Connect CY01 over BLE first");
            return;
        }
        if (!haveWifiPermission()) {
            requestNeededPermissions();
            log("Nearby Wi-Fi permission is required");
            return;
        }
        p2pConnectIssued = false;
        glassesIp = null;
        p2pNetwork = null;
        log("Starting HeyCyan preview P2P command [02 01 14 01]");
        sendFrame(0x41, new byte[]{0x02, 0x01, 0x14, 0x01});
        main.postDelayed(this::discoverP2pPeers, 900);

        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);
        autoStopRunnable = () -> {
            log("Safety timeout reached: stopping preview and P2P");
            stopPreviewAndP2p();
        };
        main.postDelayed(autoStopRunnable, 60000);
    }

    private void setupP2pReceiver() {
        IntentFilter f = new IntentFilter();
        f.addAction(WifiP2pManager.WIFI_P2P_STATE_CHANGED_ACTION);
        f.addAction(WifiP2pManager.WIFI_P2P_PEERS_CHANGED_ACTION);
        f.addAction(WifiP2pManager.WIFI_P2P_CONNECTION_CHANGED_ACTION);
        f.addAction(WifiP2pManager.WIFI_P2P_THIS_DEVICE_CHANGED_ACTION);
        p2pReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                String action = intent.getAction();
                if (WifiP2pManager.WIFI_P2P_PEERS_CHANGED_ACTION.equals(action)) {
                    requestPeers();
                } else if (WifiP2pManager.WIFI_P2P_CONNECTION_CHANGED_ACTION.equals(action)) {
                    requestConnectionInfo();
                }
            }
        };
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(p2pReceiver, f, RECEIVER_NOT_EXPORTED);
        else registerReceiver(p2pReceiver, f);
    }

    private void discoverP2pPeers() {
        if (!haveWifiPermission()) return;
        p2pManager.discoverPeers(p2pChannel, new WifiP2pManager.ActionListener() {
            @Override public void onSuccess() { log("Wi-Fi Direct discovery started"); }
            @Override public void onFailure(int reason) { log("Wi-Fi Direct discovery failed: " + reason); }
        });
    }

    private void requestPeers() {
        if (!haveWifiPermission()) return;
        p2pManager.requestPeers(p2pChannel, this::onPeers);
    }

    private void onPeers(WifiP2pDeviceList list) {
        for (WifiP2pDevice d : list.getDeviceList()) {
            String name = d.deviceName == null ? "" : d.deviceName;
            if (name.replace("_", " ").toUpperCase(Locale.ROOT).startsWith("CY 01") && !p2pConnectIssued) {
                p2pConnectIssued = true;
                log("Wi-Fi Direct peer found: " + name + " / " + d.deviceAddress);
                WifiP2pConfig cfg = new WifiP2pConfig();
                cfg.deviceAddress = d.deviceAddress;
                p2pManager.connect(p2pChannel, cfg, new WifiP2pManager.ActionListener() {
                    @Override public void onSuccess() { log("Wi-Fi Direct connect requested"); }
                    @Override public void onFailure(int reason) {
                        p2pConnectIssued = false;
                        log("Wi-Fi Direct connect failed: " + reason);
                    }
                });
                return;
            }
        }
    }

    private void requestConnectionInfo() {
        if (!haveWifiPermission()) return;
        p2pManager.requestConnectionInfo(p2pChannel, this::onConnectionInfo);
    }

    private void onConnectionInfo(WifiP2pInfo info) {
        p2pConnected = info != null && info.groupFormed;
        if (p2pConnected) {
            log("Wi-Fi Direct connected. phoneIsGroupOwner=" + info.isGroupOwner + " groupOwner=" +
                    (info.groupOwnerAddress == null ? "?" : info.groupOwnerAddress.getHostAddress()));
            status("BLE: " + (bleReady ? "ready" : "connected") + " | P2P: connected");
            main.postDelayed(() -> sendFrame(0x41, new byte[]{0x02, 0x03}), 500);
            main.postDelayed(this::refreshP2pNetwork, 900);
        } else {
            status("BLE: " + (bleReady ? "ready" : "disconnected") + " | P2P: disconnected");
        }
    }

    private void refreshP2pNetwork() {
        p2pNetwork = findP2pNetwork();
        log("Android P2P Network binding = " + (p2pNetwork == null ? "not found yet" : p2pNetwork.toString()));
    }

    private Network findP2pNetwork() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        Network fallbackWifi = null;
        for (Network n : cm.getAllNetworks()) {
            NetworkCapabilities caps = cm.getNetworkCapabilities(n);
            if (caps == null || !caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) continue;
            fallbackWifi = n;
            LinkProperties lp = cm.getLinkProperties(n);
            if (lp == null) continue;
            for (LinkAddress la : lp.getLinkAddresses()) {
                InetAddress a = la.getAddress();
                if (a instanceof Inet4Address && a.getHostAddress() != null && a.getHostAddress().startsWith("192.168.49.")) {
                    return n;
                }
            }
        }
        return fallbackWifi;
    }

    private void runProbeSuite() {
        final String ip = glassesIp != null ? glassesIp : "192.168.49.96";
        log("Probe suite starting for " + ip);
        io.execute(() -> {
            Network network = p2pNetwork != null ? p2pNetwork : findP2pNetwork();
            if (network != null) {
                p2pNetwork = network;
                log("Probe sockets bound to Android network " + network);
            } else {
                log("WARNING: P2P Network object not found; probes use default route");
            }

            probeHttp(network, ip, "/files/media.config", "HeyCyan file-server classification");
            probeRtspSet(network, ip, "before HTTP trigger");

            log("Trying Eyevue-inspired local HTTP trigger (experimental GET only)");
            probeHttp(network, ip, "/?custom=1&cmd=3001&par=1", "Eyevue-style stream trigger");
            probeRtspSet(network, ip, "after HTTP trigger");

            log("Probe suite finished");
        });
    }

    private void probeHttp(Network network, String ip, String path, String label) {
        HttpURLConnection c = null;
        try {
            URL u = new URL("http://" + ip + path);
            c = (HttpURLConnection) (network != null ? network.openConnection(u) : u.openConnection());
            c.setConnectTimeout(1200);
            c.setReadTimeout(1200);
            c.setRequestMethod("GET");
            c.setRequestProperty("User-Agent", "okhttp/4.9.2");
            c.setRequestProperty("Connection", "close");
            int code = c.getResponseCode();
            String body = readSmall(code >= 400 ? c.getErrorStream() : c.getInputStream());
            log("HTTP " + label + ": " + code + " " + shortText(body));
        } catch (Exception e) {
            log("HTTP " + label + ": " + e.getClass().getSimpleName() + " - " + e.getMessage());
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private void probeRtspSet(Network network, String ip, String phase) {
        int[] ports = {554, 8554};
        String[] paths = {"/testH264VideoStreamer", "/xxx.mov", "/h264", "/live", "/stream", "/"};
        boolean anyTcp = false;
        for (int port : ports) {
            for (String path : paths) {
                RtspResult r = probeRtsp(network, ip, port, path);
                if (r.tcpOpen) anyTcp = true;
                if (r.tcpOpen || r.firstLine != null) {
                    log("RTSP " + phase + " " + port + path + " -> " + (r.firstLine == null ? "TCP OPEN, no RTSP reply" : r.firstLine));
                }
            }
        }
        if (!anyTcp) log("RTSP " + phase + ": ports 554/8554 did not accept TCP connections");
    }

    private RtspResult probeRtsp(Network network, String ip, int port, String path) {
        Socket s = null;
        try {
            s = network != null ? network.getSocketFactory().createSocket() : new Socket();
            s.connect(new InetSocketAddress(ip, port), 550);
            s.setSoTimeout(900);
            String uri = "rtsp://" + ip + ":" + port + path;
            String req = "OPTIONS " + uri + " RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: CY01StreamLab/0.1\r\n\r\n";
            OutputStream os = s.getOutputStream();
            os.write(req.getBytes(StandardCharsets.US_ASCII));
            os.flush();
            BufferedReader br = new BufferedReader(new InputStreamReader(s.getInputStream(), StandardCharsets.US_ASCII));
            String line = br.readLine();
            return new RtspResult(true, line);
        } catch (Exception e) {
            return new RtspResult(false, null);
        } finally {
            if (s != null) try { s.close(); } catch (Exception ignored) {}
        }
    }

    private String readSmall(InputStream in) {
        if (in == null) return "";
        try {
            byte[] buf = new byte[512];
            int n = in.read(buf);
            if (n <= 0) return "";
            return new String(buf, 0, n, StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "";
        } finally {
            try { in.close(); } catch (Exception ignored) {}
        }
    }

    private String shortText(String s) {
        if (s == null) return "";
        s = s.replace('\n', ' ').replace('\r', ' ').trim();
        return s.length() > 120 ? s.substring(0, 120) + "..." : s;
    }

    private void stopPreviewAndP2p() {
        if (autoStopRunnable != null) {
            main.removeCallbacks(autoStopRunnable);
            autoStopRunnable = null;
        }
        if (bleReady) {
            log("Stopping preview [02 01 15 01]");
            sendFrame(0x41, new byte[]{0x02, 0x01, 0x15, 0x01});
        }
        p2pManager.removeGroup(p2pChannel, new WifiP2pManager.ActionListener() {
            @Override public void onSuccess() {
                p2pConnected = false;
                p2pConnectIssued = false;
                p2pNetwork = null;
                log("Wi-Fi Direct group removed");
                status("BLE: " + (bleReady ? "ready" : "disconnected") + " | P2P: disconnected");
            }
            @Override public void onFailure(int reason) {
                p2pConnected = false;
                p2pConnectIssued = false;
                p2pNetwork = null;
                log("Wi-Fi Direct removeGroup result=" + reason);
            }
        });
    }

    private void openWifiDirectSettings() {
        try {
            startActivity(new Intent(Settings.ACTION_WIFI_SETTINGS));
        } catch (Exception e) {
            startActivity(new Intent(Settings.ACTION_WIRELESS_SETTINGS));
        }
    }

    private void status(String s) {
        runOnUiThread(() -> status.setText(s));
    }

    private void log(String s) {
        String time = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        runOnUiThread(() -> logView.append(time + "  " + s + "\n"));
    }

    private String hex(byte[] a) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < a.length; i++) {
            if (i > 0) sb.append('-');
            sb.append(String.format(Locale.US, "%02X", a[i] & 0xFF));
        }
        return sb.toString();
    }

    @Override
    protected void onDestroy() {
        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);
        try { if (p2pReceiver != null) unregisterReceiver(p2pReceiver); } catch (Exception ignored) {}
        try { if (gatt != null) gatt.disconnect(); } catch (Exception ignored) {}
        try { if (gatt != null) gatt.close(); } catch (Exception ignored) {}
        io.shutdownNow();
        super.onDestroy();
    }

    private static final class RtspResult {
        final boolean tcpOpen;
        final String firstLine;
        RtspResult(boolean tcpOpen, String firstLine) {
            this.tcpOpen = tcpOpen;
            this.firstLine = firstLine;
        }
    }
}
