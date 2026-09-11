# RTSP live555 session-name correction

## Why v0.4 returned 404

The physical v0.4 test reached the CY01 RTSP server on `192.168.49.96:8554`, but `DESCRIBE` returned `404 Stream Not Found` for the previous candidate paths, including `/testH264VideoStreamer`.

The upstream LIVE555 source provides a strong explanation. In `testProgs/testH264VideoStreamer.cpp`, the server is created on port `8554`, while the `ServerMediaSession` stream name is **`testStream`**. The text `Session streamed by "testH264VideoStreamer"` is the human-readable session description, not the RTSP mount name.

Therefore the source-level candidate corresponding to the stock LIVE555 test program is:

`rtsp://192.168.49.96:8554/testStream`

This is a source-derived hypothesis until it is verified on the physical CY01.

## v0.5

v0.5 probes `/testStream` first with `DESCRIBE`, logs the SDP fields needed to classify the media/transport, and then attempts Media3 playback. It tries interleaved RTP-over-RTSP/TCP first and then a UDP-first classification retry if needed.

The app still treats `PLAYER READY` as insufficient proof. Live video is confirmed only after Android reports `EVENT_RENDERED_FIRST_FRAME`.

If the returned SDP indicates RTP multicast, that is logged explicitly. AndroidX Media3 does not support RTP multicast, so such a result would trigger a separate raw multicast RTP/H.264 receiver implementation rather than being misclassified as a camera failure.
