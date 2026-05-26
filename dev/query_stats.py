#!/usr/bin/env python3
"""
Query the cube's 0x51 stats command and display the raw response.

Run this, note the 8 payload bytes, do some moves, run it again,
and compare to figure out what each byte means.

Usage:
    python dev/query_stats.py <ADDRESS_OR_NAME>
"""

import asyncio
import sys

from bleak import BleakClient, BleakScanner

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python dev/query_stats.py <ADDRESS_OR_NAME>")
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
    print(f"Found: {device.name} ({device.address})\nConnecting ...")

    responses = []

    listen_only = "--listen" in sys.argv

    try:
        async with BleakClient(device) as client:
            await client.start_notify(NOTIFY_UUID, lambda _, d: responses.append(bytes(d)))
            await asyncio.sleep(0.5)
            await client.write_gatt_char(WRITE_UUID, bytes([0x55]), response=False)  # handshake
            if listen_only:
                print("Listening for 5s after handshake (no further commands) ...")
                await asyncio.sleep(5.0)
            else:
                await asyncio.sleep(0.5)
                await client.write_gatt_char(WRITE_UUID, bytes([0x50]), response=False)
                await asyncio.sleep(0.5)
                responses.clear()
                await client.write_gatt_char(WRITE_UUID, bytes([0x51]), response=False)
                await asyncio.sleep(2.0)
    except TimeoutError:
        print("Connection timed out — cube may have gone back to sleep.")
        sys.exit(1)
    except Exception as e:
        print(f"Connection error: {type(e).__name__}: {e}")
        sys.exit(1)

    if not responses:
        print("No response received.")
        sys.exit(1)

    for r in responses:
        print(f"\nRaw:     {r.hex(' ')}")
        if len(r) < 6 or r[0] != 0x2a:
            print("  (unrecognised packet)")
            continue
        msg_type = r[1]
        payload = r[3:-3]   # strip header (2a type sub) and trailer (checksum 0d 0a)
        print(f"Type:    0x{msg_type:02x}  sub=0x{r[2]:02x}  payload_len={len(payload)}")
        print(f"Payload: {payload.hex(' ')}")
        print(f"         as decimal: {list(payload)}")
        for i in range(0, len(payload) - 1, 2):
            le = int.from_bytes(payload[i:i+2], 'little')
            be = int.from_bytes(payload[i:i+2], 'big')
            print(f"  byte[{i}..{i+1}]  LE={le:5d}  BE={be:5d}")


if __name__ == "__main__":
    asyncio.run(main())
