#!/usr/bin/env python3
"""
Comprehensive event watcher: looks for unsolicited battery/status packets,
probes battery commands with response=True, and watches for a solved notification.

Usage:
    python dev/events_watch.py <ADDRESS_OR_NAME>

Phases:
  1. Wait 30s after connect for any unsolicited notifications (battery auto-report?)
  2. Try battery commands with write-with-response (different from write-without-response)
  3. Wait for you to solve the cube — press Enter when solved
"""

import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

SCAN_DURATION = 10
NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

FACE_LETTERS = ["B", "F", "U", "D", "R", "L"]


def make_cmd(*payload: int) -> bytes:
    body = bytes([0x2a, *payload])
    return body + bytes([sum(body) & 0xFF, 0x0d, 0x0a])


def decode(data: bytearray) -> str:
    if len(data) < 2 or data[0] != 0x2a:
        return f"UNKNOWN {data.hex(' ')}"
    t = data[1]
    if t == 0x06 and len(data) == 8:
        fid = data[3]; d = data[4]
        pair = fid // 2
        letter = FACE_LETTERS[pair] if pair < len(FACE_LETTERS) else f"?{fid}"
        notation = f"{letter}'" if fid % 2 else letter
        return f"MOVE  {notation:<3}  face_id={fid} angle={d*30}°"
    if t == 0x05 and len(data) == 7:
        return f"STATE val={data[3]} ({'moving?' if data[3] else 'still?'})"
    return f"RAW   type=0x{t:02x} len={len(data)}  {data.hex(' ')}"


def on_notify(_, data: bytearray) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"  [{ts}]  {decode(data)}")


async def phase1_wait(client: BleakClient) -> None:
    print("\n─── Phase 1: Waiting 30s for unsolicited notifications ───")
    print("  (don't touch the cube)\n")
    await asyncio.sleep(30)
    print("  Done waiting.")


async def phase2_battery_commands(client: BleakClient) -> None:
    print("\n─── Phase 2: Battery command candidates (write WITH response) ───\n")
    candidates = [
        # Common patterns in similar Nordic UART cube protocols
        ("batt? type=09 sub=01", make_cmd(0x09, 0x01)),
        ("batt? type=08 sub=00", make_cmd(0x08, 0x00)),
        ("batt? type=07 sub=00", make_cmd(0x07, 0x00)),
        ("batt? type=0a sub=00", make_cmd(0x0a, 0x00)),
        ("batt? type=0b sub=00", make_cmd(0x0b, 0x00)),
        ("batt? type=01 sub=00", make_cmd(0x01, 0x00)),
        ("batt? type=02 sub=00", make_cmd(0x02, 0x00)),
        ("batt? type=03 sub=00", make_cmd(0x03, 0x00)),
        ("batt? type=04 sub=00", make_cmd(0x04, 0x00)),
        # Single byte type only (no sub-byte)
        ("single type=01",       make_cmd(0x01)),
        ("single type=02",       make_cmd(0x02)),
        ("single type=03",       make_cmd(0x03)),
        ("single type=09",       make_cmd(0x09)),
        # ASCII-style probe
        ("ascii *b\\r\\n",       b"*b\r\n"),
        ("ascii *B\\r\\n",       b"*B\r\n"),
        ("ascii *?\\r\\n",       b"*?\r\n"),
    ]
    for label, cmd in candidates:
        print(f"  >>> {label}: {cmd.hex(' ')}")
        try:
            await client.write_gatt_char(WRITE_UUID, cmd, response=True)
        except BleakError as e:
            print(f"      write error: {e}")
        await asyncio.sleep(0.8)


async def phase3_solved(client: BleakClient) -> None:
    print("\n─── Phase 3: Solved-state detection ───")
    print("  Scramble the cube now, then solve it completely.")
    print("  Watch for any new packet types that appear when solved.")
    input("  Press Enter when you are ABOUT TO START solving...")
    print("  Go! Watching for packets...\n")
    await asyncio.sleep(60)
    print("  (60s elapsed — press Ctrl-C if you need more time)")


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python dev/events_watch.py <ADDRESS_OR_NAME>")
        sys.exit(1)

    target = sys.argv[1]
    print(f"Scanning for '{target}' ...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, _: (d.name and target.lower() in d.name.lower())
            or d.address.lower() == target.lower(),
        timeout=SCAN_DURATION,
    )
    if not device:
        print("Device not found.")
        sys.exit(1)

    print(f"Found: {device.name} ({device.address})\nConnecting ...")
    async with BleakClient(device) as client:
        await client.start_notify(NOTIFY_UUID, on_notify)
        try:
            await phase1_wait(client)
            await phase2_battery_commands(client)
            await phase3_solved(client)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nStopped.")
        finally:
            await client.stop_notify(NOTIFY_UUID)


if __name__ == "__main__":
    asyncio.run(main())
