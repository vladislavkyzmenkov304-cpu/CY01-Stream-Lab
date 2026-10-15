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
import android.content.ClipData;
import android.content.ClipboardManager;
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
    private boolean bleReady;
    private boolean scanning;

    private WifiP2pManager p2pManager;
    private WifiP2pManager.Channel p2pChannel;
    private BroadcastReceiver p2pReceiver;
    private boolean p2pConnectIssued;
    private boolean p2pConnected;
    private boolean p2pDiscoveryStarted;
    private int p2pDiscoveryAttempt;

    private boolean previewAckSeen;
    private String previewSsid;
    private String previewPassword;
    private volatile String glassesIp;
    private volatile Network p2pNetwork;
    private Runnable autoStopRunnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();

        BluetoothManager bm = (BluetoothManager) getSystemService(BLUETOOTH_SERVICE);
        btAdapter = bm == null ? null : bm.getAdapter();
        p2pManager = (WifiP2pManager) getSystemService(WIFI_P2P_SERVICE);
        if (p2pManager != null) {
            p2pChannel = p2pManager.initialize(this, getMainLooper(), () -> log("Wi-Fi Direct channel lost"));
            setupP2pReceiver();
        }

        requestNeededPermissions();
        log("CY01 Stream Lab v0.2 started");
        log("v0.2 waits for the preview ACK before P2P discovery and retries Android BUSY responses");
    }

    private void buildUi() {
        ScrollView root = new ScrollView(this);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int p = dp(14);
        box.setPadding(p, p, p, p);
        root.addView(box);

        TextView title = new TextView(this);
        title.setText("CY01 Stream Lab v0.2");
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
        box.addView(button("COPY LOG", v -> copyLog()));
        box.addView(button("STOP + DISCONNECT P2P", v -> stopPreviewAndP2p()));
        box.addView(button("ANDROID WIFI DIRECT SETTINGS", v -> openWifiDirectSettings()));

        TextView note = new TextView(this);
        note.setText("No firmware flashing, OTA, reset, restart or unknown BLE brute force. Preview is stopped automatically after 60 seconds.");
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
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
                perms.add(Manifest.permission.BLUETOOTH_SCAN);
            }
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                perms.add(Manifest.permission.BLUETOOTH_CONNECT);
            }
        }
        if (Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission(Manifest.permission.NEARBY_WIFI_DEVICES) != PackageManager.PERMISSION_GRANTED) {
                perms.add(Manifest.permission.NEARBY_WIFI_DEVICES);
            }
        } else if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            perms.add(Manifest.permission.ACCESS_FINE_LOCATION);
        }
        if (!perms.isEmpty()) {
            requestPermissions(perms.toArray(new String[0]), 100);
        }
    }

    private boolean haveBlePermissions() {
        if (Build.VERSION.SDK_INT < 31) return true;
        return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean haveWifiPermission() {
        if (Build.VERSION.SDK_INT >= 33) {
            return checkSelfPermission(Manifest.permission.NEARBY_WIFI_DEVICES) == PackageManager.PERMISSION_GRANTED;
        }
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

        closeGatt();
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
            if (scanning && scanner != null) {
                try { scanner.stopScan(scanCallback); } catch (Exception ignored) {}
                scanning = false;
                log("Scan timeout: CY01 not found");
            }
        }, 15000);
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            BluetoothDevice device = result.getDevice();
            String name = null;
            try { name = device.getName(); } catch (SecurityException ignored) {}
            if (name == null && result.getScanRecord() != null) {
                name = result.getScanRecord().getDeviceName();
            }
            if (!looksLikeCy01(name)) return;

            if (scanning && scanner != null) {
                try { scanner.stopScan(this); } catch (Exception ignored) {}
                scanning = false;
            }
            log("Found " + name + " / " + device.getAddress());
            status("BLE: connecting | P2P: " + (p2pConnected ? "connected" : "disconnected"));
            gatt = device.connectGatt(MainActivity.this, false, gattCallback, BluetoothDevice.TRANSPORT_LE);
        }

        @Override
        public void onScanFailed(int errorCode) {
            scanning = false;
            log("BLE scan failed: " + errorCode);
        }
    };

    private boolean looksLikeCy01(String name) {
        if (name == null) return false;
        String n = name.replace("_", " ").toUpperCase(Locale.ROOT);
        return n.startsWith("CY 01") || n.startsWith("CY01") || n.startsWith("EY 01");
    }

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
            BluetoothGattService service = g.getService(SERVICE_UUID);
            if (service == null) {
                log("HeyCyan service de5bf728 not found");
                return;
            }
            writeChar = service.getCharacteristic(WRITE_UUID);
            notifyChar = service.getCharacteristic(NOTIFY_UUID);
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
            if (!CCCD_UUID.equals(descriptor.getUuid())) return;
            bleReady = statusCode == BluetoothGatt.GATT_SUCCESS;
            log("BLE command channel ready=" + bleReady + " status=" + statusCode);
            status("BLE: " + (bleReady ? "ready" : "error") + " | P2P: " + (p2pConnected ? "connected" : "disconnected"));
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
                int payloadLen = le16(data, 2);
                int frameLen = 6 + payloadLen;
                if (data.length < frameLen) return;

                byte[] frame = Arrays.copyOfRange(data, 0, frameLen);
                processFrame(frame);
                data = Arrays.copyOfRange(data, frameLen, data.length);
                rx.reset();
                rx.write(data);
            }
        } catch (Exception e) {
            rx.reset();
            log("RX parse error: " + e.getMessage());
        }
    }

    private void processFrame(byte[] frame) {
        int opcode = frame[1] & 0xFF;
        int payloadLen = le16(frame, 2);
        byte[] payload = Arrays.copyOfRange(frame, 6, 6 + payloadLen);

        if (opcode != 0x59 && opcode != 0x73) {
            log("RX " + hex(frame));
        }

        if (opcode == 0x42 && payload.length >= 2) {
            log("Battery: " + (payload[0] & 0xFF) + "% charging=" + ((payload[1] & 0xFF) != 0));
            return;
        }

        if (opcode == 0x47 && payload.length > 6) {
            boolean liveReview = (payload[6] & 0x80) != 0;
            log("Capability supportLiveReview=" + liveReview + " (raw flag byte 0x" + String.format(Locale.US, "%02X", payload[6]) + ")");
            return;
        }

        if (opcode != 0x41 || payload.length < 2) return;

        if ((payload[0] & 0xFF) == 0x02 && (payload[1] & 0xFF) == 0x03 && payload.length >= 6) {
            glassesIp = (payload[2] & 0xFF) + "." + (payload[3] & 0xFF) + "." + (payload[4] & 0xFF) + "." + (payload[5] & 0xFF);
            log("Glasses P2P IP = " + glassesIp);
            main.postDelayed(this::refreshP2pNetwork, 300);
            main.postDelayed(this::runProbeSuite, 1200);
            return;
        }

        if (isPreviewStartAck(payload)) {
            previewAckSeen = true;
            parsePreviewCredentials(payload);
            log("Preview start ACK received. CY01 finished preparing its Wi-Fi side.");
            main.postDelayed(() -> beginP2pDiscovery("preview ACK"), 600);
        }
    }

    private boolean isPreviewStartAck(byte[] payload) {
        return payload.length >= 4
                && (payload[0] & 0xFF) == 0x02
                && (payload[1] & 0xFF) == 0x01
                && (payload[2] & 0xFF) == 0x14
                && (payload[3] & 0xFF) == 0x01;
    }

    private void parsePreviewCredentials(byte[] payload) {
        if (payload.length < 8) return;
        int ssidLen = le16(payload, 4);
        int passwordLen = le16(payload, 6);
        int start = 8;
        if (ssidLen < 0 || passwordLen < 0 || start + ssidLen + passwordLen > payload.length) {
            log("Preview ACK carries length fields but they do not fit this frame");
            return;
        }

        previewSsid = new String(payload, start, ssidLen, StandardCharsets.US_ASCII);
        previewPassword = new String(payload, start + ssidLen, passwordLen, StandardCharsets.US_ASCII);
        log("Preview Wi-Fi data: SSID=\"" + previewSsid + "\" passwordLength=" + previewPassword.length());
    }

    private int le16(byte[] data, int offset) {
        if (offset < 0 || offset + 1 >= data.length) return -1;
        return (data[offset] & 0xFF) | ((data[offset + 1] & 0xFF) << 8);
    }

    private void sendFrame(int opcode, byte[] payload) {
        if (!bleReady || gatt == null || writeChar == null) {
            log("BLE channel is not ready");
            return;
        }
        byte[] frame = buildFrame(opcode, payload);
        writeChar.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE);
        writeChar.setValue(frame);
        boolean queued = gatt.writeCharacteristic(writeChar);
        log("TX " + hex(frame) + " queued=" + queued);
    }

    private byte[] buildFrame(int opcode, byte[] payload) {
        int n = payload.length;
        int crc = n == 0 ? 0xFFFF : crc16Modbus(payload);
        byte[] frame = new byte[6 + n];
        frame[0] = (byte) 0xBC;
        frame[1] = (byte) opcode;
        frame[2] = (byte) (n & 0xFF);
        frame[3] = (byte) ((n >> 8) & 0xFF);
        frame[4] = (byte) (crc & 0xFF);
        frame[5] = (byte) ((crc >> 8) & 0xFF);
        System.arraycopy(payload, 0, frame, 6, n);
        return frame;
    }

    private int crc16Modbus(byte[] data) {
        int crc = 0xFFFF;
        for (byte b : data) {
            crc ^= b & 0xFF;
            for (int i = 0; i < 8; i++) {
                crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xA001 : crc >> 1;
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
        if (p2pManager == null || p2pChannel == null) {
            log("Wi-Fi Direct API unavailable on this phone");
            return;
        }

        previewAckSeen = false;
        previewSsid = null;
        previewPassword = null;
        glassesIp = null;
        p2pNetwork = null;
        p2pConnected = false;
        p2pConnectIssued = false;
        p2pDiscoveryStarted = false;
        p2pDiscoveryAttempt = 0;

        log("Starting HeyCyan preview P2P command [02 01 14 01]");
        sendFrame(0x41, new byte[]{0x02, 0x01, 0x14, 0x01});
        log("Waiting for the 0x14 ACK before starting Android P2P discovery");

        main.postDelayed(() -> {
            if (!previewAckSeen && !p2pConnected) {
                log("No preview ACK after 3.5 s; using fallback P2P discovery");
                beginP2pDiscovery("fallback timer");
            }
        }, 3500);

        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);
        autoStopRunnable = () -> {
            log("Safety timeout reached: stopping preview and P2P");
            stopPreviewAndP2p();
        };
        main.postDelayed(autoStopRunnable, 60000);
    }

    private void setupP2pReceiver() {
        IntentFilter filter = new IntentFilter();
        filter.addAction(WifiP2pManager.WIFI_P2P_STATE_CHANGED_ACTION);
        filter.addAction(WifiP2pManager.WIFI_P2P_PEERS_CHANGED_ACTION);
        filter.addAction(WifiP2pManager.WIFI_P2P_CONNECTION_CHANGED_ACTION);
        filter.addAction(WifiP2pManager.WIFI_P2P_THIS_DEVICE_CHANGED_ACTION);

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

        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(p2pReceiver, filter, RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(p2pReceiver, filter);
        }
    }

    private void beginP2pDiscovery(String reason) {
        if (p2pConnected || p2pConnectIssued) return;
        if (!haveWifiPermission() || p2pManager == null || p2pChannel == null) return;

        if (!p2pDiscoveryStarted) {
            p2pDiscoveryStarted = true;
            log("Starting Wi-Fi Direct discovery after " + reason);
        }
        requestPeers();
        discoverP2pAttempt();
    }

    private void discoverP2pAttempt() {
        if (p2pConnected || p2pConnectIssued) return;
        if (p2pDiscoveryAttempt >= 5) {
            log("Wi-Fi Direct discovery retries exhausted. Manual settings button remains available.");
            return;
        }

        p2pDiscoveryAttempt++;
        final int attempt = p2pDiscoveryAttempt;
        p2pManager.discoverPeers(p2pChannel, new WifiP2pManager.ActionListener() {
            @Override
            public void onSuccess() {
                log("Wi-Fi Direct discovery started, attempt=" + attempt);
                main.postDelayed(MainActivity.this::requestPeers, 500);
                main.postDelayed(MainActivity.this::requestPeers, 1200);
            }

            @Override
            public void onFailure(int reason) {
                log("Wi-Fi Direct discovery failed: " + p2pReason(reason) + " (" + reason + "), attempt=" + attempt);
                requestPeers();
                if (reason != WifiP2pManager.P2P_UNSUPPORTED && attempt < 5 && !p2pConnected && !p2pConnectIssued) {
                    long delay = reason == WifiP2pManager.BUSY ? 1500L : 1000L;
                    log("Scheduling P2P retry in " + delay + " ms");
                    main.postDelayed(MainActivity.this::discoverP2pAttempt, delay);
                }
            }
        });
    }

    private String p2pReason(int reason) {
        if (reason == WifiP2pManager.BUSY) return "BUSY";
        if (reason == WifiP2pManager.P2P_UNSUPPORTED) return "P2P_UNSUPPORTED";
        if (reason == WifiP2pManager.ERROR) return "ERROR";
        return "reason";
    }

    private void requestPeers() {
        if (!haveWifiPermission() || p2pManager == null || p2pChannel == null) return;
        p2pManager.requestPeers(p2pChannel, this::onPeers);
    }

    private void onPeers(WifiP2pDeviceList list) {
        if (list == null) return;
        for (WifiP2pDevice device : list.getDeviceList()) {
            String name = device.deviceName == null ? "" : device.deviceName;
            if (!looksLikeCy01(name)) continue;

            log("Wi-Fi Direct peer found: " + name + " / " + device.deviceAddress);
            if (p2pConnected || p2pConnectIssued) return;
            p2pConnectIssued = true;

            WifiP2pConfig config = new WifiP2pConfig();
            config.deviceAddress = device.deviceAddress;
            p2pManager.connect(p2pChannel, config, new WifiP2pManager.ActionListener() {
                @Override
                public void onSuccess() {
                    log("Wi-Fi Direct connect requested");
                }

                @Override
                public void onFailure(int reason) {
                    p2pConnectIssued = false;
                    log("Wi-Fi Direct connect failed: " + p2pReason(reason) + " (" + reason + ")");
                    if (reason == WifiP2pManager.BUSY && p2pDiscoveryAttempt < 5) {
                        main.postDelayed(MainActivity.this::discoverP2pAttempt, 1500);
                    }
                }
            });
            return;
        }
    }

    private void requestConnectionInfo() {
        if (!haveWifiPermission() || p2pManager == null || p2pChannel == null) return;
        p2pManager.requestConnectionInfo(p2pChannel, this::onConnectionInfo);
    }

    private void onConnectionInfo(WifiP2pInfo info) {
        p2pConnected = info != null && info.groupFormed;
        if (!p2pConnected) {
            status("BLE: " + (bleReady ? "ready" : "disconnected") + " | P2P: disconnected");
            return;
        }

        String owner = info.groupOwnerAddress == null ? "?" : info.groupOwnerAddress.getHostAddress();
        log("Wi-Fi Direct connected. phoneIsGroupOwner=" + info.isGroupOwner + " groupOwner=" + owner);
        status("BLE: " + (bleReady ? "ready" : "connected") + " | P2P: connected");

        main.postDelayed(() -> sendFrame(0x41, new byte[]{0x02, 0x03}), 400);
        main.postDelayed(this::refreshP2pNetwork, 700);
        main.postDelayed(() -> {
            if (glassesIp == null) {
                log("No BLE IP reply yet; retrying [02 03]");
                sendFrame(0x41, new byte[]{0x02, 0x03});
            }
        }, 1800);
    }

    private void refreshP2pNetwork() {
        p2pNetwork = findP2pNetwork();
        log("Android P2P Network binding = " + (p2pNetwork == null ? "not found yet" : p2pNetwork.toString()));
    }

    private Network findP2pNetwork() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        if (cm == null) return null;
        Network fallbackWifi = null;

        for (Network network : cm.getAllNetworks()) {
            NetworkCapabilities caps = cm.getNetworkCapabilities(network);
            if (caps == null || !caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) continue;
            fallbackWifi = network;

            LinkProperties lp = cm.getLinkProperties(network);
            if (lp == null) continue;
            for (LinkAddress la : lp.getLinkAddresses()) {
                InetAddress address = la.getAddress();
                if (address instanceof Inet4Address) {
                    String host = address.getHostAddress();
                    if (host != null && host.startsWith("192.168.49.")) {
                        return network;
                    }
                }
            }
        }
        return fallbackWifi;
    }

    private void runProbeSuite() {
        final String ip = glassesIp != null ? glassesIp : "192.168.49.96";
        log("Probe suite starting for " + ip + (glassesIp == null ? " (confirmed lab fallback IP)" : ""));

        io.execute(() -> {
            Network network = p2pNetwork != null ? p2pNetwork : findP2pNetwork();
            if (network != null) {
                p2pNetwork = network;
                log("Probe sockets bound to Android network " + network);
            } else {
                log("WARNING: P2P Network object not found; probes use default route");
            }

            probeHttp(network, ip, "/files/media.config", "HeyCyan media.config");
            probeRtspSet(network, ip, "before HTTP trigger");

            log("Trying Eyevue-inspired local HTTP trigger (experimental GET only)");
            probeHttp(network, ip, "/?custom=1&cmd=3001&par=1", "Eyevue-style trigger");
            probeRtspSet(network, ip, "after HTTP trigger");
            log("Probe suite finished");
        });
    }

    private void probeHttp(Network network, String ip, String path, String label) {
        HttpURLConnection connection = null;
        try {
            URL url = new URL("http://" + ip + path);
            connection = (HttpURLConnection) (network != null ? network.openConnection(url) : url.openConnection());
            connection.setConnectTimeout(1400);
            connection.setReadTimeout(1400);
            connection.setRequestMethod("GET");
            connection.setRequestProperty("User-Agent", "okhttp/4.9.2");
            connection.setRequestProperty("Connection", "close");

            int code = connection.getResponseCode();
            String body = readSmall(code >= 400 ? connection.getErrorStream() : connection.getInputStream());
            log("HTTP " + label + ": " + code + " " + shortText(body));
        } catch (Exception e) {
            log("HTTP " + label + ": " + e.getClass().getSimpleName() + " - " + e.getMessage());
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private void probeRtspSet(Network network, String ip, String phase) {
        int[] ports = {554, 8554};
        String[] paths = {"/testH264VideoStreamer", "/xxx.mov", "/h264", "/live", "/stream", "/"};
        boolean anyTcp = false;

        for (int port : ports) {
            for (String path : paths) {
                RtspResult result = probeRtsp(network, ip, port, path);
                if (result.tcpOpen) anyTcp = true;
                if (result.tcpOpen || result.firstLine != null) {
                    log("RTSP " + phase + " " + port + path + " -> " + (result.firstLine == null ? "TCP OPEN, no RTSP reply" : result.firstLine));
                }
            }
        }
        if (!anyTcp) {
            log("RTSP " + phase + ": ports 554/8554 did not accept TCP connections");
        }
    }

    private RtspResult probeRtsp(Network network, String ip, int port, String path) {
        Socket socket = null;
        try {
            socket = network != null ? network.getSocketFactory().createSocket() : new Socket();
            socket.connect(new InetSocketAddress(ip, port), 650);
            socket.setSoTimeout(1000);

            String uri = "rtsp://" + ip + ":" + port + path;
            String request = "OPTIONS " + uri + " RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: CY01StreamLab/0.2\r\n\r\n";
            OutputStream os = socket.getOutputStream();
            os.write(request.getBytes(StandardCharsets.US_ASCII));
            os.flush();

            BufferedReader br = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.US_ASCII));
            return new RtspResult(true, br.readLine());
        } catch (Exception e) {
            return new RtspResult(false, null);
        } finally {
            if (socket != null) {
                try { socket.close(); } catch (Exception ignored) {}
            }
        }
    }

    private String readSmall(InputStream in) {
        if (in == null) return "";
        try {
            byte[] buf = new byte[512];
            int n = in.read(buf);
            return n <= 0 ? "" : new String(buf, 0, n, StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "";
        } finally {
            try { in.close(); } catch (Exception ignored) {}
        }
    }

    private String shortText(String text) {
        if (text == null) return "";
        String value = text.replace('\n', ' ').replace('\r', ' ').trim();
        return value.length() > 140 ? value.substring(0, 140) + "..." : value;
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

        if (p2pManager == null || p2pChannel == null) return;
        p2pManager.removeGroup(p2pChannel, new WifiP2pManager.ActionListener() {
            @Override
            public void onSuccess() {
                resetP2pState();
                log("Wi-Fi Direct group removed");
            }

            @Override
            public void onFailure(int reason) {
                resetP2pState();
                log("Wi-Fi Direct removeGroup result=" + p2pReason(reason) + " (" + reason + ")");
            }
        });
    }

    private void resetP2pState() {
        p2pConnected = false;
        p2pConnectIssued = false;
        p2pDiscoveryStarted = false;
        p2pDiscoveryAttempt = 0;
        p2pNetwork = null;
        status("BLE: " + (bleReady ? "ready" : "disconnected") + " | P2P: disconnected");
    }

    private void openWifiDirectSettings() {
        try {
            startActivity(new Intent(Settings.ACTION_WIFI_SETTINGS));
        } catch (Exception e) {
            startActivity(new Intent(Settings.ACTION_WIRELESS_SETTINGS));
        }
    }

    private void copyLog() {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (clipboard == null) return;
        clipboard.setPrimaryClip(ClipData.newPlainText("CY01 Stream Lab log", logView.getText()));
        log("Log copied to clipboard");
    }

    private void closeGatt() {
        if (gatt == null) return;
        try { gatt.disconnect(); } catch (Exception ignored) {}
        try { gatt.close(); } catch (Exception ignored) {}
        gatt = null;
        writeChar = null;
        notifyChar = null;
    }

    private void status(String text) {
        runOnUiThread(() -> status.setText(text));
    }

    private void log(String text) {
        String time = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        runOnUiThread(() -> logView.append(time + "  " + text + "\n"));
    }

    private String hex(byte[] data) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < data.length; i++) {
            if (i > 0) sb.append('-');
            sb.append(String.format(Locale.US, "%02X", data[i] & 0xFF));
        }
        return sb.toString();
    }

    @Override
    protected void onDestroy() {
        if (autoStopRunnable != null) main.removeCallbacks(autoStopRunnable);
        try { if (p2pReceiver != null) unregisterReceiver(p2pReceiver); } catch (Exception ignored) {}
        closeGatt();
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
