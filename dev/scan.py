#!/usr/bin/env python3
"""
BLE scanner: finds nearby devices and lists services/characteristics
for a device matching a name or address.

Usage:
    python dev/scan.py                    # list all nearby BLE devices
    python dev/scan.py <ADDRESS_OR_NAME>  # connect and dump all services
"""

import asyncio
import sys

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic


SCAN_DURATION = 10  # seconds


async def scan_devices() -> None:
    print(f"Scanning for BLE devices for {SCAN_DURATION}s ...\n")
    results = await BleakScanner.discover(timeout=SCAN_DURATION, return_adv=True)
    if not results:
        print("No BLE devices found. Is Bluetooth enabled?")
        return
    items = sorted(results.values(), key=lambda pair: pair[0].name or "")
    print(f"{'ADDRESS':<20}  {'RSSI':>5}  NAME")
    print("-" * 60)
    for d, adv in items:
        print(f"{d.address:<20}  {adv.rssi:>5}  {d.name or '(unknown)'}")


async def dump_services(address_or_name: str) -> None:
    print(f"Scanning to resolve '{address_or_name}' ...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, _: (
            d.name and address_or_name.lower() in d.name.lower()
        ) or d.address.lower() == address_or_name.lower(),
        timeout=SCAN_DURATION,
    )
    if device is None:
        print(f"Device '{address_or_name}' not found. Is it powered on and in range?")
        return

    print(f"Found: {device.name} ({device.address})\n")
    print("Connecting ...")
    async with BleakClient(device) as client:
        print(f"Connected. Services:\n")
        for service in client.services:
            print(f"  [SVC] {service.uuid}  {service.description}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"    [CHR] {char.uuid}  [{props}]  {char.description}")
                for desc in char.descriptors:
                    print(f"      [DSC] {desc.uuid}  {desc.description}")


async def main() -> None:
    if len(sys.argv) < 2:
        await scan_devices()
    else:
        await dump_services(sys.argv[1])


if __name__ == "__main__":
    asyncio.run(main())
