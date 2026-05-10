#!/usr/bin/env python3
"""
Probe all unnamed BLE devices by connecting and reading their GATT services.
Helps identify which device is your cube.

Usage:
    python dev/probe.py                    # probe all unnamed devices in range
    python dev/probe.py AA:BB:CC:DD:EE:FF  # probe one specific address
"""

import asyncio
import sys

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError


SCAN_DURATION = 8
CONNECT_TIMEOUT = 10


async def probe_device(address: str) -> None:
    print(f"\n{'='*60}")
    print(f"Probing {address} ...")
    try:
        async with BleakClient(address, timeout=CONNECT_TIMEOUT) as client:
            print(f"  Connected!")
            for service in client.services:
                print(f"  [SVC] {service.uuid}  {service.description or ''}")
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    val = ""
                    if "read" in char.properties:
                        try:
                            raw = await client.read_gatt_char(char)
                            val = f"  value={raw.hex(' ')}"
                            # Try to decode as ASCII too
                            try:
                                text = raw.decode("utf-8").strip()
                                if text.isprintable() and text:
                                    val += f'  ("{text}")'
                            except Exception:
                                pass
                        except Exception:
                            val = "  (read error)"
                    print(f"    [CHR] {char.uuid}  [{props}]{val}")
    except BleakError as e:
        print(f"  Failed to connect: {e}")
    except asyncio.TimeoutError:
        print(f"  Timed out connecting.")


async def main() -> None:
    if len(sys.argv) >= 2:
        await probe_device(sys.argv[1])
        return

    print(f"Scanning {SCAN_DURATION}s for unnamed devices ...")
    results = await BleakScanner.discover(timeout=SCAN_DURATION, return_adv=True)
    targets = [
        (d, adv) for d, adv in results.values()
        if not d.name
    ]
    named = [(d, adv) for d, adv in results.values() if d.name]

    if named:
        print("\nNamed devices (skipping):")
        for d, adv in named:
            print(f"  {d.address}  {d.name}  RSSI={adv.rssi}")

    if not targets:
        print("No unnamed devices found.")
        return

    # Sort by signal strength — probe strongest first (most likely to be cube)
    targets.sort(key=lambda pair: pair[1].rssi, reverse=True)
    print(f"\nWill probe {len(targets)} unnamed device(s), strongest signal first.")
    print("Press Ctrl-C at any time to stop.\n")

    for d, adv in targets:
        await probe_device(d.address)


if __name__ == "__main__":
    asyncio.run(main())
