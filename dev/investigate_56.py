#!/usr/bin/env python3
"""
Structured investigation of commands 0x56, 0x57, 0x58, 0x59.

Runs four phases:
  Phase 1 — stability poll: query 0x56 rapidly; is the value stable?
  Phase 2 — orientation poll: query 0x56 every 0.5 s while you move the cube.
  Phase 3 — toggle test: read 0x56 baseline, send 0x58, re-read, send 0x59,
             re-read — does 0x58/0x59 change what 0x56 reports?
  Phase 4 — neighbour scan: try 0x5a–0x5f and also 0x57 to see if any
             respond after the earlier commands have been sent.

Usage:
    python3 dev/investigate_56.py <ADDRESS>
"""

import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _fmt(data: bytes) -> str:
    try:
        text = data.decode("ascii").strip()
        return f"ASCII {text!r}"
    except Exception:
        pass
    if len(data) >= 4 and data[0] == 0x2a:
        payload = data[3:-3]
        return (f"type=0x{data[1]:02x} sub=0x{data[2]:02x} "
                f"payload={payload.hex(' ')} ({list(payload)})")
    return f"raw: {data.hex(' ')}"


async def query(client, cmd: int, responses: list, wait: float = 0.5) -> list[bytes]:
    responses.clear()
    await client.write_gatt_char(WRITE_UUID, bytes([cmd]), response=False)
    await asyncio.sleep(wait)
    return list(responses)


async def prompt(loop, msg: str) -> None:
    await loop.run_in_executor(None, input, msg)


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

            # ── Phase 1: stability poll ───────────────────────────────────────
            print("\n── Phase 1: stability poll (0x56 × 10, cube at rest) ───────")
            print("Set the cube down and leave it still.")
            await asyncio.sleep(2.0)
            values = []
            for i in range(10):
                rs = await query(client, 0x56, responses, wait=0.3)
                for r in rs:
                    desc = _fmt(r)
                    print(f"  [{_ts()}]  {r.hex(' ')}  {desc}")
                    values.append(r)
            unique = set(r.hex() for r in values)
            print(f"  → {len(unique)} unique response(s) across 10 polls.")

            # ── Phase 2: orientation poll ─────────────────────────────────────
            print("\n── Phase 2: orientation poll (0x56, 30 s) ──────────────────")
            print("Slowly flip the cube to each of its 6 faces one at a time.")
            print("Hold each face-up for ~3 seconds before moving on.\n")
            end = asyncio.get_event_loop().time() + 30
            seen: dict[str, list[str]] = {}
            while asyncio.get_event_loop().time() < end:
                rs = await query(client, 0x56, responses, wait=0.5)
                for r in rs:
                    key = r.hex()
                    ts = _ts()
                    desc = _fmt(r)
                    print(f"  [{ts}]  {r.hex(' ')}  {desc}")
                    seen.setdefault(key, []).append(ts)
            print(f"\n  → {len(seen)} distinct value(s) seen:")
            for k, times in sorted(seen.items()):
                print(f"     {k}  (×{len(times)}: first at {times[0]}, last at {times[-1]})")

            # ── Phase 3: toggle test ──────────────────────────────────────────
            print("\n── Phase 3: toggle test ─────────────────────────────────────")
            print("Cube at rest, do not move it.\n")
            await asyncio.sleep(1.0)

            async def read_and_show(label: str) -> None:
                rs = await query(client, 0x56, responses)
                for r in rs:
                    print(f"  {label:30s}  {r.hex(' ')}  {_fmt(r)}")

            await read_and_show("0x56 baseline")
            rs58 = await query(client, 0x58, responses)
            for r in rs58:
                print(f"  {'0x58 sent → response:':30s}  {r.hex(' ')}  {_fmt(r)}")
            await read_and_show("0x56 after 0x58")
            rs59 = await query(client, 0x59, responses)
            for r in rs59:
                print(f"  {'0x59 sent → response:':30s}  {r.hex(' ')}  {_fmt(r)}")
            await read_and_show("0x56 after 0x59")
            # send 0x58 again to restore if it was a toggle
            await query(client, 0x58, responses)
            await read_and_show("0x56 after 0x58 again")

            # ── Phase 4: neighbours after context ────────────────────────────
            print("\n── Phase 4: neighbours after context ───────────────────────")
            for cmd in [0x57, 0x5a, 0x5b, 0x5c, 0x5d, 0x5e, 0x5f]:
                rs = await query(client, cmd, responses, wait=0.8)
                if rs:
                    for r in rs:
                        print(f"  0x{cmd:02x}  →  {r.hex(' ')}  {_fmt(r)}")
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
