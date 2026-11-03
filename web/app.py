"""
U-Light phone bridge — Flask dashboard.

Run on the Mac (mock radio, nothing transmitted):
    ULIGHT_MOCK=1 python -m web.app          # then open http://localhost:8080
Run on the Pi (real radio) via the systemd unit in setup/.
"""

from __future__ import annotations

import os
import tempfile

from flask import Flask, jsonify, render_template, request

from tx import capture_import, discovery, rpitx

from . import store
from .engine import ACTIONS, COLORS, NATIVE_FX, Discovery, Effect, engine, nearest_color, send_candidate

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024   # capture uploads


def body():
    return request.get_json(silent=True) or {}


def err(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


@app.get("/")
def index():
    return render_template("index.html", colors=COLORS, plans=discovery.PLANS, native_fx=NATIVE_FX)


@app.get("/api/state")
def state():
    d, e = engine.discovery(), engine.effect()
    codes = store.load()
    return jsonify({
        "radio": rpitx.status(),
        "discovery": dict(d.state(), pulses=_preview(d.current())) if d else None,
        "effect": e.state() if e else None,
        "confirmed": sorted(codes["confirmed"].keys()),
        "hits": codes["hits"][-8:][::-1],
        "imports": codes["imports"],
        "actions": ACTIONS,
        "tx": [r.to_dict() for r in rpitx.history[-8:]][::-1],
    })


def _preview(c, n=70):
    """First n pulses of a candidate, for the little waveform drawing."""
    if not c:
        return []
    try:
        return discovery.candidate_to_train(c)[:n]
    except (KeyError, ValueError):
        return []


# ---------- everyday control ----------

@app.post("/api/color")
def color():
    """{"id": "red"} or {"hex": "#ff3399"} -> send the matching confirmed code."""
    b = body()
    cid = b.get("id") or nearest_color(b.get("hex", "#ffffff"), only_confirmed=True)["id"]
    codes = store.load()["confirmed"]
    engine.replace(None)
    if cid not in codes:
        return jsonify({"ok": False, "unmapped": True, "id": cid,
                        "error": f"No code confirmed for “{cid}” yet — find one in Discovery."})
    res = send_candidate(codes[cid], label=f"colour {cid}")
    return jsonify({"ok": res.ok, "id": cid, "tx": res.to_dict()})


@app.post("/api/effect")
def effect():
    b = body()
    mode = b.get("mode", "solid")
    if mode not in ("solid", "strobe", "rainbow", "pulse"):
        return err("unknown effect")
    if mode == "rainbow" and len(set(store.load()["confirmed"]) & {c["id"] for c in COLORS}) < 2:
        engine.replace(None)
        return jsonify({"ok": False, "unmapped": True, "error": "Rainbow needs at least 2 confirmed colours."})
    job = Effect(mode, b.get("color", "pink"), int(b.get("speed", 5)))
    engine.replace(job)
    return jsonify({"ok": True, "effect": job.state()})


@app.post("/api/stop")
def stop():
    engine.replace(None)
    return jsonify({"ok": True})


@app.post("/api/tone")
def tone():
    engine.replace(None)
    res = rpitx.smoke_tone(float(body().get("seconds", 1.0)))
    return jsonify({"ok": res.ok, "tx": res.to_dict()})


# ---------- discovery ----------

@app.post("/api/discovery/start")
def disc_start():
    b = body()
    plan = b.get("plan", "timing")
    codes = store.load()
    if plan == "learn" and not codes.get("my_address"):
        codes["my_address"] = discovery.new_learn_address()
        store.save(codes)
    try:
        cands = discovery.build_plan(plan, {"my_address": codes.get("my_address")})
    except KeyError:
        return err("unknown plan")
    dwell = max(600, min(int(b.get("dwell_ms", 1500)), 6000))
    job = Discovery(plan, cands, dwell, int(b.get("start", 0)))
    engine.replace(job)
    return jsonify({"ok": True, "discovery": job.state()})


@app.post("/api/discovery/pause")
def disc_pause():
    d = engine.discovery()
    if not d:
        return err("discovery not running")
    d.paused = bool(body().get("paused", not d.paused))
    return jsonify({"ok": True, "discovery": d.state()})


@app.post("/api/discovery/step")
def disc_step():
    """Paused: move ±1 and re-fire, so you can bracket the exact hit."""
    d = engine.discovery()
    if not d:
        return err("discovery not running")
    d.paused = True
    step = int(body().get("dir", 1))
    d.index = max(0, min(len(d.candidates) - 1, d.index + step))
    d.fire(d.index)
    return jsonify({"ok": True, "discovery": d.state()})


@app.post("/api/discovery/replay")
def disc_replay():
    d = engine.discovery()
    if not d or not d.current():
        return err("nothing sent yet")
    d.paused = True
    d.fire(d.sent[-1])
    return jsonify({"ok": True, "discovery": d.state()})


@app.post("/api/discovery/hit")
def disc_hit():
    """THAT DID SOMETHING! — log current + previous candidate and pause."""
    d = engine.discovery()
    if not d or not d.current():
        return err("nothing sent yet")
    d.paused = True
    hit = store.add_hit(d.current(), d.previous(), body().get("note", ""))
    return jsonify({"ok": True, "hit": hit})


# ---------- codes ----------

@app.post("/api/codes/confirm")
def codes_confirm():
    """{"action": "red", "candidate": {...}} — map a hit to a button."""
    b = body()
    if b.get("action") not in ACTIONS:
        return err("unknown action")
    if not isinstance(b.get("candidate"), dict) or "proto" not in b["candidate"]:
        return err("missing candidate")
    store.confirm(b["action"], b["candidate"])
    return jsonify({"ok": True})


@app.post("/api/codes/unconfirm")
def codes_unconfirm():
    store.unconfirm(body().get("action", ""))
    return jsonify({"ok": True})


@app.post("/api/codes/send")
def codes_send():
    """Fire any candidate JSON (from a hit or an import) once."""
    c = body().get("candidate")
    if not isinstance(c, dict):
        return err("missing candidate")
    engine.replace(None)
    try:
        res = send_candidate(c)
    except (KeyError, ValueError) as e:
        return err(str(e))
    return jsonify({"ok": res.ok, "tx": res.to_dict()})


@app.post("/api/import")
def import_capture():
    f = request.files.get("file")
    if not f or not f.filename:
        return err("no file")
    suffix = os.path.splitext(f.filename)[1].lower()
    if suffix not in (".sub", ".ook"):
        return err("expected a Flipper .sub or rtl_433 .ook file")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, os.path.basename(f.filename))
        f.save(path)
        try:
            cands = capture_import.import_file(path)
        except (ValueError, KeyError) as e:
            return err(str(e))
    codes = store.load()
    known = {c["id"] for c in codes["imports"]}
    codes["imports"] += [c for c in cands if c["id"] not in known]
    store.save(codes)
    return jsonify({"ok": True, "imported": len(cands)})


def main():
    host = os.environ.get("ULIGHT_HOST", "0.0.0.0")
    port = int(os.environ.get("ULIGHT_PORT", "8080"))
    print(f"U-Light bridge on http://{host}:{port}  (radio: {'MOCK' if rpitx.is_mock() else 'LIVE'})")
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
