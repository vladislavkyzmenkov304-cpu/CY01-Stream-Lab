# CY01 Stream Lab

Android research client for the CY01 / HeyCyan smart-glasses family.

This repository contains only the CY01/HeyCyan lab extracted from the private AtlasAI workspace. It does not include unrelated AtlasAI source.

## Current scope

- BLE connection to CY01 using the HeyCyan GATT service.
- Battery and capability queries.
- Source-derived preview P2P start/stop commands.
- Wi-Fi Direct discovery and connection.
- P2P IP query.
- HTTP media-server classification.
- RTSP probes on candidate ports/paths.
- Eyevue-inspired local HTTP trigger experiment.
- Automatic safety stop for preview/P2P sessions.
- Copyable diagnostic log.

## Physical hardware observations

The physical CY01 test confirmed BLE control, battery/capability replies, preview-start ACK and preview-stop ACK. The first app version also exposed an Android Wi-Fi Direct timing problem: discovery was attempted before the glasses had returned the preview-start ACK. The current code waits for the ACK and retries Android `BUSY` responses.

## Install-tested APK build

Because one TECNO/Android install rejected a later debug artifact with the generic `App not installed` message, CI now creates an isolated install-test package with application id `com.vk.cy01streamlab2`. Before upload, the generated APK is checked with `apksigner`, inspected with `aapt2`, ZIP-tested, then actually installed through Android PackageManager on an API 35 emulator. The artifact is published only if that install smoke test succeeds.

## Safety

The app does not flash firmware, issue factory-reset commands, or send OTA commands. Preview mode has a bounded automatic stop path.
