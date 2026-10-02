# Physical test — CY01 + TECNO, 2026-09-08

## v0.1 confirmed on physical hardware

- BLE scan found `CY 01_BAB8` / `9F:BB:9F:2E:BA:B8`.
- GATT service/notify/write setup succeeded.
- Battery query succeeded: 100% in this run.
- Capability query again reported `supportLiveReview=false`.
- Preview command `[02 01 14 01]` was accepted and produced a structured `0x41` reply.
- Stop command `[02 01 15 01]` produced its own `0x41` reply.

## v0.1 timing defect found

The app scheduled Android Wi-Fi Direct discovery at a fixed 900 ms after sending preview start. On the physical log:

- preview TX: 21:17:54.109
- Android P2P discovery failure `reason=2` (BUSY): 21:17:55.080
- preview-start ACK from glasses: 21:17:55.582

So discovery began about 0.5 s before the glasses returned their preview-start ACK.

## v0.2 change

- Wait for the preview-start ACK before beginning P2P discovery.
- Add bounded retry for Android `WifiP2pManager.BUSY` responses.
- Parse the preview-start ACK credential-shaped fields for diagnostics.
- Keep the existing safety timeout/stop path.

## APK installation issue and v0.2.2 isolation build

The physical phone repeatedly rejected a later debug APK with the generic Android message `App not installed`, even after the previous CY01 Stream Lab install had been removed. To isolate package-manager/signature state from the glasses code, CI now produces an install-test variant with a completely new package identity:

- package: `com.vk.cy01streamlab2`
- versionCode: 202
- versionName: `0.2.2-debug`
- minSdk: 26
- targetSdk: 35

GitHub Actions verifies the APK with Android build-tools before publishing it. `apksigner verify` passes using APK Signature Scheme v2, and the ZIP structure is clean.

Most importantly, the exact generated APK is installed through Android's package manager on a clean API 35 emulator as part of CI:

```text
adb install -r app/build/outputs/apk/debug/app-debug.apk
Performing Streamed Install
Success
adb shell pm path com.vk.cy01streamlab2
package:/data/app/.../com.vk.cy01streamlab2-.../base.apk
```

Therefore this artifact has now passed an actual Android PackageManager install test before being sent to the physical TECNO device.
