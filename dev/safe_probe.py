#!/usr/bin/env python3
"""
Safety probe: sends commands one at a time while staying connected.
A dot (·) prints for every face turn detected. After each command:
  Enter = moves still OK, next command
  n     = moves STOPPED (dangerous command!)
  q     = quit

Results are saved to safe_probe_results.json.

Usage:
    python dev/safe_probe.py <ADDRESS> [start_hex [end_hex]]

Examples:
    python dev/safe_probe.py F1:EC:84:F0:A4:3F 0x28 0x4f
    python dev/safe_probe.py F1:EC:84:F0:A4:3F 0x00 0xff
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
MOVE_TYPE   = 0x06

results: dict[str, str] = {}
_responses:     list[bytes] = []
_move_detected: bool        = False


def _notify(_, data: bytearray) -> None:
    global _move_detected
    b = bytes(data)
    _responses.append(b)
    if len(b) >= 2 and b[0] == 0x2a and b[1] == MOVE_TYPE:
        sys.stdout.write("·")
        sys.stdout.flush()
        _move_detected = True


async def _ask(prompt: str) -> str:
    """Read a line of input without blocking the event loop."""
    loop = asyncio.get_event_loop()
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = await loop.run_in_executor(None, sys.stdin.readline)
    return line.strip().lower()


async def _find(target: str):
    return await BleakScanner.find_device_by_filter(
        lambda d, _: (d.name and target.lower() in d.name.lower())
            or d.address.lower() == target.lower(),
        timeout=15,
    )


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target    = sys.argv[1]
    start_hex = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x00
    end_hex   = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0xFF

    # 0x32 (battery) prepended as a known-safe control
    commands = [0x32] + list(range(start_hex, end_hex + 1))

    print(f"\nSafe probe: 0x{start_hex:02x}–0x{end_hex:02x}  ({end_hex - start_hex + 1} commands + 0x32 control)")
    print("=" * 60)
    print("Turn the cube continuously. A dot (·) appears for each turn.")
    print("After each command: Enter=safe  n=broken  q=quit")
    print("=" * 60)

    dangerous   = []
    interesting = []
    idx         = 0
    quit_flag   = False

    while idx < len(commands) and not quit_flag:
        # ── connect ───────────────────────────────────────────────────────────
        print(f"\nConnecting ...")
        device = await _find(target)
        if not device:
            print("  [not found — retrying in 5s]")
            await asyncio.sleep(5)
            continue

        disconnected = asyncio.Event()
        idx_at_connect = idx

        try:
            async with BleakClient(
                device,
                disconnected_callback=lambda _: disconnected.set(),
            ) as client:
                await client.start_notify(NOTIFY_UUID, _notify)

                # ── test phase: wait for a real move before probing ───────────
                global _move_detected
                _move_detected = False
                print("Connected! Turn the cube now to confirm moves are detected ...")
                while not _move_detected:
                    await asyncio.sleep(0.2)
                print("✓ Move detected! Starting probe — keep turning the cube.\n")

                while idx < len(commands) and not disconnected.is_set() and not quit_flag:
                    b     = commands[idx]
                    label = f"0x{b:02x}"
                    note  = " (control)" if b == 0x32 else ""

                    _responses.clear()
                    await client.write_gatt_char(WRITE_UUID, bytes([b]), response=False)
                    await asyncio.sleep(0.4)

                    non_move = [r for r in _responses
                                if not (len(r) >= 2 and r[0] == 0x2a and r[1] == MOVE_TYPE)]
                    resp_str = ""
                    if non_move:
                        resp_str = "  ← " + " | ".join(r.hex(" ") for r in non_move)

                    ans = await _ask(f"\n  {label}{note}{resp_str}  [Enter/n/q] ")

                    if ans == "q":
                        quit_flag = True
                        break
                    elif ans == "n":
                        results[label] = "DANGEROUS"
                        dangerous.append(label)
                        print(f"  *** DANGEROUS: {label} ***")
                        idx += 1
                        break   # reconnect
                    else:
                        status = "safe"
                        if non_move:
                            status = "safe+response:" + " | ".join(r.hex(" ") for r in non_move)
                            interesting.append((label, status))
                        results[label] = status
                        idx += 1

                if disconnected.is_set():
                    print("\n  [disconnected — reconnecting]")

        except Exception as exc:
            print(f"  [error: {exc}]")
            if idx > idx_at_connect:
                # error occurred during command execution — record and advance
                results[f"0x{commands[idx]:02x}"] = f"error:{exc}"
                idx += 1
            # else: error occurred during connection setup — retry same idx
            await asyncio.sleep(3)

    # ── save & report ─────────────────────────────────────────────────────────
    out = Path(__file__).parent / "safe_probe_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "═" * 60)
    print(f"DANGEROUS ({len(dangerous)}): {', '.join(dangerous) or 'none found'}")
    print(f"INTERESTING ({len(interesting)}):")
    for label, status in interesting:
        print(f"  {label}: {status}")
    print(f"\nResults → {out}")
    print("═" * 60)


if __name__ == "__main__":
    asyncio.run(main())
