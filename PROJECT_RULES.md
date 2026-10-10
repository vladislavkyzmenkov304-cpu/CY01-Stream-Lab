# CY01 Stream Lab — project rules

## Commercial boundary
- Treat every client APK as inspectable/reversible. Do not rely on APK obfuscation or repository privacy as the sole protection for commercial logic.
- Never commit production secrets, private keys, subscription credentials, signing secrets, service tokens, or production-only configuration.
- Keep future subscription entitlement/authorization and commercially sensitive server-side logic behind a backend boundary where practical.
- Public/shared research may document interoperability facts, but proprietary product logic must be reviewed before publication.

## Regression rules
- Preserve the last physically confirmed working video path unless a change is required by evidence.
- A build passing CI is not proof of physical CY01 behavior; physical-glasses tests remain a release gate for transport/audio changes.
- Video quality is judged by perceived smoothness as well as average FPS. Track stalls/jitter/frame-delivery gaps and decoder recoveries; do not accept ~30 FPS alone as proof of smooth playback.
- Camera/microphone transition work must not silently regress BLE -> preview -> P2P -> RTSP /ch0 -> H.264 decode.

## Working process
- Work in the current authorized branch; do not create new branches without explicit approval.
- If an engineering blocker can be safely resolved from repository evidence, fix it and continue instead of waiting.
- Ask the owner when a decision, external credential, destructive action, or physical-device action is actually required.
- Keep diagnostic reports truthful: preserve successful-session metrics separately from later recovery-attempt failures.


## Product target: AI-assisted uninterrupted LIVE
- The end product is not an AI assistant that stops LIVE to take a photo. AI interaction must be designed as a parallel path over an uninterrupted live video session.
- While LIVE continues to viewers, a glasses button or voice command may invoke the assistant. The app should reuse the current stream and select one or more recent frames from a rolling buffer for visual context, rather than interrupting the camera merely to capture a still image.
- The user's spoken question plus selected live-frame context may be sent to an AI service/model. AI processing must not block, restart, or noticeably interrupt the broadcast video path.
- AI voice responses should support at least two product modes: private playback to the wearer and broadcast playback mixed into the LIVE audio so viewers can hear the assistant as a virtual co-host.
- Architecture should allow context-dependent sampling: a recent high-quality frame for object/text questions, or a short sequence of recent frames when motion/action context is required. Continuous analysis of every video frame is not a requirement.
- Target hands-free interactions include questions about visible objects, signs/text, places, how to use or repair something in view, contextual advice, and real-time translation.
- Future controls should support invoking LIVE/AI from glasses buttons and/or voice without taking out the phone.
- This target makes uninterrupted simultaneous video + usable voice/audio a product requirement. The current diagnostic camera/mic-exclusive switching is temporary research behavior and must not become the final commercial UX.
- Preserve this product target when changing transport, audio, buffering, AI, streaming, or subscription architecture.
