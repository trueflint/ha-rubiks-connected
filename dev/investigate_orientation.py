#!/usr/bin/env python3
"""
Test whether 0x62 and 0x76 return orientation-dependent data.

Phase 1 — stability: poll 0x62 and 0x76 ten times with cube at rest.
Phase 2 — orientation: poll both every second for 60 s while you slowly
           place each of the cube's 6 faces upward and hold for ~8 s.
           If either payload changes with orientation, it's IMU/accel data.
Phase 3 — neighbours: try 0x63, 0x64, 0x65 to see if there are more axes.

Usage:
    python3 dev/investigate_orientation.py <ADDRESS>
"""

import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _decode(data: bytes) -> str:
    if len(data) >= 6 and data[0] == 0x2a and data[1] == 0x06:
        p = data[3:-3]
        if len(p) == 2:
            a = p[0] if p[0] < 128 else p[0] - 256
            b = p[1] if p[1] < 128 else p[1] - 256
            return (f"sub=0x{data[2]:02x}  raw=[{p[0]}, {p[1]}]"
                    f"  signed=[{a:+d}, {b:+d}]"
                    f"  uint16-LE={int.from_bytes(p, 'little')}"
                    f"  uint16-BE={int.from_bytes(p, 'big')}")
    try:
        return f"ASCII {data.decode('ascii').strip()!r}"
    except Exception:
        return f"raw {data.hex(' ')}"


async def poll(client, cmd: int, responses: list, wait: float = 0.4) -> list[bytes]:
    responses.clear()
    await client.write_gatt_char(WRITE_UUID, bytes([cmd]), response=False)
    await asyncio.sleep(wait)
    return list(responses)


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
        print("Device not found.")
        sys.exit(1)
    print(f"Found: {device.name} ({device.address})")

    responses: list[bytes] = []
    loop = asyncio.get_event_loop()

    def on_notify(_, data: bytearray) -> None:
        responses.append(bytes(data))

    try:
        async with BleakClient(device) as client:
            await client.start_notify(NOTIFY_UUID, on_notify)
            await client.write_gatt_char(WRITE_UUID, bytes([0x55]), response=False)
            await asyncio.sleep(0.5)
            responses.clear()

            # ── Phase 1: stability ────────────────────────────────────────────
            print("\n── Phase 1: stability (cube flat on table) ──────────────────")
            print("Leave the cube still.\n")
            await asyncio.sleep(1.0)
            for i in range(10):
                r62 = await poll(client, 0x62, responses)
                r76 = await poll(client, 0x76, responses)
                for r in r62:
                    print(f"  [{_ts()}]  0x62  {_decode(r)}")
                for r in r76:
                    print(f"  [{_ts()}]  0x76  {_decode(r)}")

            # ── Phase 2: orientation sweep ────────────────────────────────────
            print("\n── Phase 2: orientation sweep (60 s) ────────────────────────")
            print("Place each face UP in order, holding ~8 s per face:")
            print("  White, Yellow, Green, Blue, Red, Orange\n")

            end = loop.time() + 60
            prev62 = prev76 = None
            while loop.time() < end:
                r62 = await poll(client, 0x62, responses)
                r76 = await poll(client, 0x76, responses)
                for r in r62:
                    d = _decode(r)
                    marker = " ◄ CHANGED" if r != prev62 and prev62 is not None else ""
                    print(f"  [{_ts()}]  0x62  {d}{marker}")
                    prev62 = r
                for r in r76:
                    d = _decode(r)
                    marker = " ◄ CHANGED" if r != prev76 and prev76 is not None else ""
                    print(f"  [{_ts()}]  0x76  {d}{marker}")
                    prev76 = r
                await asyncio.sleep(0.2)

            # ── Phase 3: neighbours ───────────────────────────────────────────
            print("\n── Phase 3: neighbours 0x63–0x65, 0x77 ──────────────────────")
            for cmd in [0x63, 0x64, 0x65, 0x77]:
                rs = await poll(client, cmd, responses, wait=0.8)
                if rs:
                    for r in rs:
                        print(f"  0x{cmd:02x}  →  {r.hex(' ')}  {_decode(r)}")
                else:
                    print(f"  0x{cmd:02x}  →  (no response)")

    except TimeoutError:
        print("Connection timed out.")
        sys.exit(1)
    except Exception as e:
        print(f"Connection error: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
