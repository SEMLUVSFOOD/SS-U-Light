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


def _cand(proto: str, label: str, repeats: int = 8, **params) -> Dict:
    """Make a candidate with a stable, readable id like 'ev1527-a0-d1-t350'."""
    parts = []
    for k, v in sorted(params.items()):
        parts.append(_ABBR.get(k, k) + (f"{v:x}" if k == "address" else str(v)))
    return {"id": "-".join([proto] + parts), "proto": proto, "params": params,
            "label": label, "repeats": repeats}


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
}


def build_plan(name: str, ctx: Optional[Dict] = None) -> List[Dict]:
    ctx = ctx or {}
    if name not in PLANS:
        raise KeyError(name)
    return PLANS[name]["build"](ctx)


def candidate_to_train(c: Dict):
    return encoders.build(c["proto"], **c["params"])
