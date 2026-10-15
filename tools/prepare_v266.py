from pathlib import Path

def edit(s,a,b):
    assert a in s, a[:100]
    return s.replace(a,b,1)

root=Path('app/src/main/java/com/vk/cy01streamlab')
p=root/'RawRtspH264Activity.java'
r=p.read_text()
r=edit(r,'    private void startRawTest() {','''    private int emptyTransportFailures, routeRebuilds;
    private boolean routeRecoveryActive;

    private void retryTransportOrRoute() {
        if (rtpPacketCount > 0) emptyTransportFailures=0;
        else emptyTransportFailures++;
        if (emptyTransportFailures < 2) { startRawSession(); return; }
        beginRouteRecovery();
    }

    private void beginRouteRecovery() {
        if (!liveRequested || running || !surfaceReady || isFinishing() || routeRecoveryActive) return;
        routeRecoveryActive=true;
        final int epoch=stopEpoch;
        final long deadline=android.os.SystemClock.elapsedRealtime()+45000L;
        routeRebuilds++;
        log("LIVE ROUTE recovery #"+routeRebuilds+": rebuilding P2P and obtaining fresh IP; Bluetooth capture retained");
        status("Восстанавливается соединение с очками: Wi-Fi Direct → новый IP → видео");
        boolean accepted=MainActivityV03.requestLiveRouteRecovery();
        if (!accepted) log("LIVE ROUTE owner unavailable; recovery will retry");
        pollLiveRoute(epoch,accepted ? deadline : android.os.SystemClock.elapsedRealtime());
    }

    private void pollLiveRoute(int epoch,long deadline) {
        if (!liveRequested || epoch!=stopEpoch || running || !surfaceReady || isFinishing()) return;
        if (MainActivityV03.consumeCameraRecoveryReady()) {
            String ip=MainActivityV03.cameraRecoveryIp;
            if (ip!=null && !ip.trim().isEmpty()) {
                rtspHost=ip.trim(); baseUri="rtsp://"+rtspHost+":"+PORT+"/ch0";
                routeRecoveryActive=false; emptyTransportFailures=0;
                log("LIVE ROUTE ready: fresh /ch0 at "+rtspHost);
                startRawSession();
                return;
            }
        }
        if (android.os.SystemClock.elapsedRealtime()>=deadline) {
            MainActivityV03.cancelLiveRouteRecovery();
            routeRecoveryActive=false;
            log("LIVE ROUTE recovery timed out; retrying full route in 10 seconds");
            status("Очки пока недоступны. Повтор восстановления через 10 с.");
            main.postDelayed(() -> {
                if (liveRequested && epoch==stopEpoch) beginRouteRecovery();
            },10000L);
            return;
        }
        main.postDelayed(() -> pollLiveRoute(epoch,deadline),500L);
    }

    private void startRawTest() {''')
r=edit(r,'        if (running) return;\n        transportRetries = 0;','        if (running || routeRecoveryActive) return;\n        emptyTransportFailures=routeRebuilds=0;\n        transportRetries = 0;')
r=edit(r,'                        startRawSession();\n                    }\n                },delay);','                        retryTransportOrRoute();\n                    }\n                },delay);')
r=edit(r,'        liveRequested=false;','        liveRequested=false;\n        routeRecoveryActive=false;\n        MainActivityV03.cancelLiveRouteRecovery();')
r=edit(r,'        summary += "transportRetries="', '        summary += "routeRebuilds="+routeRebuilds+" routeRecoveryActive="+routeRecoveryActive+" emptyTransportFailures="+emptyTransportFailures+"\\n";\n        summary += "transportRetries="')
p.write_text(r.replace('2.6.5','2.6.6'))

p=root/'MainActivityV03.java'; s=p.read_text()
s=edit(s,'    public static boolean requestCameraRecoveryAfterMic() {','''    private boolean liveRouteOwned;
    private int routeGeneration;

    public static boolean requestLiveRouteRecovery() {
        MainActivityV03 owner=activeInstance;
        if (owner==null || owner.isFinishing()) return false;
        owner.liveRouteOwned=true;
        owner.routeGeneration++;
        owner.recoverCameraAfterMic();
        return true;
    }

    public static void cancelLiveRouteRecovery() {
        MainActivityV03 owner=activeInstance;
        if(owner==null || !owner.liveRouteOwned) return;
        owner.routeGeneration++;
        cameraRecoveryRequested=false; cameraRecoveryReady=false; cameraRecoveryIp=null;
        owner.oneTapLiveRequested=false; owner.oneTapLaunchInProgress=false;
        if(owner.p2pConnectWatchdog!=null) owner.main.removeCallbacks(owner.p2pConnectWatchdog);
        owner.cancelP2pDiscoveryWatchdog("LIVE route cancelled");
    }

    private boolean routeCancelled() {
        return liveRouteOwned && (!RawRtspH264Activity.liveRequested || !cameraRecoveryRequested);
    }

    public static boolean requestCameraRecoveryAfterMic() {''')
s=edit(s,'''        if (!bleReady) {
            log("MIC->CAMERA recovery blocked: BLE channel is not ready");
            return;
        }
        cameraRecoveryRequested = true;''','''        final int generation=routeGeneration;
        cameraRecoveryRequested = true;''')
s=edit(s,'        Runnable restart = () -> {\n            resetP2pState();','        Runnable restart = () -> {\n            if(liveRouteOwned && (generation!=routeGeneration || routeCancelled())) return;\n            resetP2pState();')
s=edit(s,'''                cameraRecoveryRequested = false;
                log("MIC->CAMERA recovery aborted: BLE dropped before preview re-arm");
                return;''','''                log("LIVE ROUTE: reconnecting BLE before preview re-arm");
                oneTapScanAttempt=0;
                scanAndConnect();
                return;''')
