#!/usr/bin/env python3
"""
Investigate mode/settings write commands and soft-reset candidates.

Tests two things:

A) Mode write: 0x57 with various single-byte payloads — does writing back
   the current flags value (0xee) produce a response? Does flipping a bit?

B) Soft reset: single-byte candidates not yet confirmed harmless, sent one
   at a time with 2 s observation. Skips all known-dangerous commands.
   Watches for reconnection, "HANDSHAKE" response, or cube state change.

Usage:
    python3 dev/investigate_modes.py <ADDRESS>
"""

import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

# Known-dangerous — never send
SKIP = {0x31, 0x34, 0x36, 0x51, 0x52, 0x53, 0x54, 0x78}

# Already well-understood — skip to keep the run short
KNOWN = {
    0x32, 0x33, 0x35, 0x39, 0x4e, 0x55, 0x56, 0x57, 0x58, 0x59,
}

# Unexplored single-byte candidates in interesting ranges
# 0x60-0x7f: completely dark territory adjacent to known 0x5x range
# 0x30, 0x37, 0x38, 0x3a-0x3f: gaps in the 0x3x query range
RESET_CANDIDATES = [
    0x30,
    0x37, 0x38,
    0x3a, 0x3b, 0x3c, 0x3d, 0x3e, 0x3f,
    0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67,
    0x68, 0x69, 0x6a, 0x6b, 0x6c, 0x6d, 0x6e, 0x6f,
    0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77,
    0x79, 0x7a, 0x7b, 0x7c, 0x7d, 0x7e, 0x7f,
]

# 0x57 payloads to test (mode write candidates)
# Current flags = 0xee = 0b11101110; try echo, flip each dark bit, all-on, all-off
MODE_WRITE_PAYLOADS = [
    (0xee, "echo current flags (0b11101110)"),
    (0xfe, "set bit 0  (0b11111110)"),
    (0xde, "set bit 4  (0b11011110 — but bit already off; flip on)"),
    (0xff, "all bits on"),
    (0x00, "all bits off"),
    (0xee, "restore original"),
]


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
        return f"type=0x{data[1]:02x} sub=0x{data[2]:02x} payload={payload.hex(' ')} ({list(payload)})"
    return f"raw {data.hex(' ')}"


async def send_and_collect(client, cmd: bytes, responses: list, wait: float = 1.5) -> list[bytes]:
    responses.clear()
    await client.write_gatt_char(WRITE_UUID, cmd, response=False)
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

    def on_notify(_, data: bytearray) -> None:
        b = bytes(data)
        responses.append(b)
        print(f"    [{_ts()}]  {b.hex(' ')}  {_fmt(b)}")

    try:
        async with BleakClient(device) as client:
            await client.start_notify(NOTIFY_UUID, on_notify)
            await client.write_gatt_char(WRITE_UUID, bytes([0x55]), response=False)
            await asyncio.sleep(0.5)
            responses.clear()

            # ── Section A: mode write via 0x57 ───────────────────────────────
            print("\n══ Section A: 0x57 mode-write candidates ════════════════════")
            print("(Sending 0x57 + payload byte; watching for response or behaviour change)\n")

            for payload_byte, label in MODE_WRITE_PAYLOADS:
                cmd = bytes([0x57, payload_byte])
                print(f"  0x57 0x{payload_byte:02x}  [{label}]")
                rs = await send_and_collect(client, cmd, responses, wait=1.0)
                if not rs:
                    print(f"    (no response)")
                # read back 0x56 to see if flags changed
                rs56 = await send_and_collect(client, bytes([0x56]), responses, wait=0.5)
                for r in rs56:
                    print(f"    0x56 after → {r.hex(' ')}  {_fmt(r)}")
                print()

            # ── Section B: single-byte reset / mode candidates ───────────────
            print("══ Section B: unexplored single-byte candidates ═════════════")
            print("(2 s observation each; watching for responses or disconnect)\n")

            interesting: dict[str, list[str]] = {}

            for cmd_byte in RESET_CANDIDATES:
                if cmd_byte in SKIP or cmd_byte in KNOWN:
                    continue
                key = f"0x{cmd_byte:02x}"
                print(f"  {key} ...", end="", flush=True)
                rs = await send_and_collect(client, bytes([cmd_byte]), responses, wait=2.0)
                if rs:
                    interesting[key] = [r.hex(" ") for r in rs]
                    print(f"  ← {len(rs)} response(s)")
                else:
                    print("  (none)")

                if not client.is_connected:
                    print(f"\n  !! Cube disconnected after {key} — stopping section B.")
                    break

            if interesting:
                print("\n── Interesting responses in section B ───────────────────────")
                for k, resps in interesting.items():
                    for r in resps:
                        b = bytes.fromhex(r.replace(" ", ""))
                        print(f"  {k}  →  {r}  {_fmt(b)}")
            else:
                print("\n  No responses in section B.")

    except TimeoutError:
        print("Connection timed out.")
        sys.exit(1)
    except Exception as e:
        print(f"Connection error: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
