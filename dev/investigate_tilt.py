#!/usr/bin/env python3
"""
Determine if 0x62 encodes orientation.

Prompts you to hold each of 6 faces upward, polls 0x62 ten times per face,
and reports the modal value. If the cube has a single-axis gravity threshold
we expect two groups of three faces.

Usage:
    python3 dev/investigate_tilt.py <ADDRESS>
"""

import asyncio
import collections
import sys

from bleak import BleakClient, BleakScanner

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

FACES = ["White", "Yellow", "Green", "Blue", "Red", "Orange"]


async def poll(client, cmd: int, responses: list, wait: float = 0.5) -> list[bytes]:
    responses.clear()
    await client.write_gatt_char(WRITE_UUID, bytes([cmd]), response=False)
    await asyncio.sleep(wait)
    return list(responses)


def payload_of(data: bytes) -> tuple[int, int] | None:
    if len(data) == 8 and data[0] == 0x2a and data[1] == 0x06 and data[2] == 0x0c:
        return (data[3], data[4])
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
    print(f"Found: {device.name} ({device.address})\n")

    responses: list[bytes] = []
    loop = asyncio.get_event_loop()

    def on_notify(_, data: bytearray) -> None:
        responses.append(bytes(data))

    results: dict[str, tuple[int, int] | None] = {}

    try:
        async with BleakClient(device) as client:
            await client.start_notify(NOTIFY_UUID, on_notify)
            await client.write_gatt_char(WRITE_UUID, bytes([0x55]), response=False)
            await asyncio.sleep(0.5)
            responses.clear()

            for face in FACES:
                await loop.run_in_executor(
                    None, input,
                    f"Hold {face}-face UP, set it down steady, then press Enter ..."
                )
                await asyncio.sleep(1.5)  # settle

                readings: list[tuple[int, int]] = []
                for _ in range(10):
                    rs = await poll(client, 0x62, responses)
                    for r in rs:
                        p = payload_of(r)
                        if p:
                            readings.append(p)

                if readings:
                    counter = collections.Counter(readings)
                    modal, count = counter.most_common(1)[0]
                    print(f"  {face:8s}  readings={[r for r in readings]}")
                    print(f"            modal={modal}  ({count}/{len(readings)} polls)\n")
                    results[face] = modal
                else:
                    print(f"  {face:8s}  no sub=0x0c responses received\n")
                    results[face] = None

    except TimeoutError:
        print("Connection timed out.")
        sys.exit(1)
    except Exception as e:
        print(f"Connection error: {type(e).__name__}: {e}")
        sys.exit(1)

    print("── Summary ──────────────────────────────────────────────────")
    groups: dict[tuple, list[str]] = collections.defaultdict(list)
    for face, val in results.items():
        groups[val].append(face)
    for val, faces in sorted(groups.items(), key=lambda x: str(x[0])):
        signed = None
        if val:
            a = val[0] if val[0] < 128 else val[0] - 256
            b = val[1] if val[1] < 128 else val[1] - 256
            signed = (a, b)
        print(f"  {val}  signed={signed}  →  {', '.join(faces)}")


if __name__ == "__main__":
    asyncio.run(main())
