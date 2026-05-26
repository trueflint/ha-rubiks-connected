#!/usr/bin/env python3
"""
Attempt to set the cube's internal state to "solved".
The cube must be physically solved before running this.

Tries several approaches and queries state (0x33) before and after each.

Usage:
    python3 dev/set_solved.py <ADDRESS>
"""

import asyncio
import re
import sys

from bleak import BleakClient

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

SOLVED_FACELETS = bytes(face for face in range(6) for _ in range(9))  # 54 bytes
SOLVED_PADDING  = bytes(6)

def _state_packet(sub: int) -> bytes:
    body = bytes([0x2a, 0x40, sub]) + SOLVED_FACELETS + SOLVED_PADDING
    return body + bytes([sum(body) & 0xFF, 0x0d, 0x0a])

def _describe_state(data: bytes) -> str:
    if len(data) < 57 or data[0] != 0x2a or data[1] != 0x40:
        return None
    facelets = data[3:57]
    solved = all(facelets[i] == i // 9 for i in range(54))
    if solved:
        return "SOLVED"
    faces = [set(facelets[f*9:(f+1)*9]) for f in range(6)]
    return "SCRAMBLED  face sets: " + " | ".join(str(sorted(f)) for f in faces)


async def query_state(client, responses, cmds=(0x33, 0x35)) -> dict:
    result = {}
    for cmd in cmds:
        responses.clear()
        await client.write_gatt_char(WRITE_UUID, bytes([cmd]), response=False)
        await asyncio.sleep(0.6)
        desc = "(no response)"
        for r in responses:
            d = _describe_state(bytes(r))
            if d:
                desc = d
                break
        result[f"0x{cmd:02x}"] = desc
    return result


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target = sys.argv[1]
    from bleak import BleakScanner
    print(f"Scanning for '{target}' ...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, _: (d.name and target.lower() in d.name.lower())
            or d.address.lower() == target.lower(),
        timeout=15,
    )
    if not device:
        print("Device not found — is the cube awake and advertising?")
        print("Try turning a face to wake it, then run again.")
        sys.exit(1)
    print(f"Found: {device.name} ({device.address})")

    responses = []

    try:
        async with BleakClient(device) as client:
            await client.start_notify(NOTIFY_UUID, lambda _, d: responses.append(bytes(d)))
            await asyncio.sleep(0.5)
            await client.write_gatt_char(WRITE_UUID, bytes([0x55]), response=False)
            await asyncio.sleep(0.5)

            print("Connected. PUT THE CUBE DOWN and do not touch it.")
            print("Waiting 5 seconds to settle ...")
            await asyncio.sleep(5.0)
            responses.clear()

            # Baseline using only 0x33 — never send 0x35 before the candidate
            baseline = await query_state(client, responses, cmds=(0x33,))
            print("Baseline (0x33 only):")
            for cmd, desc in baseline.items():
                print(f"  {cmd}: {desc}")

            if "SCRAMBLED" not in str(baseline):
                print("\nBaseline already SOLVED — scramble the cube and try again.")
            else:
                label = sys.argv[2] if len(sys.argv) > 2 else "0x35"
                candidate = bytes([int(sys.argv[2], 16)]) if len(sys.argv) > 2 else bytes([0x35])

                loop = asyncio.get_event_loop()

                # Step 1: send calibration command
                print(f"\nStep 1 — sending calibration command: {label}")
                responses.clear()
                await client.write_gatt_char(WRITE_UUID, candidate, response=False)
                await asyncio.sleep(1.5)
                resp_hex = " | ".join(bytes(r).hex(" ") for r in responses) or "(none)"
                state = await query_state(client, responses, cmds=(0x33,))
                print(f"  response:    {resp_hex}")
                print(f"  0x33 after:  {state['0x33']}")
                if "SOLVED" not in state["0x33"]:
                    print("  FAIL — cube did not report SOLVED after calibration command.")
                else:
                    print("  PASS — cube reports SOLVED.")

                # Step 2: scramble and verify SCRAMBLED
                await loop.run_in_executor(None, input,
                    "\nStep 2 — scramble the cube, then press Enter ...")
                await asyncio.sleep(1.0)
                state2 = await query_state(client, responses, cmds=(0x33,))
                print(f"  0x33 after scramble: {state2['0x33']}")
                if "SCRAMBLED" not in state2["0x33"]:
                    print("  FAIL — cube still reports SOLVED (tracking may be broken).")
                else:
                    print("  PASS — cube reports SCRAMBLED.")

                # Step 3: solve and verify SOLVED
                await loop.run_in_executor(None, input,
                    "\nStep 3 — solve the cube, then press Enter ...")
                await asyncio.sleep(1.0)
                state3 = await query_state(client, responses, cmds=(0x33,))
                print(f"  0x33 after solve:    {state3['0x33']}")
                if "SOLVED" not in state3["0x33"]:
                    print("  FAIL — cube did not return to SOLVED.")
                else:
                    print("  PASS — cube reports SOLVED again. Round-trip confirmed!")

    except TimeoutError:
        print("Connection timed out — cube may have gone back to sleep. Try scanning and running again.")
        sys.exit(1)
    except Exception as e:
        print(f"Connection error: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
