#!/usr/bin/env python3
"""
Command probe: sends candidate request packets on the write characteristic
and prints any notifications that come back. Helps find battery level,
cube state, and other request/response commands.

Usage:
    python dev/cmd_probe.py <ADDRESS_OR_NAME>
"""

import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner

SCAN_DURATION = 10
NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"


def make_cmd(*payload_bytes: int) -> bytes:
    """Build a framed command: 0x2a + payload + checksum + \r\n"""
    body = bytes([0x2a, *payload_bytes])
    chk = sum(body) & 0xFF
    return body + bytes([chk, 0x0d, 0x0a])


# Candidate commands to try. Format: (label, bytes)
# We try message types 0x01-0x0f with sub-byte 0x01, plus a few extras.
CANDIDATES = [
    ("type=01 sub=01", make_cmd(0x01, 0x01)),
    ("type=02 sub=01", make_cmd(0x02, 0x01)),
    ("type=03 sub=01", make_cmd(0x03, 0x01)),
    ("type=04 sub=01", make_cmd(0x04, 0x01)),
    ("type=07 sub=01", make_cmd(0x07, 0x01)),
    ("type=08 sub=01", make_cmd(0x08, 0x01)),
    ("type=09 sub=01", make_cmd(0x09, 0x01)),  # common battery request in similar protocols
    ("type=0a sub=01", make_cmd(0x0a, 0x01)),
    ("type=0b sub=01", make_cmd(0x0b, 0x01)),
    ("type=0c sub=01", make_cmd(0x0c, 0x01)),
    ("type=0f sub=01", make_cmd(0x0f, 0x01)),
    ("type=05 sub=01", make_cmd(0x05, 0x01)),  # we've seen 0x05 in notifications
    ("type=06 sub=00", make_cmd(0x06, 0x00)),  # move type with 0x00
]

responses: list[tuple[str, bytearray]] = []


def handler(_, data: bytearray) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    responses.append((ts, data))
    print(f"  <<< [{ts}]  {data.hex(' ')}")


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python dev/cmd_probe.py <ADDRESS_OR_NAME>")
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

    print(f"Found: {device.name} ({device.address})\nConnecting ...\n")
    async with BleakClient(device) as client:
        await client.start_notify(NOTIFY_UUID, handler)
        print("Don't touch the cube during this probe.\n")

        for label, cmd in CANDIDATES:
            print(f">>> Sending {label}: {cmd.hex(' ')}")
            responses.clear()
            await client.write_gatt_char(WRITE_UUID, cmd, response=False)
            await asyncio.sleep(0.6)
            if not responses:
                print("    (no response)")

        await client.stop_notify(NOTIFY_UUID)

    print("\n=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
