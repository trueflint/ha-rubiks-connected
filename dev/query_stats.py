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

    async with BleakClient(device) as client:
        await client.start_notify(NOTIFY_UUID, lambda _, d: responses.append(bytes(d)))
        await asyncio.sleep(1.0)  # let connection settle
        await client.write_gatt_char(WRITE_UUID, bytes([0x50]), response=False)
        await asyncio.sleep(0.5)
        responses.clear()
        await client.write_gatt_char(WRITE_UUID, bytes([0x51]), response=False)
        await asyncio.sleep(2.0)

    if not responses:
        print("No response received.")
        sys.exit(1)

    for r in responses:
        print(f"\nRaw:     {r.hex(' ')}")
        if len(r) >= 14 and r[0] == 0x2a and r[1] == 0x0c:
            payload = r[3:11]
            print(f"Payload: {payload.hex(' ')}")
            print(f"         as decimal: {list(payload)}")
            print(f"  byte[0..1] as uint16-LE: {int.from_bytes(payload[0:2], 'little')}")
            print(f"  byte[2..3] as uint16-LE: {int.from_bytes(payload[2:4], 'little')}")
            print(f"  byte[4..5] as uint16-LE: {int.from_bytes(payload[4:6], 'little')}")
            print(f"  byte[6..7] as uint16-LE: {int.from_bytes(payload[6:8], 'little')}")


if __name__ == "__main__":
    asyncio.run(main())
