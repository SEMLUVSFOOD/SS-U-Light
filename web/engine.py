"""
Background jobs that transmit over time: the discovery runner and the effects
player. Only one job runs at a time — starting one stops the other.
"""

from __future__ import annotations

import colorsys
import threading
import time
from typing import Dict, List, Optional

from tx import discovery, rpitx

from . import store

# The colour buttons. "rgb" is only for the on-screen preview and the colour
# picker's nearest-match; the stick's real colours depend on what we confirm.
COLORS = [
    {"id": "red", "name": "Red", "rgb": "#ff2d55"},
    {"id": "orange", "name": "Orange", "rgb": "#ff8a1f"},
    {"id": "yellow", "name": "Yellow", "rgb": "#ffe14d"},
    {"id": "green", "name": "Green", "rgb": "#3dff8c"},
    {"id": "cyan", "name": "Cyan", "rgb": "#3de8ff"},
    {"id": "blue", "name": "Blue", "rgb": "#3d6bff"},
    {"id": "purple", "name": "Purple", "rgb": "#a64dff"},
    {"id": "pink", "name": "Pink", "rgb": "#ff5fc8"},
    {"id": "white", "name": "White", "rgb": "#ffffff"},
]
OFF = {"id": "off", "name": "Off", "rgb": "#000000"}
# Effects the stick might do natively (if we find their codes) — otherwise we fake them.
NATIVE_FX = ["fx_strobe", "fx_rainbow", "fx_pulse", "fx_fade"]
ACTIONS = [c["id"] for c in COLORS] + ["off"] + NATIVE_FX


def send_candidate(c: Dict, label: Optional[str] = None) -> rpitx.TxResult:
    train = discovery.candidate_to_train(c)
    return rpitx.send_pulses(train, repeats=c.get("repeats", 8),
                             freq_hz=c.get("freq_hz", rpitx.DEFAULT_FREQ_HZ),
                             label=label or c.get("label", c.get("id", "")))


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def nearest_color(hex_rgb: str, only_confirmed: bool) -> Dict:
    """Closest palette colour by hue (with a white check for low saturation)."""
    r, g, b = (v / 255 for v in _hex_to_rgb(hex_rgb))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    confirmed = store.load()["confirmed"]
    pool = [c for c in COLORS if not only_confirmed or c["id"] in confirmed] or COLORS
    if v < 0.08:
        return OFF
    if s < 0.18:
        whites = [c for c in pool if c["id"] == "white"]
        if whites:
            return whites[0]

    def dist(c):
        ch, cs, _ = colorsys.rgb_to_hsv(*(x / 255 for x in _hex_to_rgb(c["rgb"])))
        if cs < 0.18:
            return 9  # white only via the branch above
        d = abs(ch - h)
        return min(d, 1 - d)
    return min(pool, key=dist)


class Job:
    """Base: a thread with a stop flag."""
    name = "job"

    def __init__(self):
        self._stop = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True, name=self.name)
        self.thread.start()

    def stop(self):
        self._stop.set()

    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive() and not self._stop.is_set())

    def _sleep(self, seconds: float) -> bool:
        """Interruptible sleep; returns False if we were asked to stop."""
        return not self._stop.wait(seconds)


class Discovery(Job):
    name = "discovery"

    def __init__(self, plan: str, candidates: List[Dict], dwell_ms: int, start: int = 0):
        super().__init__()
        self.plan, self.candidates, self.dwell_ms = plan, candidates, dwell_ms
        self.index = max(0, min(start, len(candidates) - 1))
        self.sent: List[int] = []       # indices in send order
        self.paused = False

    def _run(self):
        while not self._stop.is_set() and self.index < len(self.candidates):
            if self.paused:
                self._sleep(0.1)
                continue
            self.fire(self.index)
            if not self._sleep(self.dwell_ms / 1000):
                return
            if not self.paused:
                self.index += 1
        self.paused = True

    def fire(self, i: int):
        self.sent.append(i)
        del self.sent[:-20]
        send_candidate(self.candidates[i], label=f"[{i + 1}/{len(self.candidates)}] {self.candidates[i]['label']}")

    def current(self) -> Optional[Dict]:
        return self.candidates[self.sent[-1]] if self.sent else None

    def previous(self) -> Optional[Dict]:
        return self.candidates[self.sent[-2]] if len(self.sent) > 1 else None

    def state(self) -> Dict:
        return {"plan": self.plan, "index": self.index, "total": len(self.candidates),
                "paused": self.paused, "running": self.running(),
                "dwell_ms": self.dwell_ms, "current": self.current()}


class Effect(Job):
    """
    solid   – send the colour once (plus one repeat a bit later, for reliability)
    strobe  – colour / off alternating
    rainbow – step through every confirmed colour
    pulse   – colour, then off, slower and softer than strobe (no real fading:
              the stick only knows the codes we found, so "pulse" is on/off breathing)
    If the stick has a native code for the effect (fx_*), we send that instead.
    """
    name = "effect"

    def __init__(self, mode: str, color: str, speed: int):
        super().__init__()
        self.mode, self.color, self.speed = mode, color, max(1, min(10, speed))

    def interval(self) -> float:
        base = {"strobe": 0.9, "rainbow": 2.2, "pulse": 3.0}.get(self.mode, 1.0)
        return max(0.25, base / self.speed * 2)   # speed 1 = slow … 10 = fast (rate-limited)

    def _run(self):
        confirmed = store.load()["confirmed"]
        native = confirmed.get(f"fx_{self.mode}")
        if native:
            send_candidate(native)
            return
        if self.mode == "solid":
            if self.color in confirmed:
                send_candidate(confirmed[self.color])
            return
        off = confirmed.get("off")
        seq: List[Dict] = []
        if self.mode in ("strobe", "pulse") and self.color in confirmed:
            seq = [confirmed[self.color]] + ([off] if off else [])
        elif self.mode == "rainbow":
            seq = [confirmed[c["id"]] for c in COLORS if c["id"] in confirmed]
        if len(seq) < 2:
            return   # nothing to animate with yet
        i = 0
        while not self._stop.is_set():
            send_candidate(seq[i % len(seq)])
            i += 1
            if not self._sleep(self.interval()):
                return

    def state(self) -> Dict:
        return {"mode": self.mode, "color": self.color, "speed": self.speed, "running": self.running()}


class Engine:
    def __init__(self):
        self.job: Optional[Job] = None
        self.lock = threading.Lock()

    def replace(self, job: Optional[Job]):
        with self.lock:
            if self.job:
                self.job.stop()
            self.job = job
            if job:
                job.start()

    def discovery(self) -> Optional[Discovery]:
        return self.job if isinstance(self.job, Discovery) else None

    def effect(self) -> Optional[Effect]:
        return self.job if isinstance(self.job, Effect) else None


engine = Engine()
