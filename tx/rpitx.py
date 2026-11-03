"""
The ONE place that touches the radio.

Everything else hands us a pulse train; we write it to a temp file and call
    sudo sendook -i -f <freq> -r <repeats> -p <pause_us> <file>
(syntax verified against rpitx src/ook/sendook.cpp @ ee7ff57, Sept 2024).

If sendook misbehaves on the Zero 2 W, fix it HERE — e.g. switch
SEND_MODE to "string" to use the plain `-0/-1` chip-string mode instead.

Safety guards (keep them!):
  * frequency locked to the 433.05–434.79 MHz ISM band
  * max on-air time per call and a minimum gap between calls
  * MOCK mode (default off-Pi) just logs the command
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from .pulses import PulseTrain, describe, normalize, on_time_us, to_chip_string, to_sendook_file, total_us

DEFAULT_FREQ_HZ = 433_920_000          # X1 13.52127 MHz on the CMT2220LS -> 433.92 MHz
ISM_LOW_HZ, ISM_HIGH_HZ = 433_050_000, 434_790_000

MAX_AIR_MS = 1500        # longest single transmission we allow (all repeats together)
MIN_GAP_MS = 120         # minimum silence between two transmissions
MAX_REPEATS = 20

SEND_MODE = os.environ.get("ULIGHT_SEND_MODE", "file")   # "file" (exact timings) or "string"
SENDOOK = os.environ.get("ULIGHT_SENDOOK", "sendook")
TUNE = os.environ.get("ULIGHT_TUNE", "tune")


def is_mock() -> bool:
    """Mock unless explicitly told to transmit AND sendook exists."""
    if os.environ.get("ULIGHT_MOCK", "").lower() in ("1", "true", "yes"):
        return True
    if os.environ.get("ULIGHT_MOCK", "").lower() in ("0", "false", "no"):
        return False
    return shutil.which(SENDOOK) is None


@dataclass
class TxResult:
    ok: bool
    mock: bool
    command: List[str]
    air_ms: float
    summary: str
    output: str = ""
    error: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self):
        return self.__dict__.copy()


_lock = threading.Lock()          # one transmission at a time
_last_end = 0.0
history: List[TxResult] = []      # recent TX log shown in the dashboard


def _remember(res: TxResult) -> TxResult:
    history.append(res)
    del history[:-50]
    log_path = os.environ.get("ULIGHT_TX_LOG")
    if log_path:
        with open(log_path, "a") as f:
            f.write(json.dumps(res.to_dict()) + "\n")
    return res


def send_pulses(train: PulseTrain, repeats: int = 8, pause_us: int = 0,
                freq_hz: int = DEFAULT_FREQ_HZ, label: str = "") -> TxResult:
    """
    Transmit `train` `repeats` times. For 1527-style codes the sync gap is part
    of the frame, so pause_us can stay 0 (sendook needs >=1, we clamp).
    """
    global _last_end
    train = normalize(train)
    if not train:
        raise ValueError("empty pulse train")
    if not (ISM_LOW_HZ <= freq_hz <= ISM_HIGH_HZ):
        raise ValueError("frequency outside the 433 MHz ISM band — refusing to transmit")
    repeats = max(1, min(int(repeats), MAX_REPEATS))
    pause_us = max(1, int(pause_us))
    air_ms = (total_us(train) * repeats + pause_us * (repeats - 1)) / 1000
    if air_ms > MAX_AIR_MS:
        raise ValueError(f"burst would be {air_ms:.0f} ms on air (limit {MAX_AIR_MS} ms)")

    summary = f"{label or 'burst'} ×{repeats} · {describe(train, 8)} · on {on_time_us(train)/1000:.1f}ms/frame"

    with _lock:
        wait = MIN_GAP_MS / 1000 - (time.time() - _last_end)
        if wait > 0:
            time.sleep(wait)

        tmp = None
        if SEND_MODE == "string":
            chip = _gcd_all(us for _, us in train)
            cmd = ["sudo", "-n", SENDOOK, "-f", str(freq_hz), "-0", str(chip), "-1", str(chip),
                   "-r", str(repeats), "-p", str(pause_us), to_chip_string(train, chip)]
        else:
            tmp = tempfile.NamedTemporaryFile(prefix="ulight-", suffix=".ook", delete=False)
            tmp.write(to_sendook_file(train))
            tmp.close()
            cmd = ["sudo", "-n", SENDOOK, "-i", "-f", str(freq_hz),
                   "-r", str(repeats), "-p", str(pause_us), tmp.name]

        try:
            if is_mock():
                time.sleep(min(air_ms, 400) / 1000)  # feel roughly like the real thing
                res = TxResult(True, True, cmd, air_ms, summary, output="[mock] not transmitted")
            else:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                res = TxResult(p.returncode == 0, False, cmd, air_ms, summary,
                               output=p.stdout[-500:], error=p.stderr[-500:])
        except Exception as e:  # noqa: BLE001 — surface any failure in the UI
            res = TxResult(False, is_mock(), cmd, air_ms, summary, error=str(e))
        finally:
            if tmp:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
            _last_end = time.time()
    return _remember(res)


def smoke_tone(seconds: float = 1.0, freq_hz: int = DEFAULT_FREQ_HZ) -> TxResult:
    """
    Phase-1 smoke test: unmodulated carrier via rpitx `tune`, killed after
    `seconds`. Check it with any SDR / Flipper / a cheap 433 receiver nearby.
    """
    seconds = max(0.2, min(seconds, 3.0))
    if not (ISM_LOW_HZ <= freq_hz <= ISM_HIGH_HZ):
        raise ValueError("frequency outside ISM band")
    # tune runs until interrupted; sudo relays our SIGINT to it, and tune then
    # switches the carrier off. (No `timeout` wrapper -> sudoers stays narrow.)
    cmd = ["sudo", "-n", TUNE, "-f", str(freq_hz)]
    summary = f"tone {freq_hz/1e6:.3f} MHz for {seconds:.1f}s"
    with _lock:
        if is_mock():
            res = TxResult(True, True, cmd, seconds * 1000, summary, output="[mock] not transmitted")
        else:
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                time.sleep(seconds)
                if p.poll() is None:            # still transmitting, as expected
                    p.send_signal(signal.SIGINT)
                out, errout = p.communicate(timeout=5)
                ok = p.returncode in (0, -signal.SIGINT, 130) and "sudo:" not in errout
                res = TxResult(ok, False, cmd, seconds * 1000, summary, output=out[-500:], error=errout[-500:])
            except Exception as e:  # noqa: BLE001
                res = TxResult(False, False, cmd, seconds * 1000, summary, error=str(e))
    return _remember(res)


def _gcd_all(values) -> int:
    from math import gcd
    g = 0
    for v in values:
        g = gcd(g, int(v))
    return max(g, 10)


def status() -> dict:
    return {
        "mock": is_mock(),
        "send_mode": SEND_MODE,
        "sendook": shutil.which(SENDOOK),
        "freq_hz": DEFAULT_FREQ_HZ,
        "limits": {"max_air_ms": MAX_AIR_MS, "min_gap_ms": MIN_GAP_MS, "max_repeats": MAX_REPEATS},
    }
