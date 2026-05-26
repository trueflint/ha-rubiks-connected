#!/usr/bin/env python3
"""
Proper PCAP parser for nRF Sniffer link type 272
(LINKTYPE_BLUETOOTH_LE_LL_WITH_PHDR).

Correctly parses: PHDR → BLE LL → L2CAP → ATT layer.
Only shows real ATT write/notify/indicate packets, not advertising noise.

Usage:
    python dev/parse_pcap.py cube_capture.pcap
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rubiks_connected"))
from rubiks_ble.protocol import decode, MoveEvent, StateEvent

# ── PCAP structures (big-endian for this capture) ────────────────────────────
PCAP_GLOBAL = struct.Struct('>IHHiIII')   # magic vmaj vmin tz sf snap linktype
PCAP_PKT    = struct.Struct('>IIII')      # ts_sec ts_usec incl_len orig_len
# ── nRF Sniffer PHDR (10 bytes, little-endian) ───────────────────────────────
BTLE_PHDR   = struct.Struct('<BbbBIH')    # rf_ch signal noise aa_off ref_aa flags

# ── ATT opcodes ───────────────────────────────────────────────────────────────
ATT_WRITE_REQ = 0x12
ATT_WRITE_CMD = 0x52
ATT_WRITE_RSP = 0x13
ATT_NOTIFY    = 0x1b
ATT_INDICATE  = 0x1d

OPCODE_NAME = {
    ATT_WRITE_REQ: "WriteReq",
    ATT_WRITE_CMD: "WriteCmd",
    ATT_WRITE_RSP: "WriteRsp",
    ATT_NOTIFY:    "Notify  ",
    ATT_INDICATE:  "Indicate",
}


def parse(path: str) -> None:
    with open(path, "rb") as f:
        ghdr = f.read(24)
        if len(ghdr) < 24:
            print("File too short"); return
        magic, _, _, _, _, _, linktype = PCAP_GLOBAL.unpack(ghdr)
        if linktype != 272:
            print(f"Unexpected link type {linktype} (expected 272)")
            return

        print(f"Parsing {path}  (link type 272 — nRF Sniffer BLE)\n")
        print(f"{'#':>5}  {'Dir':8}  {'Op':10}  {'Hdl':6}  {'Decoded / Raw value'}")
        print("─" * 90)

        pkt_num = 0
        while True:
            raw_hdr = f.read(16)
            if len(raw_hdr) < 16:
                break
            ts_sec, ts_usec, incl_len, _ = PCAP_PKT.unpack(raw_hdr)
            raw = f.read(incl_len)
            pkt_num += 1

            if len(raw) < BTLE_PHDR.size:
                continue

            # ── Pseudo-header ─────────────────────────────────────────────────
            _, _, _, _, _, flags = BTLE_PHDR.unpack(raw[:10])
            # bit 15: 0=master→slave (phone→cube), 1=slave→master (cube→phone)
            is_from_cube = bool((flags >> 15) & 1)
            direction    = "← CUBE" if is_from_cube else "→ CUBE"

            # ── BLE LL PDU (offset 10) ────────────────────────────────────────
            pdu = raw[10:]
            if len(pdu) < 8:        # AA(4) + LL_hdr(2) + L2CAP_hdr(4) minimum
                continue

            llid   = pdu[4] & 0x03  # bits 1:0 of LL header byte 0
            ll_len = pdu[5]         # LL header byte 1 = payload length

            if llid not in (1, 2):  # must be L2CAP fragment or complete
                continue
            if len(pdu) < 6 + ll_len:
                continue

            l2cap = pdu[6 : 6 + ll_len]
            if len(l2cap) < 5:      # L2CAP hdr(4) + ATT opcode(1)
                continue

            l2cap_cid = struct.unpack_from("<H", l2cap, 2)[0]
            if l2cap_cid != 0x0004:  # not ATT
                continue

            att    = l2cap[4:]
            opcode = att[0]

            if opcode not in OPCODE_NAME:
                continue
            if len(att) < 3:
                continue

            handle = struct.unpack_from("<H", att, 1)[0]
            value  = bytes(att[3:])

            # ── Decode cube protocol if it matches ────────────────────────────
            decoded = ""
            if is_from_cube and opcode in (ATT_NOTIFY, ATT_INDICATE):
                event = decode(value)
                if isinstance(event, MoveEvent):
                    decoded = f"  ← {event}"
                elif isinstance(event, StateEvent):
                    decoded = f"  ← state={event.value}"

            name = OPCODE_NAME[opcode]
            hex_val = value.hex(" ") if value else "(empty)"
            print(f"{pkt_num:>5}  {direction}  {name}  h={handle:#06x}  {hex_val}{decoded}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python dev/parse_pcap.py <capture.pcap>")
        sys.exit(1)
    parse(sys.argv[1])
