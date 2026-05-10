#!/usr/bin/env python3
"""
Delta scanner: scans twice so you can identify your cube by turning it off
between scans. Devices in scan 2 but not scan 1 are new; devices gone are removed.

Usage:
    1. Make sure cube is OFF (or sleeping). Run this script.
    2. When prompted, turn the cube ON and shake it.
    3. See what appeared.
"""

import asyncio
from bleak import BleakScanner

SCAN_DURATION = 8


async def scan_once(label: str) -> dict:
    print(f"\n[{label}] Scanning {SCAN_DURATION}s ...")
    results = await BleakScanner.discover(timeout=SCAN_DURATION, return_adv=True)
    return {addr: (d, adv) for addr, (d, adv) in results.items()}


async def main() -> None:
    print("=== Delta BLE Scanner ===")
    print("Step 1: Make sure your cube is OFF or sleeping.")
    input("Press Enter when ready for baseline scan...")
    baseline = await scan_once("Baseline (cube OFF)")
    print(f"  Found {len(baseline)} device(s).")

    print("\nStep 2: Now TURN ON your cube and shake/turn it a few times.")
    input("Press Enter when ready for second scan...")
    after = await scan_once("After (cube ON)")
    print(f"  Found {len(after)} device(s).")

    new_addrs = set(after) - set(baseline)
    gone_addrs = set(baseline) - set(after)

    print("\n=== Results ===")
    if new_addrs:
        print("\nNEW devices (appeared after cube turned on) — likely your cube:")
        for addr in new_addrs:
            d, adv = after[addr]
            print(f"  {addr}  RSSI={adv.rssi:>4}  name={d.name or '(unknown)'}")
    else:
        print("\nNo new devices appeared. The cube may already have been visible,")
        print("or it may use a rotating/random MAC address.")
        print("\nAll devices found after cube was on:")
        for addr, (d, adv) in after.items():
            marker = " <-- WAS ALREADY THERE" if addr in baseline else " <-- NEW"
            print(f"  {addr}  RSSI={adv.rssi:>4}  name={d.name or '(unknown)'}{marker}")

    if gone_addrs:
        print("\nDevices that DISAPPEARED:")
        for addr in gone_addrs:
            d, adv = baseline[addr]
            print(f"  {addr}  name={d.name or '(unknown)'}")


if __name__ == "__main__":
    asyncio.run(main())
