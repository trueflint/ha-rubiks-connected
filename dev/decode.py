#!/usr/bin/env python3
"""
Real-time move decoder using the rubiks_ble.protocol module.

Usage:
    python dev/decode.py <ADDRESS_OR_NAME>
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rubiks_connected"))

from bleak import BleakClient, BleakScanner
from rubiks_ble.protocol import NOTIFY_UUID, MoveEvent, StateEvent, decode


def on_notify(_, data: bytearray) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    event = decode(data)
    if isinstance(event, MoveEvent):
        print(f"[{ts}]  MOVE  {event}")
    elif isinstance(event, StateEvent):
        print(f"[{ts}]  STATE {event}")
    else:
        print(f"[{ts}]  RAW   {data.hex(' ')}")


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python dev/decode.py <ADDRESS_OR_NAME>")
        sys.exit(1)

    target = sys.argv[1]
    print(f"Scanning for '{target}' ...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, _: (d.name and target.lower() in d.name.lower())
            or d.address.lower() == target.lower(),
        timeout=10,
    )
    if not device:
        print("Device not found.")
        sys.exit(1)

    print(f"Found: {device.name} ({device.address})\nConnecting ...")
    async with BleakClient(device) as client:
        await client.start_notify(NOTIFY_UUID, on_notify)
        print("Listening. Turn faces — Ctrl-C to stop.\n")
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        await client.stop_notify(NOTIFY_UUID)


if __name__ == "__main__":
    asyncio.run(main())
