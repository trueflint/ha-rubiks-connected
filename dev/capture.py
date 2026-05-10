#!/usr/bin/env python3
"""
BLE notification capture: connects to the cube and prints every
notification/indication from every characteristic so we can reverse-engineer
the move protocol.

Usage:
    python dev/capture.py <ADDRESS_OR_NAME>

While running, turn cube faces and watch what comes in.
Press Ctrl-C to stop.
"""

import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic


SCAN_DURATION = 10


def notification_handler(char: BleakGATTCharacteristic, data: bytearray) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hex_data = data.hex(" ")
    print(f"[{ts}] {char.uuid}  ({len(data)}B)  {hex_data}")


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python dev/capture.py <ADDRESS_OR_NAME>")
        sys.exit(1)

    target = sys.argv[1]
    print(f"Scanning for '{target}' ...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, _: (
            d.name and target.lower() in d.name.lower()
        ) or d.address.lower() == target.lower(),
        timeout=SCAN_DURATION,
    )
    if device is None:
        print(f"Device '{target}' not found.")
        sys.exit(1)

    print(f"Found: {device.name} ({device.address})\nConnecting ...")
    async with BleakClient(device) as client:
        notify_chars = [
            char
            for service in client.services
            for char in service.characteristics
            if "notify" in char.properties or "indicate" in char.properties
        ]

        if not notify_chars:
            print("No notify/indicate characteristics found on this device!")
            return

        print(f"\nSubscribed to {len(notify_chars)} characteristic(s):")
        for char in notify_chars:
            print(f"  {char.uuid}  [{', '.join(char.properties)}]")
            await client.start_notify(char, notification_handler)

        print("\nTurn cube faces now. Press Ctrl-C to stop.\n")
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

        for char in notify_chars:
            try:
                await client.stop_notify(char)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
