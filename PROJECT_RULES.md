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
