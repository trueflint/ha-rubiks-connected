#!/usr/bin/env python3
"""
Guided calibration: walks you through one move at a time to build
the face-ID → notation mapping.

Usage:
    python dev/calibrate.py <ADDRESS_OR_NAME>

Hold the cube with White on top, Green facing you (standard orientation).
Follow the prompts exactly.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner

SCAN_DURATION = 10
NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

MOVES = [
    ("U",  "UP face CLOCKWISE 90°        (top face, turn right)"),
    ("U'", "UP face COUNTER-CLOCKWISE 90° (top face, turn left)"),
    ("D",  "DOWN face CLOCKWISE 90°       (bottom face, turn right when viewed from below)"),
    ("D'", "DOWN face COUNTER-CLOCKWISE 90°"),
    ("F",  "FRONT face CLOCKWISE 90°      (Green face toward you, turn right)"),
    ("F'", "FRONT face COUNTER-CLOCKWISE 90°"),
    ("B",  "BACK face CLOCKWISE 90°       (Blue face away from you, turn right from back)"),
    ("B'", "BACK face COUNTER-CLOCKWISE 90°"),
    ("R",  "RIGHT face CLOCKWISE 90°      (Red face on right, turn down)"),
    ("R'", "RIGHT face COUNTER-CLOCKWISE 90°"),
    ("L",  "LEFT face CLOCKWISE 90°       (Orange face on left, turn down)"),
    ("L'", "LEFT face COUNTER-CLOCKWISE 90°"),
]

RESULTS_FILE = Path("dev/face_map.json")


class Collector:
    def __init__(self):
        self.packets: list[tuple[int, int]] = []  # (face, dir)

    def handler(self, _char, data: bytearray) -> None:
        if len(data) == 8 and data[0] == 0x2a and data[1] == 0x06:
            face = data[3]
            direction = data[4]
            self.packets.append((face, direction))
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"  [{ts}]  face={face:2d} (0x{face:02x})  dir={direction:02x} ({direction//3*90}°)")

    def clear(self):
        self.packets.clear()

    def best_move(self) -> tuple[int, int] | None:
        """Return the face,dir pair from the most clearly committed move.
        Prefer dir=03 (CW 90°) or dir=09 (CCW 90°) as completed snaps.
        """
        # Look for a snapped quarter-turn (not 0° or 180°)
        snaps = [(f, d) for f, d in self.packets if d in (0x03, 0x09)]
        if snaps:
            # Return the last snap (most likely the completed move)
            return snaps[-1]
        # Fall back to any packet
        return self.packets[-1] if self.packets else None


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python dev/calibrate.py <ADDRESS_OR_NAME>")
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

    print(f"Found: {device.name} ({device.address})\n")
    print("=" * 60)
    print("CALIBRATION - Hold cube: White UP, Green toward YOU")
    print("Do ONE clean quarter-turn per prompt, then press Enter.")
    print("=" * 60)

    collector = Collector()
    face_map: dict[str, dict] = {}

    async with BleakClient(device) as client:
        await client.start_notify(NOTIFY_UUID, collector.handler)

        for notation, description in MOVES:
            print(f"\n>>> Move: {notation}")
            print(f"    {description}")
            print("    (undo the move after if you want, doesn't matter)")
            collector.clear()
            input("    Ready? Press Enter, then do the move...")

            # Wait briefly for any packets to arrive
            await asyncio.sleep(1.5)

            move = collector.best_move()
            if move:
                face_id, dir_val = move
                print(f"  --> Recorded: face={face_id} (0x{face_id:02x})  dir=0x{dir_val:02x}")
                face_map[notation] = {"face": face_id, "dir": dir_val, "description": description}
            else:
                print("  --> No move detected! Try again next run or check connection.")
                face_map[notation] = {"face": None, "dir": None, "description": description}

        await client.stop_notify(NOTIFY_UUID)

    print("\n" + "=" * 60)
    print("CALIBRATION COMPLETE")
    print("=" * 60)
    print("\nFace map:")
    for notation, info in face_map.items():
        print(f"  {notation:4s} => face=0x{info['face']:02x}  dir=0x{info['dir']:02x}" if info['face'] is not None else f"  {notation:4s} => NOT CAPTURED")

    RESULTS_FILE.write_text(json.dumps(face_map, indent=2))
    print(f"\nSaved to {RESULTS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
