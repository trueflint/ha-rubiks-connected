#!/usr/bin/env python3
"""
Send a single command byte to the cube and report the response.

Usage:
    python dev/send_cmd.py <ADDRESS> <HEX_BYTE>

Example:
    python dev/send_cmd.py F1:EC:84:F0:A4:3F 0x53
"""

import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"


async def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python dev/send_cmd.py <ADDRESS> <HEX_BYTE>")
        sys.exit(1)

    target  = sys.argv[1]
    cmd_int = int(sys.argv[2], 16)
    cmd     = bytes([cmd_int])

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
    print(f"Sending: 0x{cmd_int:02x} ({cmd.hex()})\n")

    responses = []

    def on_notify(_, data: bytearray) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        b  = bytes(data)
        responses.append(b)
        try:
            text = b.decode("ascii")
            print(f"  [{ts}]  {b.hex(' ')}  (ASCII: {text!r})")
        except Exception:
            print(f"  [{ts}]  {b.hex(' ')}")

    try:
        async with BleakClient(device) as client:
            await client.start_notify(NOTIFY_UUID, on_notify)
            await client.write_gatt_char(WRITE_UUID, cmd, response=False)
            print("Waiting 3 seconds for response and to observe if cube disconnects ...")
            await asyncio.sleep(3.0)
            still_connected = client.is_connected
            print(f"\nStill connected after 3s: {still_connected}")
    except TimeoutError:
        print("Connection timed out — cube may have gone back to sleep.")
        sys.exit(1)
    except Exception as e:
        print(f"Connection error: {type(e).__name__}: {e}")
        sys.exit(1)

    if not responses:
        print("No response received.")
    else:
        print(f"{len(responses)} response(s) received.")


if __name__ == "__main__":
    asyncio.run(main())
