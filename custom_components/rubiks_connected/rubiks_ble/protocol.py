"""
Rubik's Connected BLE protocol decoder.

Transport: Nordic UART Service (NUS)
  Notify:  6e400003-b5a3-f393-e0a9-e50e24dcca9e  (cube → host)
  Write:   6e400002-b5a3-f393-e0a9-e50e24dcca9e  (host → cube)

Notification packet format (cube → host):
  [0x2a] [type] [sub-type] [payload...] [checksum] [0x0d] [0x0a]
  checksum = sum of all bytes before the checksum field, masked to 8 bits.

Known notification types (byte[1], byte[2]):
  0x06 0x01  Move event  (8 bytes total)
  0x05 0x06  State toggle (7 bytes total) — motion detected? TBD
  0x05 0x05  Battery level (7 bytes total)

Move event layout:
  byte[0] = 0x2a  start
  byte[1] = 0x06  type
  byte[2] = 0x01  sub-type (constant)
  byte[3] = face_id  0-11 (see FACE_MAP)
  byte[4] = angle_code  0/3/6/9  → absolute face angle = code × 30°
  byte[5] = checksum
  byte[6] = 0x0d
  byte[7] = 0x0a

Battery response layout:
  byte[0] = 0x2a  start
  byte[1] = 0x05  type
  byte[2] = 0x05  sub-type
  byte[3] = battery percentage (0-100)
  byte[4] = checksum
  byte[5] = 0x0d
  byte[6] = 0x0a

Battery request (host → cube):
  Single byte: 0x32  written to the NUS write characteristic.

Face-ID mapping (calibrated with White-up / Green-front orientation):
  Even IDs = clockwise, odd IDs = counter-clockwise.
  Pairs map to colors: (0,1)=Blue, (2,3)=Green, (4,5)=White,
                       (6,7)=Yellow, (8,9)=Red, (10,11)=Orange
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
WRITE_UUID  = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"

MSG_MOVE    = 0x06
MSG_STATE   = 0x05
SUB_MOVE    = 0x01
SUB_BATTERY = 0x05
SUB_TOGGLE  = 0x06

BATTERY_REQUEST = bytes([0x32])  # single byte written to WRITE_UUID


class Face(str, Enum):
    WHITE  = "white"
    YELLOW = "yellow"
    GREEN  = "green"
    BLUE   = "blue"
    RED    = "red"
    ORANGE = "orange"


class Direction(str, Enum):
    CW  = "cw"
    CCW = "ccw"


# face_id → (Face color, Direction)
# Calibrated: White=Up, Green=Front, Red=Right, Orange=Left, Blue=Back, Yellow=Down
FACE_MAP: dict[int, tuple[Face, Direction]] = {
    0:  (Face.BLUE,   Direction.CW),
    1:  (Face.BLUE,   Direction.CCW),
    2:  (Face.GREEN,  Direction.CW),
    3:  (Face.GREEN,  Direction.CCW),
    4:  (Face.WHITE,  Direction.CW),
    5:  (Face.WHITE,  Direction.CCW),
    6:  (Face.YELLOW, Direction.CW),
    7:  (Face.YELLOW, Direction.CCW),
    8:  (Face.RED,    Direction.CW),
    9:  (Face.RED,    Direction.CCW),
    10: (Face.ORANGE, Direction.CW),
    11: (Face.ORANGE, Direction.CCW),
}


@dataclass(frozen=True)
class MoveEvent:
    face: Face
    direction: Direction
    angle: int      # absolute face-layer angle in degrees: 0, 90, 180, or 270
    face_id: int    # raw protocol value, for debugging

    def __str__(self) -> str:
        arrow = "↻" if self.direction == Direction.CW else "↺"
        return f"{self.face.value} {arrow} ({self.angle}°)"


@dataclass(frozen=True)
class BatteryEvent:
    level: int      # 0-100 percent

    def __str__(self) -> str:
        return f"battery={self.level}%"


@dataclass(frozen=True)
class StateEvent:
    value: int      # 0 or 1 — exact meaning TBD

    def __str__(self) -> str:
        return f"state={self.value}"


def _checksum_ok(data: bytes | bytearray) -> bool:
    return (sum(data[:-3]) & 0xFF) == data[-3]


def decode(data: bytes | bytearray) -> MoveEvent | BatteryEvent | StateEvent | None:
    """Decode a raw notification payload. Returns None for unrecognised packets."""
    if len(data) < 5 or data[0] != 0x2a:
        return None

    msg_type = data[1]
    sub_type = data[2]

    if msg_type == MSG_MOVE and sub_type == SUB_MOVE and len(data) == 8:
        if not _checksum_ok(data):
            return None
        face_id = data[3]
        angle   = data[4] * 30
        if face_id not in FACE_MAP:
            return None
        face, direction = FACE_MAP[face_id]
        return MoveEvent(face=face, direction=direction, angle=angle, face_id=face_id)

    if msg_type == MSG_STATE and len(data) == 7:
        if not _checksum_ok(data):
            return None
        if sub_type == SUB_BATTERY:
            return BatteryEvent(level=data[3])
        return StateEvent(value=data[3])

    return None
