from pathlib import Path
import runpy

# v1.8: harden repeated BLE/P2P sessions observed on physical CY01.
runpy.run_path("tools/prepare_v17.py", run_name="__main__")

def rr(t,o,n,l):
    if o not in t: raise SystemExit(l+" not found")
    return t.replace(o,n,1)

g=Path("app/build.gradle"); s=g.read_text()
s=rr(s,"applicationId 'com.vk.cy01streamlab17'","applicationId 'com.vk.cy01streamlab18'","id")
s=rr(s,"versionCode 1700","versionCode 1800","code")
s=rr(s,"versionName '1.7.0'","versionName '1.8.0'","name"); g.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/MainActivityV03.java"); s=p.read_text()
s=s.replace("CY01 Live v1.7 started","CY01 Live v1.8 started").replace("CY01 Live v1.7","CY01 Live v1.8").replace("CY01StreamLab-OneTap/1.7","CY01StreamLab-OneTap/1.8")
s=s.replace("v1.5: no explicit Android Network binding","v1.8: no explicit Android Network binding").replace("v1.5 will NOT bind sockets","v1.8 will NOT bind sockets")

field="""    private boolean scanning;
"""
field_new=field+"""    private int bleRecoveryAttempt;
    private BluetoothDevice lastBleDevice;
"""
s=rr(s,field,field_new,"ble recovery fields")

found='''            log("Found " + name + " / " + device.getAddress());
            status("BLE: connecting | P2P: " + (p2pConnected ? "connected" : "disconnected"));'''
found_new='''            log("Found " + name + " / " + device.getAddress());
            lastBleDevice = device;
            status("BLE: connecting | P2P: " + (p2pConnected ? "connected" : "disconnected"));'''
s=rr(s,found,found_new,"remember device")

desc="""            bleReady = statusCode == BluetoothGatt.GATT_SUCCESS;
            log("BLE command channel ready=" + bleReady + " status=" + statusCode);
            status("BLE: " + (bleReady ? "ready" : "error") + " | P2P: " + (p2pConnected ? "connected" : "disconnected"));
"""
desc_new="""            bleReady = statusCode == BluetoothGatt.GATT_SUCCESS;
            log("BLE command channel ready=" + bleReady + " status=" + statusCode);
            status("BLE: " + (bleReady ? "ready" : "error") + " | P2P: " + (p2pConnected ? "connected" : "disconnected"));
            if (bleReady) {
                bleRecoveryAttempt = 0;
            } else if (bleRecoveryAttempt < 2 && lastBleDevice != null) {
                final int attempt = ++bleRecoveryAttempt;
                log("BLE CCCD recovery scheduled after status=" + statusCode + ", attempt=" + attempt + "/2");
                main.postDelayed(() -> reconnectLastBleDevice(attempt), 900L);
            }
"""
s=rr(s,desc,desc_new,"descriptor recovery")

marker="""    private boolean looksLikeCy01(String name) {
"""
method="""    private void reconnectLastBleDevice(int attempt) {
        BluetoothDevice device = lastBleDevice;
        if (device == null || bleReady) return;
        log("BLE recovery: closing stale GATT and reconnecting, attempt=" + attempt);
        closeGatt();
        rx.reset();
        main.postDelayed(() -> {
            if (bleReady || device == null) return;
            try {
                gatt = device.connectGatt(MainActivityV03.this, false, gattCallback, BluetoothDevice.TRANSPORT_LE);
            } catch (Exception e) {
                log("BLE recovery connect failed: " + errorText(e));
            }
        }, 450L);
    }

"""
s=rr(s,marker,method+marker,"ble reconnect method")

retry="""        cancelP2pDiscoveryWatchdog("connect watchdog retry");
        main.postDelayed(() -> beginP2pDiscovery("connect watchdog retry"), 900);
"""
retry_new="""        cancelP2pDiscoveryWatchdog("connect watchdog retry");
        if (bleReady) {
            log("P2P recovery: re-arming CY01 preview before rediscovery");
            sendFrame(0x41, new byte[]{0x02, 0x01, 0x14, 0x01});
        }
        main.postDelayed(() -> beginP2pDiscovery("connect watchdog retry"), 1400);
"""
s=rr(s,retry,retry_new,"preview rearm")

ipblock="""            if (p2pConnected && !candidateIp.startsWith("192.168.49.")) {
                log("Ignoring transient/non-P2P IP candidate while group is 192.168.49.x");
                if (ipQueryAttempt < 4) main.postDelayed(this::requestGlassesIp, 700);
                return;
            }

            glassesIp = candidateIp;
"""
ipnew="""            if (p2pConnected && !candidateIp.startsWith("192.168.49.")) {
                log("BLE IP candidate is outside current P2P subnet; retaining as probe candidate=" + candidateIp);
                final String candidate = candidateIp;
                io.execute(() -> {
                    RtspResult result = probeRtsp(candidate, 8554, "/ch0");
                    if (result.tcpOpen) {
                        glassesIp = candidate;
                        log("Alternate CY01 IP accepted after RTSP probe: " + candidate);
                        main.postDelayed(this::runBaseProbeSuite, 100L);
                    } else if (ipQueryAttempt < 4) {
                        main.postDelayed(this::requestGlassesIp, 700L);
                    }
                });
                return;
            }

            glassesIp = candidateIp;
"""
s=rr(s,ipblock,ipnew,"candidate probe")

fallback="""            glassesIp = "192.168.49.96";
            log("No accepted BLE P2P IP after retries; using confirmed CY01 fallback " + glassesIp);
            main.postDelayed(this::runBaseProbeSuite, 500);
"""
fallback_new="""            log("No accepted BLE P2P IP after retries; probing likely CY01 addresses instead of trusting fixed .96");
            discoverCy01RtspPeer();
"""
s=rr(s,fallback,fallback_new,"fallback discovery")

marker2="""    private void logP2pRoutes() {
"""
method2="""    private void discoverCy01RtspPeer() {
        io.execute(() -> {
            String[] likely = {"192.168.49.96", "192.168.49.2", "192.168.49.3", "192.168.49.4"};
            for (String ip : likely) {
                if (!p2pConnected) return;
                RtspResult result = probeRtsp(ip, 8554, "/ch0");
                log("CY01 peer probe " + ip + ":8554 tcpOpen=" + result.tcpOpen
                        + (result.firstLine == null ? "" : " " + result.firstLine));
                if (result.tcpOpen) {
                    glassesIp = ip;
                    log("CY01 RTSP peer selected dynamically = " + ip);
                    main.postDelayed(this::runBaseProbeSuite, 100L);
                    return;
                }
            }
            log("CY01 RTSP peer not found in bounded candidate set; re-arming preview once");
            if (bleReady) sendFrame(0x41, new byte[]{0x02, 0x01, 0x14, 0x01});
            main.postDelayed(this::requestConnectionInfo, 1200L);
        });
    }

"""
s=rr(s,marker2,method2+marker2,"dynamic peer method")
p.write_text(s)

p=Path("app/src/main/java/com/vk/cy01streamlab/RawRtspH264Activity.java"); r=p.read_text()
r=r.replace("CY01 LIVE v1.7 started","CY01 LIVE v1.8 started").replace("CY01 LIVE VIDEO v1.7","CY01 LIVE VIDEO v1.8").replace("CY01StreamLab-Raw/1.7","CY01StreamLab-Raw/1.8").replace("CY01 LIVE v1.7 compact report","CY01 LIVE v1.8 compact report").replace("MIC TEST v1.7:","MIC TEST v1.8:")
p.write_text(r)
print("v1.8 BLE/P2P recovery and dynamic peer preparation complete")
