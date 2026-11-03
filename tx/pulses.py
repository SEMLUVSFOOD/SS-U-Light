"""
Pulse trains — the one data type everything in tx/ speaks.

A *pulse train* is a list of (level, duration_us) tuples:
    level 1 = carrier ON  (433.92 MHz radiated)
    level 0 = carrier OFF (silence)

Encoders build pulse trains, discovery labels them, the importer parses them
from captures, and rpitx.py turns them into a sendook call. Keeping a single
representation means "what the stick reacted to" is always reproducible.
"""

from __future__ import annotations

import struct
from typing import Iterable, List, Tuple

Pulse = Tuple[int, int]          # (level 0/1, duration in microseconds)
PulseTrain = List[Pulse]

# sendook refuses anything shorter than 10 us (librpitx limitation).
MIN_US = 10


def normalize(train: Iterable[Pulse]) -> PulseTrain:
    """Merge neighbouring pulses with the same level and drop zero-length ones."""
    out: PulseTrain = []
    for level, us in train:
        level = 1 if level else 0
        us = int(round(us))
        if us <= 0:
            continue
        if out and out[-1][0] == level:
            out[-1] = (level, out[-1][1] + us)
        else:
            out.append((level, us))
    return out


def total_us(train: Iterable[Pulse]) -> int:
    return sum(us for _, us in train)


def on_time_us(train: Iterable[Pulse]) -> int:
    """How long the carrier is actually ON — used for the duty-cycle guard."""
    return sum(us for level, us in train if level)


def to_sendook_file(train: Iterable[Pulse]) -> bytes:
    """
    Serialise for `sendook -i <file>` (file mode).

    Verified against rpitx src/ook/sendook.cpp: the file is a flat array of
        struct Bitdata { double active; uint32_t duration /* ns */; uint32_t padding; }
    = 16 bytes per entry, little-endian on the Pi. Duration is in NANOseconds.
    """
    blob = bytearray()
    for level, us in normalize(train):
        if us < MIN_US:
            raise ValueError(f"pulse of {us}us is shorter than sendook's {MIN_US}us minimum")
        blob += struct.pack("<dII", float(level), us * 1000, 0)
    return bytes(blob)


def to_chip_string(train: Iterable[Pulse], chip_us: int) -> str:
    """
    Fallback representation for sendook's plain string mode:
    `sendook -0 <chip> -1 <chip> 111000...` where every char is one chip.
    Every duration must be a whole number of chips. Only used if file mode
    misbehaves on real hardware.
    """
    chars = []
    for level, us in normalize(train):
        n, rem = divmod(us, chip_us)
        if rem:
            raise ValueError(f"{us}us is not a multiple of chip {chip_us}us")
        chars.append(("1" if level else "0") * n)
    return "".join(chars)


def describe(train: Iterable[Pulse], limit: int = 16) -> str:
    """Short human-readable form, e.g. '+350 -1050 +1050 -350 …' (rtl_433 style)."""
    parts = [("+" if lvl else "-") + str(us) for lvl, us in train]
    more = f" … ({len(parts)} pulses)" if len(parts) > limit else ""
    return " ".join(parts[:limit]) + more