s=edit(s,'    private void startOneTapLive() {','    private void startOneTapLive() {\n        liveRouteOwned=false; routeGeneration++;')
s=edit(s,'        final String ip = glassesIp != null ? glassesIp : "192.168.49.96";','        final int generation=routeGeneration;\n        final String ip = glassesIp != null ? glassesIp : "192.168.49.96";')
s=edit(s,'main.post(() -> launchRawDecoderAuto("/ch0 already ready; no re-arm needed"));','''main.post(() -> {
                    if(generation!=routeGeneration || (liveRouteOwned && routeCancelled()) || !ip.equals(glassesIp)) return;
                    launchRawDecoderAuto("/ch0 already ready; no re-arm needed");
                });''')
s=edit(s,'            if (!oneTapRearmSent && bleReady) {','            if(generation!=routeGeneration || (liveRouteOwned && routeCancelled())) return;\n            if (!oneTapRearmSent && bleReady) {')
s=edit(s,'                    log("ONE-TAP: /ch0 not ready;', '                    if(generation!=routeGeneration || (liveRouteOwned && routeCancelled())) return;\n                    log("ONE-TAP: /ch0 not ready;')
for method in ['startLiveTest()', 'beginP2pDiscovery(String reason)', 'retryP2pAfterStall()', 'requestGlassesIp()']:
    token='    private void '+method+' {'
    s=edit(s,token,token+'\n        if(routeCancelled()) return;')
s=edit(s,'    private void launchRawDecoderAuto(String reason) {','    private void launchRawDecoderAuto(String reason) {\n        if(routeCancelled()) return;')
s=edit(s,'    private void startLiveBatteryMonitoring() {','    private void startLiveBatteryMonitoring() {\n        if(liveRouteOwned && liveBatteryPollRunnable!=null) return;')
s=edit(s,'if (!p2pConnected && !oneTapLiveRequested) return;', 'if (!p2pConnected && !oneTapLiveRequested && !RawRtspH264Activity.liveRequested) return;')
s=s.replace('MIC->CAMERA recovery','CAMERA/P2P recovery')
p.write_text(s.replace('2.6.5','2.6.6'))
p=Path('app/build.gradle');p.write_text(p.read_text().replace('versionCode 2605','versionCode 2606').replace('2.6.5','2.6.6'))

# Exercise the generated recovery methods with a deterministic clock and Handler.
import shutil, subprocess, tempfile
if shutil.which('javac'):
    actual=(root/'RawRtspH264Activity.java').read_text()
    methods=actual[actual.index('    private int emptyTransportFailures'):actual.index('    private void startRawTest()')]
    methods=methods.replace('android.os.SystemClock.elapsedRealtime()', 'Clock.now')
    harness='''
public class RouteRecoveryCheck {
 boolean liveRequested=true,running=false,surfaceReady=true,finishing=false;
 int stopEpoch=7,starts; long rtpPacketCount; String rtspHost="old",baseUri; static final int PORT=8554;
 static class Clock {static long now;}
 static class Handler {Runnable task; void postDelayed(Runnable r,long delay){task=r;} void run(){Runnable r=task;task=null;r.run();}}
 Handler main=new Handler();
 static class MainActivityV03 {
  static boolean ready,accept=true; static String cameraRecoveryIp="fresh"; static int requests,cancels;
  static boolean requestLiveRouteRecovery(){requests++;return accept;}
  static boolean consumeCameraRecoveryReady(){boolean r=ready;ready=false;return r;}
  static void cancelLiveRouteRecovery(){cancels++;ready=false;}
 }
 void log(String s){} void status(String s){} boolean isFinishing(){return finishing;}
 void startRawSession(){starts++;running=true;stopEpoch++;}
'''+methods+'''
 public static void main(String[]args){
  RouteRecoveryCheck c=new RouteRecoveryCheck();
  c.retryTransportOrRoute();if(c.starts!=1)throw new AssertionError("first TCP retry");
  c.running=false;c.retryTransportOrRoute();
  if(c.starts!=1 || !c.routeRecoveryActive || MainActivityV03.requests!=1)throw new AssertionError("full route escalation");
  MainActivityV03.ready=true;c.main.run();
  if(c.starts!=2 || !c.rtspHost.equals("fresh") || c.routeRecoveryActive)throw new AssertionError("fresh address handoff");
  c=new RouteRecoveryCheck();c.emptyTransportFailures=2;c.beginRouteRecovery();
  c.liveRequested=false;c.stopEpoch++;MainActivityV03.ready=true;c.main.run();
  if(c.starts!=0)throw new AssertionError("STOP resurrected LIVE");
  MainActivityV03.ready=false;c=new RouteRecoveryCheck();c.beginRouteRecovery();
  Clock.now=45001;c.main.run();if(c.routeRecoveryActive || MainActivityV03.cancels==0)throw new AssertionError("deadline");
  int before=MainActivityV03.requests;c.main.run();if(MainActivityV03.requests!=before+1)throw new AssertionError("route retry");
  MainActivityV03.ready=false;c=new RouteRecoveryCheck();c.emptyTransportFailures=4;c.rtpPacketCount=100;c.retryTransportOrRoute();
  if(c.starts!=1 || c.emptyTransportFailures!=0)throw new AssertionError("healthy transport resets escalation");
  System.out.println("Route recovery PASS: escalation, fresh IP, STOP, deadline, repeated recovery, healthy reset");
 }
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        f=Path(tmp)/'RouteRecoveryCheck.java';f.write_text(harness)
        subprocess.run(['javac',str(f)],check=True)
        subprocess.run(['java','-cp',tmp,'RouteRecoveryCheck'],check=True)
