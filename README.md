# CY01 Stream Lab

Android research client for the CY01 / HeyCyan smart-glasses family.

This repository contains only the CY01/HeyCyan lab extracted from the private AtlasAI workspace. It does not include unrelated AtlasAI source.

## Current scope

- BLE connection to CY01 using the HeyCyan GATT service.
- Battery and capability queries.
- Source-derived preview P2P start/stop commands.
- Wi-Fi Direct discovery and connection after the preview ACK.
- P2P IP query.
- HTTP/RTSP service classification.
- RTSP `DESCRIBE` probing on candidate paths.
- Media3 local RTSP playback with RTP-over-RTSP/TCP forced.
- Automatic safety stop for preview/P2P sessions.
- Copyable diagnostic log.

## Physical hardware status

Physical CY01 testing has now confirmed the complete control/network path from the Android app to the glasses:

`BLE preview command -> preview ACK -> Wi-Fi Direct -> P2P group -> BLE IP query -> local socket route`

During preview mode the tested device is reachable at `192.168.49.96`. TCP/80 and TCP/554 refuse connections, while TCP/8554 accepts connections and answers RTSP `OPTIONS` with `RTSP/1.0 200 OK`.

This is direct hardware evidence that the CY01 exposes an RTSP service on port 8554 when preview mode is activated. The next proof boundary is actual media delivery: `DESCRIBE -> SDP -> SETUP -> PLAY -> RTP -> decoded video frame`.

See `docs/TEST_2026-09-08_V03_RTSP.md` for the physical v0.3 result.

## v0.4 field-test build

v0.4 adds a dedicated RTSP player using AndroidX Media3. It probes the current candidate paths with RTSP `DESCRIBE`, looks for SDP video metadata, then starts Media3 with RTP-over-RTSP/TCP forced. The preview safety window is extended to three minutes for the playback test.

The CI build is verified with `apksigner`, ZIP integrity checks, and an Android 16 emulator install/launcher smoke test before the APK artifact is uploaded.

## Safety

The app does not flash firmware, issue factory-reset commands, or send OTA commands. Preview mode has a bounded automatic stop path. Unique physical-device identifiers and preview passwords are not committed to this public repository.
