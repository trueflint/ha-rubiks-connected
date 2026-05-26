"""
Rubik's Connected BLE protocol decoder.

Transport: Nordic UART Service (NUS)
  Notify:  6e400003-b5a3-f393-e0a9-e50e24dcca9e  (cube → host)
  Write:   6e400002-b5a3-f393-e0a9-e50e24dcca9e  (host → cube)

Notification packet format (cube → host):
  [0x2a] [type] [sub-type] [payload...] [checksum] [0x0d] [0x0a]
  checksum = sum of all bytes before the checksum field, masked to 8 bits.

Known notification types (byte[1], byte[2]):
  0x06 0x01  Move event       (8 bytes total)
  0x05 0x05  Battery level    (7 bytes total)
  0x05 0x06  Motion flag      (7 bytes total) — fires on physical movement; meaning of payload TBD
  0x05 0x08  Feature flags    (7 bytes total) — static bitmask 0xee (0b11101110); bits 0 and 4 unset
  0x05 0x09  Status register  (7 bytes total) — payload 0x01
  0x40 0x02  Cube state       (66 bytes total) — 54-byte facelet array

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

Cube state layout:
  byte[0]    = 0x2a  start
  byte[1]    = 0x40  type
  byte[2]    = 0x02  sub-type
  byte[3:57] = facelets (54 bytes): face 0-5 × 9 stickers, value = face index (0-5)
               solved when facelets[i] == i // 9 for all i
  byte[57:63]= padding (6 zero bytes)
  byte[63]   = checksum
  byte[64:66]= 0x0d 0x0a

Request commands (host → cube, single byte unless noted):
  0x32  Battery level request
  0x33  Cube state read (current tracked state)
  0x35  Calibrate (set tracking to solved) + returns solved reference cube state
  0x39  Total play time → ASCII "H#MM#SS"
  0x4e  IMU diagnostic  → ASCII "IMU_PASS"
  0x55  Handshake       → ASCII "HANDSHAKE"; must be sent on connect to enable move events
  0x56  Feature flags read → type=0x05 sub=0x08, payload=0xee (static; not orientation-dependent)
  0x58  Status register #9 read → type=0x05 sub=0x09, payload=0x01
  0x59  Status register #8 read → type=0x05 sub=0x08, payload=0x01

  Dangerous commands (do not send):
  0x31  Deep sleep (requires physical button or charger to recover)
  0x34  Immediate disconnect
  0x36  Immediate disconnect
  0x51  Enter stats session (pauses move reporting until 0x53 sent)
  0x53  End stats session → ASCII "TEST_FINISHED", then disconnects
  0x54  Disconnects
  0x78  Disconnects

IMU note:
  The cube contains an IMU (confirmed by 0x4e → "IMU_PASS" diagnostic).
  Raw accelerometer/gyro data is NOT exposed over BLE — no unsolicited pushes
  and no known poll command returns orientation data. The IMU is used internally
  for face-layer angle detection only.

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
SUB_MOVE       = 0x01
SUB_BATTERY    = 0x05
SUB_MOTION     = 0x06  # unsolicited; fires on physical movement
SUB_FLAGS      = 0x08  # feature-flags bitmask (0xee); response to 0x56 and 0x59
SUB_STATUS9    = 0x09  # status register #9 (0x01); response to 0x58

BATTERY_REQUEST   = bytes([0x32])  # single byte written to WRITE_UUID
HANDSHAKE_REQUEST = bytes([0x55])  # cube responds with b"HANDSHAKE"; enables move reporting
STATE_REQUEST     = bytes([0x33])  # read current tracked cube state
CALIBRATE_REQUEST = bytes([0x35])  # set tracking to solved; also returns solved reference state

MSG_CUBE_STATE = 0x40
SUB_CUBE_STATE = 0x02


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


@dataclass(frozen=True)
class CubeStateEvent:
    is_solved: bool

    def __str__(self) -> str:
        return "solved" if self.is_solved else "scrambled"


def _checksum_ok(data: bytes | bytearray) -> bool:
    return (sum(data[:-3]) & 0xFF) == data[-3]


def decode(data: bytes | bytearray) -> MoveEvent | BatteryEvent | StateEvent | CubeStateEvent | None:
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

    if msg_type == MSG_CUBE_STATE and sub_type == SUB_CUBE_STATE and len(data) == 66:
        if not _checksum_ok(data):
            return None
        facelets = data[3:57]
        is_solved = all(facelets[i] == i // 9 for i in range(54))
        return CubeStateEvent(is_solved=is_solved)

    return None
