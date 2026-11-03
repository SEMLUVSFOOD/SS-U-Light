"""
Encoders for the cheap 433 MHz remote-chip families most likely to be inside
(or compatible with) the U-Light's FT60E12x firmware.

All of these use the same idea: a base time unit T, and every bit is a short
and a long piece (1T + 3T). Only the framing differs. Timings below are the
datasheet ratios; real-world T varies a lot between remotes (~200–500 us),
which is exactly what discovery sweeps.

          bit "0"            bit "1"            sync (sent BEFORE each word)
EV1527:   ▔|___ (T,3T)       ▔▔▔|_ (3T,T)       ▔|_______…  (T, 31T)
PT2262:   each tri-state "bit" is TWO EV1527-style bits:
          '0' = 0,0  '1' = 1,1  'F' (float) = 0,1          sync (T, 31T) AFTER word
HS2303:   EV1527-compatible "learning code" chip; some batches use a longer
          sync. We model it as EV1527 framing with a selectable sync length.
PWM-1:2:  generic custom firmware guess: 0=(T,2T) 1=(2T,T), sync (T, 24T).

If the U-Light firmware uses something else entirely, a real capture
(see tx/capture_import.py) is the way forward.
"""

from __future__ import annotations

from .pulses import PulseTrain, normalize


def _pwm_bit(bit: str, t: int, short: int = 1, long: int = 3, invert: bool = False) -> PulseTrain:
    """One PWM bit: '0' -> short high + long low, '1' -> long high + short low."""
    if (bit == "1") ^ invert:
        return [(1, long * t), (0, short * t)]
    return [(1, short * t), (0, long * t)]


def bits_from_int(value: int, width: int) -> str:
    return format(value & ((1 << width) - 1), f"0{width}b")


def ev1527(address: int, data: int, t_us: int = 350, addr_bits: int = 20,
           data_bits: int = 4, sync_units: int = 31, invert: bool = False) -> PulseTrain:
    """
    EV1527 / RT1527 / HS1527 learning-code frame:
        [sync] + address (MSB first, 20 bits) + data (4 bits, one per button).
    Returns ONE frame; rpitx repeats it.
    """
    bits = bits_from_int(address, addr_bits) + bits_from_int(data, data_bits)
    train: PulseTrain = [(1, t_us), (0, sync_units * t_us)]
    for b in bits:
        train += _pwm_bit(b, t_us, invert=invert)
    return normalize(train)


def pt2262(trits: str, t_us: int = 350, sync_units: int = 31) -> PulseTrain:
    """
    PT2262 / PT2260 / SC2262 fixed-code frame. `trits` is a string of
    '0' '1' 'F', usually 12 long (PT2262) — PT2260 variants are shorter on
    address and use the remaining positions as data. Sync follows the word.
    (Datasheet: α = osc period, short = 4α = our T, long = 12α = 3T.)
    """
    pairs = {"0": "00", "1": "11", "F": "01"}
    train: PulseTrain = []
    for trit in trits.upper():
        if trit not in pairs:
            raise ValueError(f"PT2262 trit must be 0/1/F, got {trit!r}")
        for b in pairs[trit]:
            train += _pwm_bit(b, t_us)
    train += [(1, t_us), (0, sync_units * t_us)]
    return normalize(train)


def hs2303(address: int, data: int, t_us: int = 400, sync_units: int = 36) -> PulseTrain:
    """HS2303-style: EV1527 bit shape with a slightly longer sync gap."""
    return ev1527(address, data, t_us=t_us, sync_units=sync_units)


def pwm12(bits: str, t_us: int = 400, sync_units: int = 24) -> PulseTrain:
    """Generic 1:2 duty PWM, for custom firmware that isn't a 1527 clone."""
    train: PulseTrain = [(1, t_us), (0, sync_units * t_us)]
    for b in bits:
        train += _pwm_bit(b, t_us, short=1, long=2)
    return normalize(train)


def tone(duration_us: int = 200_000) -> PulseTrain:
    """Plain carrier — the smoke test. Not a code; just proves RF is coming out."""
    return [(1, duration_us)]


# Registry used by the web API / CLI so a candidate can be rebuilt from JSON.
def build(proto: str, **p) -> PulseTrain:
    proto = proto.lower()
    if proto == "ev1527":
        return ev1527(int(p["address"]), int(p["data"]), int(p.get("t_us", 350)),
                      sync_units=int(p.get("sync_units", 31)),
                      invert=bool(p.get("invert", False)))
    if proto in ("pt2262", "pt2260"):
        return pt2262(str(p["trits"]), int(p.get("t_us", 350)), int(p.get("sync_units", 31)))
    if proto == "hs2303":
        return hs2303(int(p["address"]), int(p["data"]), int(p.get("t_us", 400)),
                      int(p.get("sync_units", 36)))
    if proto == "pwm12":
        return pwm12(str(p["bits"]), int(p.get("t_us", 400)), int(p.get("sync_units", 24)))
    if proto == "raw":
        # [[level, us], ...] — e.g. from an imported capture
        return normalize((int(l), int(u)) for l, u in p["pulses"])
    if proto == "tone":
        return tone(int(p.get("duration_us", 200_000)))
    raise ValueError(f"unknown protocol {proto!r}")
