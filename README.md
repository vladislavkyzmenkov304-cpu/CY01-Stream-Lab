# CY01 Stream Lab

Android research client for the CY01 / HeyCyan smart-glasses family.

This repository contains only the CY01/HeyCyan lab extracted from the private AtlasAI workspace. It does not include unrelated AtlasAI source.

## Current scope

- BLE connection to CY01 using the HeyCyan GATT service.
- Battery and capability queries.
- Source-derived preview P2P start/stop commands.
- Wi-Fi Direct discovery and connection after the preview ACK.
- P2P IP query and direct local routing.
- RTSP service discovery on the glasses.
- Confirmed CY01 media session at `rtsp://192.168.49.96:8554/ch0`.
- Custom RTSP client for `DESCRIBE -> SETUP -> PLAY`.
- RTP-over-RTSP/TCP H.264 depacketization, including single NAL, STAP-A and FU-A.
- In-band SPS/PPS acquisition and Android `MediaCodec` AVC decode.
- Confirmed live video rendering from the physical CY01 camera.
- v0.9 one-tap orchestration from BLE discovery to the live-video decoder.
- Automatic safety stop and copyable diagnostic logs.

## Physical hardware status

Physical testing has now confirmed the complete local live-video path:

`CY01 camera -> BLE preview control -> Wi-Fi Direct -> RTSP :8554/ch0 -> RTP/H.264 -> in-band SPS/PPS -> Android MediaCodec -> rendered live frame`

During preview mode the tested device is reachable at `192.168.49.96`. TCP/80 and TCP/554 refuse connections. TCP/8554 is the active RTSP service.

The confirmed RTSP media session is:

`rtsp://192.168.49.96:8554/ch0`

Its SDP advertises H.264 video on `track1` and MPEG4-GENERIC/AAC audio on `track2`. The H.264 SDP omits `a=fmtp` / `sprop-parameter-sets`, which makes AndroidX Media3 reject the stream before playback. The CY01 sends SPS and PPS in-band, so the custom raw RTP/H.264 path waits for those NAL units and configures `MediaCodec` directly.

Field logs confirmed all of the following on real hardware:

- `DESCRIBE /ch0 -> RTSP/1.0 200 OK`
- `SETUP track1 TCP interleaved -> RTSP/1.0 200 OK`
- `PLAY /ch0 -> RTSP/1.0 200 OK`
- first RTP video packet received
- SPS and PPS received in-band
- IDR keyframe received
- first decoded video output buffer released to the Surface
- first video frame rendered on the Android device

The current development boundary is no longer local camera access. The next major stage is turning the Android phone into a publisher/relay for internet streaming (for example RTMP, SRT or WebRTC) while preserving the proven CY01 local ingest path.

## v0.9 one-tap build

v0.9 automates the proven path behind a single `LIVE — ONE TAP` action:

1. BLE scan/connect.
2. Preview command.
3. Wi-Fi Direct group formation.
4. CY01 P2P IP acquisition.
5. `DESCRIBE /ch0` readiness check.
6. If `/ch0` is not ready, one safe re-send of the already verified preview command `[02 01 14 01]`.
7. Automatic launch of the raw `/ch0` RTP/H.264 decoder.
8. Automatic decoder start as soon as the video Surface is ready.

Manual lab controls remain available for diagnostics.

CI verifies source preparation, APK build/signature/integrity, and Android 16 installation plus launcher smoke test before uploading the artifact.

## Safety

The app does not flash firmware, issue factory-reset/restart commands, perform OTA, or brute-force BLE commands. Preview/P2P sessions retain a bounded safety timeout. Unique physical-device identifiers and preview passwords are not committed to this public repository.
