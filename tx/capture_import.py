"""
Import a REAL capture — the reliable route if discovery stalls.

Borrow a Flipper Zero or any RTL-SDR, stand near a working U-Light remote /
venue transmitter (or another fan's stick controller), record, then drop the
file in captures/ and run:
    python -m tx.cli import captures/myfile.sub

Supported formats
-----------------
1. Flipper Zero  .sub  (Sub-GHz app, "Read" or "Read RAW")
       Filetype: Flipper SubGhz Key File        <- decoded
       Frequency: 433920000
       Protocol: Princeton                      <- Flipper's name for PT2262/EV1527
       Bit: 24
       Key: 00 00 00 00 00 12 34 51
       TE: 350                                  <- base timing in µs
   or
       Filetype: Flipper SubGhz RAW File        <- raw
       Protocol: RAW
       RAW_Data: 350 -1050 1050 -350 ...        <- +µs carrier on, -µs off
   (RAW_Data can repeat over many lines.)

2. rtl_433  .ook  (record with `rtl_433 -f 433.92M -w capture.ook`,
   or the pulse dump from `-S unknown`), text lines:
       ;pulse data
       ;freq1 433920000
       350 1050           <- "<pulse_us> <gap_us>" pairs
       ...
       ;end

Each parser returns a list of *candidates* (same JSON shape as discovery), so a
capture can be replayed, logged and mapped to a button in the dashboard.

TODO when we have a real file: tune the frame splitter (split on gaps > 5 ms)
and add a decoder that recognises EV1527 so we can learn the address.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List

from .pulses import PulseTrain, normalize

FRAME_GAP_US = 5000   # a silence longer than this separates two frames


def _split_frames(train: PulseTrain) -> List[PulseTrain]:
    frames, cur = [], []
    for lvl, us in train:
        if lvl == 0 and us > FRAME_GAP_US and cur:
            cur.append((0, us))
            frames.append(normalize(cur))
            cur = []
        else:
            cur.append((lvl, us))
    if cur:
        frames.append(normalize(cur))
    return [f for f in frames if sum(1 for l, _ in f if l) >= 8]  # drop noise blips


def parse_flipper_sub(text: str, name: str = "capture") -> List[Dict]:
    fields: Dict[str, str] = {}
    raw: List[int] = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        if key == "RAW_Data":
            raw += [int(x) for x in val.split()]
        else:
            fields[key] = val

    freq = int(fields.get("Frequency", "433920000"))
    proto = fields.get("Protocol", "")
    if proto == "Princeton":
        bits = int(fields.get("Bit", "24"))
        key = int(fields["Key"].replace(" ", ""), 16)
        te = int(fields.get("TE", "350"))
        address, data = key >> 4, key & 0xF
        return [{
            "id": f"import-{name}-princeton", "proto": "ev1527",
            "params": {"address": address & 0xFFFFF, "data": data, "t_us": te},
            "label": f"Imported {name}: Princeton {bits}b key=0x{key:06X} TE={te}µs",
            "repeats": 8, "freq_hz": freq, "source": name,
        }]
    if proto == "RAW" or raw:
        train = normalize((1 if v > 0 else 0, abs(v)) for v in raw)
        return _frames_to_candidates(train, name, freq)
    raise ValueError(f"Unsupported Flipper protocol {proto!r} — save it with Read RAW instead")


def parse_rtl433_ook(text: str, name: str = "capture") -> List[Dict]:
    freq = 433_920_000
    train: PulseTrain = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(";"):
            m = re.match(r";freq1\s+(\d+)", line)
            if m:
                freq = int(m.group(1))
            continue
        nums = line.split()
        if len(nums) >= 2:
            train += [(1, int(nums[0])), (0, int(nums[1]))]
    return _frames_to_candidates(normalize(train), name, freq)


def _frames_to_candidates(train: PulseTrain, name: str, freq: int) -> List[Dict]:
    out = []
    for i, frame in enumerate(_split_frames(train)[:10]):
        out.append({
            "id": f"import-{name}-f{i}", "proto": "raw",
            "params": {"pulses": [list(p) for p in frame]},
            "label": f"Imported {name} frame {i} ({len(frame)} pulses)",
            "repeats": 6, "freq_hz": freq, "source": name,
        })
    return out


def import_file(path: str) -> List[Dict]:
    name = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if path.endswith(".sub") or "Flipper SubGhz" in text:
        return parse_flipper_sub(text, name)
    if path.endswith(".ook") or text.lstrip().startswith(";pulse"):
        return parse_rtl433_ook(text, name)
    raise ValueError("Unknown capture format (expected Flipper .sub or rtl_433 .ook)")
