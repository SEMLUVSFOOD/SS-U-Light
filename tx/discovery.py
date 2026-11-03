"""
Protocol discovery: generate labelled *candidates* to fire at a stick while you
watch it. We can't listen with a bare Pi, so this is a guided guessing game —
EXPERIMENTAL, and it may never hit a truly custom format.

A candidate is plain JSON so it can be logged to codes.json and replayed:
    {"id": "ev1527-t350-a00000-d1", "proto": "ev1527",
     "params": {"address": 0, "data": 1, "t_us": 350}, "label": "...", "repeats": 8}

Strategy notes (why these sweeps):
  * 1527-style receivers usually accept only the address they were paired with.
    Many cheap toys/lights instead accept a fixed "broadcast" address, or LEARN
    the first address heard shortly after power-on. So we try (a) a handful of
    "lazy factory default" addresses and (b) a learn-mode sweep with our own
    random address right after you power the stick on.
  * The 4 data bits are typically "which button" -> colour/effect, so for each
    address/timing we walk data 1..15 (0 is often unused).
  * Timing tolerance on these receivers is usually ±20–30 %, so a coarse T grid
    (250…500 us) covers most real remotes.
"""

from __future__ import annotations

import random
from typing import Dict, Iterable, List, Optional

from . import encoders

T_GRID = [250, 300, 350, 400, 450, 500]
DEFAULT_ADDRESSES = [0x00000, 0xFFFFF, 0xAAAAA, 0x55555, 0x12345, 0x00001]
DATA_ALL = list(range(1, 16))

# PT2262: 8 address trits + 4 data bits. Common factory DIP settings are all-float
# or all-zero; data positions are '0'/'1' per button.
PT_ADDRESSES = ["FFFFFFFF", "00000000", "11111111", "0F0F0F0F"]
PT_DATA = ["1000", "0100", "0010", "0001", "1100", "0011", "1111"]


_ABBR = {"address": "a", "data": "d", "t_us": "t", "trits": "k", "bits": "b"}


def _cand(proto: str, label: str, repeats: int = 8, freq_hz: Optional[int] = None, **params) -> Dict:
    """Make a candidate with a stable, readable id like 'ev1527-a0-d1-t350'."""
    parts = []
    for k, v in sorted(params.items()):
        parts.append(_ABBR.get(k, k) + (f"{v:x}" if k == "address" else str(v)))
    c = {"id": "-".join([proto] + parts), "proto": proto, "params": params,
         "label": label, "repeats": repeats}
    if freq_hz is not None:
        c["id"] += f"-f{freq_hz // 1000}"
        c["freq_hz"] = freq_hz
    return c


def ev1527_sweep(t_list: Iterable[int] = T_GRID, addresses: Iterable[int] = DEFAULT_ADDRESSES,
                 data_list: Iterable[int] = DATA_ALL, proto: str = "ev1527") -> List[Dict]:
    out = []
    for a in addresses:
        for t in t_list:
            for d in data_list:
                out.append(_cand(proto, f"{proto.upper()} T={t}µs addr=0x{a:05X} data={d:04b}",
                                 address=a, data=d, t_us=t))
    return out


def pt2262_sweep(t_list: Iterable[int] = T_GRID, addresses: Iterable[str] = PT_ADDRESSES,
                 data_list: Iterable[str] = PT_DATA) -> List[Dict]:
    out = []
    for a in addresses:
        for t in t_list:
            for d in data_list:
                out.append(_cand("pt2262", f"PT2262 T={t}µs addr={a} data={d}",
                                 trits=a + d, t_us=t))
    return out


def learn_sweep(my_address: int, t_list: Iterable[int] = (350, 300, 400)) -> List[Dict]:
    """Power-cycle the stick, then fire these immediately (pairing-window guess)."""
    out = []
    for t in t_list:
        for d in DATA_ALL:
            c = _cand("ev1527", f"LEARN EV1527 T={t}µs addr=0x{my_address:05X} data={d:04b}",
                      repeats=12, address=my_address, data=d, t_us=t)
            out.append(c)
    return out


def new_learn_address() -> int:
    """Random 20-bit address that's unlikely to collide with anyone else's remote."""
    return random.SystemRandom().randrange(0x10000, 0xFFFFF)


# --- wider sweeps (option 4): long shots when the common formats miss ---

# Small offsets around 433.92. The CMT2220LS crystal (13.52127 MHz) sets the
# receiver centre, and cheap crystals drift; a receiver with a narrow IF can
# ignore us if we're a bit off. All stay inside the 433 MHz ISM band.
FREQ_OFFSETS_HZ = [433_820_000, 433_870_000, 433_920_000, 433_970_000, 434_020_000]

