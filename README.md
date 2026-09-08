# CY01 Stream Lab

Public Android diagnostic app for CY01 / HeyCyan live-preview research.

## Purpose

Automate the manual nRF Connect + Wi-Fi Direct + VLC workflow without firmware flashing or blind command brute force.

## Current lab flow

1. Scan and connect to `CY 01...` over BLE.
2. Subscribe to HeyCyan notify characteristic `de5bf729-d711-4e47-af26-65e3012a5dc7`.
3. Send known-source preview command `[02 01 14 01]` through opcode `0x41`.
4. Discover and connect to the CY01 Wi-Fi Direct peer.
5. Query the glasses P2P IP with `[02 03]`.
6. Bind HTTP/RTSP sockets explicitly to the Android P2P Wi-Fi `Network`.
7. Classify the ordinary HeyCyan HTTP server with `/files/media.config`.
8. Probe RTSP ports `554` and `8554` with known HeyCyan and Eyevue-derived candidate paths.
9. Try the Eyevue-inspired local HTTP trigger `/?custom=1&cmd=3001&par=1` as a GET-only experiment, then probe RTSP again.
10. Stop preview with `[02 01 15 01]` and remove the P2P group automatically after 60 seconds.

## Safety boundaries

This app does **not** send OTA, factory-reset, restart, or unknown brute-force commands. It does not flash either chip. The Eyevue-inspired HTTP request is a local GET only and is logged as experimental.

## Known lab-unit data

- Hardware: `AM01CY_V2.2`
- Glasses firmware: `2.2.0.10_260411`
- Wi-Fi hardware: `WIFIAM01CY_V2.2`
- Wi-Fi firmware: `1.00.27_2512271030`
- Observed P2P IP: `192.168.49.96`
- Capability response: `supportLiveReview=false`
- Known-source preview command still raises Wi-Fi Direct on this unit.

## Research basis

- HeyCyan BLE large-data framing: `BC opcode lenLE crc16LE payload`.
- `0x41` preview source commands: P2P `[02 01 14 01]`, AP `[02 01 14 02]`, stop `[02 01 15 01]`.
- V821 static firmware research: `ai_glass_livestream`, aglink mode 8, live555, candidate RTSP port 554 and session name `testH264VideoStreamer`.
- Eyevue reference implementation: BLE live command -> Wi-Fi join -> optional HTTP control GET -> RTSP playback. Eyevue is a different protocol; only the sequencing idea is reused here.

## Development branch

`lab/cy01-stream-apk`

The project was isolated from the private `AtlasAI` repository before publication; no unrelated AtlasAI source is copied here.
