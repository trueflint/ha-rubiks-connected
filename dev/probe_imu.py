#!/usr/bin/env python3
"""
Investigate IMU / orientation data from the Rubik's Connected cube.

Phase 1 — passive listen (20 s): connect, send HANDSHAKE, print every raw
          packet while you tilt / shake / rotate the cube freely.
Phase 2 — active probe: send candidate commands one by one and log responses.

Usage:
    python3 dev/probe_imu.py <ADDRESS>
"""

import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

# Commands to probe in Phase 2 (known-safe unexplored candidates near IMU)
CANDIDATES = [
    0x30,                                           # before battery (0x32)
    0x37, 0x38,                                     # between calibrate and time
    0x3a, 0x3b, 0x3c, 0x3d, 0x3e, 0x3f,            # after time (0x39)
    0x40,                                           # bare (subtype variants are state)
    0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47,
    0x48, 0x49, 0x4a, 0x4b, 0x4c, 0x4d, 0x4f,      # neighbours of IMU_PASS (0x4e)
    0x56, 0x57, 0x58, 0x59, 0x5a, 0x5b, 0x5c,      # after HANDSHAKE (0x55)
]

# Skip known-dangerous commands just in case they slipped in
SKIP = {0x31, 0x34, 0x36, 0x51, 0x52, 0x53, 0x54, 0x78}


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _describe(data: bytes) -> str:
    try:
        text = data.decode("ascii").strip()
        return f"ASCII: {text!r}"
    except Exception:
        pass
    if len(data) >= 3 and data[0] == 0x2a:
        return f"type=0x{data[1]:02x} sub=0x{data[2]:02x} len={len(data)}"
    return f"raw ({len(data)} bytes)"


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target = sys.argv[1]
    print(f"Scanning for '{target}' ...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, _: (d.name and target.lower() in d.name.lower())
            or d.address.lower() == target.lower(),
        timeout=15,
    )
    if not device:
        print("Device not found — wake the cube and try again.")
        sys.exit(1)
    print(f"Found: {device.name} ({device.address})")

    responses: list[bytes] = []
    last_cmd: list[int] = [None]

    def on_notify(_, data: bytearray) -> None:
        b = bytes(data)
        responses.append(b)
        cmd_label = f"  [after 0x{last_cmd[0]:02x}]" if last_cmd[0] is not None else "  [unsolicited]"
        print(f"  [{_ts()}]{cmd_label}  {b.hex(' ')}  ({_describe(b)})")

    try:
        async with BleakClient(device) as client:
            await client.start_notify(NOTIFY_UUID, on_notify)
            await client.write_gatt_char(WRITE_UUID, bytes([0x55]), response=False)
            await asyncio.sleep(0.5)
            responses.clear()

            # ── Phase 1: passive listen ────────────────────────────────────────
            print("\n── Phase 1: passive listen (20 s) ──────────────────────────")
            print("Tilt, shake, and rotate the cube in all directions now!")
            last_cmd[0] = None
            await asyncio.sleep(20.0)
            passive_count = len(responses)
            print(f"\n{passive_count} unsolicited packet(s) received during passive phase.")

            # ── Phase 2: active probe ──────────────────────────────────────────
            print("\n── Phase 2: active probe ────────────────────────────────────")
            results: dict[str, list[str]] = {}
            for cmd in CANDIDATES:
                if cmd in SKIP:
                    continue
                key = f"0x{cmd:02x}"
                responses.clear()
                last_cmd[0] = cmd
                await client.write_gatt_char(WRITE_UUID, bytes([cmd]), response=False)
                await asyncio.sleep(0.8)
                if responses:
                    results[key] = [r.hex(" ") for r in responses]
                else:
                    results[key] = []

            print("\n── Summary ──────────────────────────────────────────────────")
            for key, resps in results.items():
                if resps:
                    for r in resps:
                        print(f"  {key}  →  {r}")
                else:
                    print(f"  {key}  →  (no response)")

    except TimeoutError:
        print("Connection timed out — wake the cube and try again.")
        sys.exit(1)
    except Exception as e:
        print(f"Connection error: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
