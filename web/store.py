"""
codes.json — our lab notebook. Plain JSON so you can read/edit it by hand.

  hits       every time you pressed "that did something!" (candidate + the one
             before it, since your reaction lags the radio by a moment)
  confirmed  action name -> candidate, e.g. "red" -> {...}. Buttons use these.
  imports    candidates parsed from real captures (tx/capture_import.py)
  my_address our random 20-bit address for learn-mode attempts
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, Optional

PATH = os.environ.get("ULIGHT_CODES", os.path.join(os.path.dirname(__file__), "..", "codes.json"))
_lock = threading.Lock()

EMPTY = {
    "_about": "U-Light code notebook. Edit by hand if you like; the dashboard rewrites it.",
    "version": 1,
    "freq_hz": 433920000,
    "my_address": None,
    "hits": [],
    "confirmed": {},
    "imports": [],
}


def load() -> Dict:
    with _lock:
        try:
            with open(PATH) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
    merged = json.loads(json.dumps(EMPTY))
    merged.update(data)
    return merged


def save(data: Dict) -> None:
    with _lock:
        tmp = PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, PATH)   # atomic: never leaves a half-written file


def add_hit(candidate: Dict, previous: Optional[Dict], note: str = "") -> Dict:
    data = load()
    hit = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note,
           "candidate": candidate, "previous": previous}
    data["hits"].append(hit)
    save(data)
    return hit


def confirm(action: str, candidate: Dict) -> None:
    data = load()
    data["confirmed"][action] = candidate
    save(data)


def unconfirm(action: str) -> None:
    data = load()
    data["confirmed"].pop(action, None)
    save(data)