# Wider timing grid: some toy encoders run faster/slower than the usual remotes.
T_GRID_WIDE = [150, 200, 250, 300, 350, 400, 450, 500, 600, 750]


def freq_sweep(t_list: Iterable[int] = (250, 350, 450),
               data_list: Iterable[int] = (1, 2, 4, 8),
               freqs: Iterable[int] = FREQ_OFFSETS_HZ) -> List[Dict]:
    """Same EV1527 guesses (addr 0), repeated across a few nearby frequencies."""
    out = []
    for f in freqs:
        for t in t_list:
            for d in data_list:
                out.append(_cand("ev1527",
                                 f"EV1527 {f/1e6:.3f}MHz T={t}µs data={d:04b}",
                                 freq_hz=f, address=0, data=d, t_us=t))
    return out


def wide_timing_sweep(addresses: Iterable[int] = (0x00000, 0xFFFFF, 0xAAAAA)) -> List[Dict]:
    """The wide T grid, more repeats, both normal and inverted bit polarity."""
    out = []
    for inv in (False, True):
        for a in addresses:
            for t in T_GRID_WIDE:
                for d in (1, 2, 4, 8):
                    tag = "inv " if inv else ""
                    out.append(_cand("ev1527",
                                     f"{tag}EV1527 T={t}µs addr=0x{a:05X} data={d:04b}",
                                     repeats=10, address=a, data=d, t_us=t, invert=inv))
    return out


def shapes_sweep() -> List[Dict]:
    """Other frame shapes: generic 1:2 PWM, and 24-bit EV1527 (12-bit addr + 12-bit data)."""
    out = []
    # generic 1:2 duty PWM, a few word lengths of all-ones-ish payloads
    for t in (250, 350, 450):
        for bits in ("000000000001", "000000000011", "101010101010", "111111111111",
                     "000000000000000000000001", "000000000000000000001111"):
            out.append(_cand("pwm12", f"PWM1:2 T={t}µs bits={bits}", t_us=t, bits=bits))
    # EV1527 with a wider data field (some chips map colour across more bits)
    for t in (300, 400):
        for d in (0x001, 0x002, 0x004, 0x008, 0x010, 0x020, 0x040, 0x080, 0x100, 0xFFF):
            out.append(_cand("ev1527", f"EV1527-24 T={t}µs data=0x{d:03X}",
                             address=0, data=d, t_us=t, data_bits=12, addr_bits=12))
    return out


PLANS = {
    "timing": {
        "title": "Timing scan",
        "blurb": "Address 0, the four single-button codes (0001/0010/0100/1000), every timing. Quick first pass: ~40 s.",
        "build": lambda ctx: ev1527_sweep(addresses=[0], data_list=[1, 2, 4, 8])[:24],
    },
    "ev1527": {
        "title": "EV1527 defaults",
        "blurb": "Factory-default style addresses × all timings × all 15 buttons. Long (~10 min).",
        "build": lambda ctx: ev1527_sweep(),
    },
    "pt2262": {
        "title": "PT2262 / PT2260",
        "blurb": "Tri-state fixed codes with common DIP-switch settings.",
        "build": lambda ctx: pt2262_sweep(),
    },
    "hs2303": {
        "title": "HS2303-style",
        "blurb": "1527 bits with a longer sync gap.",
        "build": lambda ctx: ev1527_sweep(t_list=[350, 400, 450], proto="hs2303"),
    },
    "learn": {
        "title": "Learn mode",
        "blurb": "Turn the stick OFF, hit Start, switch it ON straight away. Sends YOUR address.",
        "build": lambda ctx: learn_sweep(ctx["my_address"]),
    },
    "freq": {
        "title": "Frequency sweep",
        "blurb": "Long shot: the same code across 433.82–434.02 MHz, in case the receiver is detuned.",
        "build": lambda ctx: freq_sweep(),
    },
    "wide": {
        "title": "Wide timing",
        "blurb": "Fast and slow timings (150–750 µs), more repeats, normal + inverted bits. Long (~15 min).",
        "build": lambda ctx: wide_timing_sweep(),
    },
    "shapes": {
        "title": "Other shapes",
        "blurb": "Different frame shapes: generic 1:2 PWM and 24-bit EV1527 words.",
        "build": lambda ctx: shapes_sweep(),
    },
}


def build_plan(name: str, ctx: Optional[Dict] = None) -> List[Dict]:
    ctx = ctx or {}
    if name not in PLANS:
        raise KeyError(name)
    return PLANS[name]["build"](ctx)


def candidate_to_train(c: Dict):
    return encoders.build(c["proto"], **c["params"])
