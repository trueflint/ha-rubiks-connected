#!/usr/bin/env python3
"""
Systematic command probe to find stats/history request commands.

Phase 1: tries every single byte 0x00–0xFF (battery was found as 0x32 this way).
Phase 2: tries framed commands  2a [type] [sub] [chk] 0d 0a  for type 0x00–0x1f,
         sub 0x00–0x07 — covering the known protocol command space.

Probes in small batches, reconnecting between each batch so a cube disconnect
or BlueZ cache flush doesn't abort the whole run.

Usage:
    python dev/stats_probe.py <ADDRESS_OR_NAME>
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rubiks_connected"))

from bleak import BleakClient, BleakScanner

NOTIFY_UUID     = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID      = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
SCAN_TIMEOUT    = 15
WAIT_AFTER      = 0.4    # seconds to wait for a response after each write
BATCH_SIZE      = 20     # commands per connection
RECONNECT_DELAY = 4.0    # seconds between disconnect and next scan

hits: list[tuple[str, bytes, list[bytes]]] = []
_pending: list[bytes] = []


def _notify(_handle, data: bytearray) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    b = bytes(data)
    _pending.append(b)
    print(f"    <<< [{ts}]  {b.hex(' ')}")


def _framed(*payload: int) -> bytes:
    body = bytes([0x2a, *payload])
    return body + bytes([sum(body) & 0xFF, 0x0d, 0x0a])


async def _find_device(target: str) -> object:
    """Scan until we find the device. Retries up to 5 times."""
    for attempt in range(5):
        if attempt:
            print(f"  [scan attempt {attempt + 1} ...]")
            await asyncio.sleep(RECONNECT_DELAY)
        device = await BleakScanner.find_device_by_filter(
            lambda d, _: (d.name and target.lower() in d.name.lower())
                or d.address.lower() == target.lower(),
            timeout=SCAN_TIMEOUT,
        )
        if device:
            return device
    return None


async def _run_batch(target: str, commands: list[tuple[str, bytes]]) -> list[tuple[str, bytes, list[bytes]]]:
    """Connect, run a batch of commands, disconnect. Returns hits from this batch."""
    device = await _find_device(target)
    if not device:
        print("  [could not find device — skipping batch]")
        return []

    batch_hits = []
    try:
        async with BleakClient(device) as client:
            await client.start_notify(NOTIFY_UUID, _notify)
            for label, cmd in commands:
                if not client.is_connected:
                    print("  [disconnected mid-batch]")
                    break
                _pending.clear()
                try:
                    await client.write_gatt_char(WRITE_UUID, cmd, response=False)
                except Exception as exc:
                    print(f"  [write error on {label}: {exc}]")
                    break
                await asyncio.sleep(WAIT_AFTER)
                if _pending:
                    entry = (label, cmd, list(_pending))
                    batch_hits.append(entry)
                    print(f"  *** HIT: {label}  {cmd.hex(' ')} ***")
    except Exception as exc:
        print(f"  [connection error: {exc}]")

    return batch_hits


async def _run_all(target: str, commands: list[tuple[str, bytes]], phase_name: str) -> None:
    total = len(commands)
    for i in range(0, total, BATCH_SIZE):
        batch = commands[i : i + BATCH_SIZE]
        last_label = batch[-1][0]
        print(f"  [{phase_name}] commands {i}–{i + len(batch) - 1}  ({last_label}) ...")
        batch_hits = await _run_batch(target, batch)
        hits.extend(batch_hits)
        if i + BATCH_SIZE < total:
            await asyncio.sleep(RECONNECT_DELAY)


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python dev/stats_probe.py <ADDRESS_OR_NAME>")
        sys.exit(1)

    target = sys.argv[1]

    # ── Phase 1: single-byte sweep 0x00–0xFF ─────────────────────────────────
    print("=== Phase 1: single-byte sweep (0x00–0xFF) ===")
    phase1 = [(f"single 0x{b:02x}", bytes([b])) for b in range(0x100)]
    await _run_all(target, phase1, "phase1")

    # ── Phase 2: framed sweep  2a [type] [sub] ────────────────────────────────
    print("\n=== Phase 2: framed sweep (type 0x00–0x1f, sub 0x00–0x07) ===")
    phase2 = [
        (f"framed type=0x{t:02x} sub=0x{s:02x}", _framed(t, s))
        for t in range(0x20)
        for s in range(0x08)
    ]
    await _run_all(target, phase2, "phase2")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print(f"SUMMARY — {len(hits)} command(s) got a response:")
    for label, cmd, responses in hits:
        print(f"\n  {label}")
        print(f"    sent:  {cmd.hex(' ')}")
        for r in responses:
            print(f"    reply: {r.hex(' ')}")
    print("═" * 70)


if __name__ == "__main__":
    asyncio.run(main())
