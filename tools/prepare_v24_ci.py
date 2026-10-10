import runpy
from pathlib import Path

runpy.run_path("tools/prepare_v19.py", run_name="__main__")

src_path = Path("tools/prepare_v24_impl.py")
src = src_path.read_text()

old = '''old_73 = """        if (opcode == 0x73) {
            if (payload.length >= 2 && (payload[0] & 0xFF) == 0x03 && (payload[1] & 0xFF) == 0x01) {
                bleMicStartedEvent = true;
                log("BLE MICROPHONE START EVENT confirmed: cmd 0x73 payload=03-01");
            }
            return;
        }
"""'''

new = '''old_73 = """        if (opcode == 0x73) {
            log("BLE DATA REPORTING 0x73 payload=" + hex(payload)
                    + " micProbeRunning=" + bleMicProbeRunning);
            if (payload.length >= 2 && (payload[0] & 0xFF) == 0x03 && (payload[1] & 0xFF) == 0x01) {
                bleMicStartedEvent = true;
                log("BLE MICROPHONE START EVENT confirmed: cmd 0x73 payload=03-01");
            }
            return;
        }
"""'''

if old not in src:
    raise SystemExit("v2.4 bootstrap 0x73 source patch target not found")

src = src.replace(old, new, 1)
exec(compile(src, str(src_path), "exec"), {"__name__": "__main__", "__file__": str(src_path)})
