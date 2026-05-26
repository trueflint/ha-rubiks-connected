#!/usr/bin/env python3
"""
Live monitor for 0x62 and 0x76. Polls every 300 ms and prints only when
the value changes, with a timestamp.

Use this while bringing an external magnet close to the cube to test
whether 0x62 is a magnetometer reading.

Usage:
    python3 dev/monitor_62.py <ADDRESS>
"""

import asyncio
import sys
from datetime import datetime

from bleak import BleakClient, BleakScanner

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _signed(b: int) -> int:
    return b if b < 128 else b - 256


async def poll(client, cmd: int, responses: list, wait: float = 0.3) -> bytes | None:
    responses.clear()
    await client.write_gatt_char(WRITE_UUID, bytes([cmd]), response=False)
    await asyncio.sleep(wait)
    for r in responses:
        if (len(r) == 8 and r[0] == 0x2a and r[1] == 0x06
                and r[2] in (0x0a, 0x0c)):
            return r
    return None


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
    print("Monitoring 0x62 and 0x76. Ctrl-C to stop.\n")
    print(f"{'Time':15s}  {'0x62 raw':12s}  {'0x62 signed':14s}  {'0x76 raw':12s}")
    print("-" * 60)

    responses: list[bytes] = []
    prev62 = prev76 = None

    def on_notify(_, data: bytearray) -> None:
        responses.append(bytes(data))

    try:
        async with BleakClient(device) as client:
            await client.start_notify(NOTIFY_UUID, on_notify)
            await client.write_gatt_char(WRITE_UUID, bytes([0x55]), response=False)
            await asyncio.sleep(0.5)
            responses.clear()

            while True:
                r62 = await poll(client, 0x62, responses, wait=0.3)
                r76 = await poll(client, 0x76, responses, wait=0.3)

                changed = (r62 != prev62) or (r76 != prev76)
                if changed:
                    ts = _ts()
                    if r62 and len(r62) >= 6:
                        a, b = r62[3], r62[4]
                        s62 = f"[{a:3d},{b:3d}]"
                        ss62 = f"[{_signed(a):+d},{_signed(b):+d}]"
                    else:
                        s62 = ss62 = "—"
                    if r76 and len(r76) >= 6:
                        a2, b2 = r76[3], r76[4]
                        s76 = f"[{a2:3d},{b2:3d}]"
                    else:
                        s76 = "—"

                    marker = "  ◄◄◄" if (r62 != prev62) else ""
                    print(f"{ts:15s}  {s62:12s}  {ss62:14s}  {s76:12s}{marker}")
                    prev62, prev76 = r62, r76

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopped.")
    except TimeoutError:
        print("Connection timed out.")
        sys.exit(1)
    except Exception as e:
        print(f"Connection error: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
