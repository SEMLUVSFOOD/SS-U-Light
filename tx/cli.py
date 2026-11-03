"""
Command-line helpers — handy over SSH before the dashboard is up.

    python -m tx.cli tone                 # Phase-1 smoke test (1 s carrier)
    python -m tx.cli ev1527 0x12345 1     # one EV1527 frame ×8, T=350us
    python -m tx.cli ev1527 0x12345 1 --t 300 --repeats 10
    python -m tx.cli pt2262 FFFFFFFF1000
    python -m tx.cli plan timing --list   # print a discovery plan
    python -m tx.cli import captures/x.sub [--send N]
    python -m tx.cli sweep timing          # fire a whole plan, numbered; Ctrl+C when the stick reacts
    python -m tx.cli sweep all --dwell 0.8 # every plan back to back (learn mode excluded)
    python -m tx.cli sweep ev1527 --start 120

Set ULIGHT_MOCK=1 to print instead of transmit.
"""

import argparse
import json
import time

from . import capture_import, discovery, encoders, rpitx


def _report(res):
    print(("OK  " if res.ok else "FAIL") + (" [mock] " if res.mock else " ") + res.summary)
    print("    $ " + " ".join(res.command))
    if res.output.strip():
        print("    " + res.output.strip().replace("\n", "\n    "))
    if res.error.strip():
        print("    stderr: " + res.error.strip())


def main():
    ap = argparse.ArgumentParser(prog="tx.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tone"); t.add_argument("--seconds", type=float, default=1.0)
    e = sub.add_parser("ev1527"); e.add_argument("address"); e.add_argument("data")
    e.add_argument("--t", type=int, default=350); e.add_argument("--repeats", type=int, default=8)
    p = sub.add_parser("pt2262"); p.add_argument("trits"); p.add_argument("--t", type=int, default=350)
    p.add_argument("--repeats", type=int, default=8)
    pl = sub.add_parser("plan"); pl.add_argument("name"); pl.add_argument("--list", action="store_true")
    sw = sub.add_parser("sweep")
    sw.add_argument("name", help="plan name, or 'all'")
    sw.add_argument("--dwell", type=float, default=1.0, help="seconds to watch after each guess")
    sw.add_argument("--start", type=int, default=1, help="1-based number to start from")
    im = sub.add_parser("import"); im.add_argument("path"); im.add_argument("--send", type=int)
    a = ap.parse_args()

    print(f"radio: {'MOCK' if rpitx.is_mock() else 'LIVE'}")
    if a.cmd == "tone":
        _report(rpitx.smoke_tone(a.seconds))
    elif a.cmd == "ev1527":
        tr = encoders.ev1527(int(a.address, 0), int(a.data, 0), a.t)
        _report(rpitx.send_pulses(tr, a.repeats, label=f"ev1527 {a.address}/{a.data}"))
    elif a.cmd == "pt2262":
        _report(rpitx.send_pulses(encoders.pt2262(a.trits, a.t), a.repeats, label=f"pt2262 {a.trits}"))
    elif a.cmd == "plan":
        cands = discovery.build_plan(a.name, {"my_address": 0x5A5A5})
        print(f"{len(cands)} candidates")
        for c in cands if a.list else cands[:5]:
            print(" ", c["id"], "—", c["label"])
    elif a.cmd == "sweep":
        _sweep(a)
    elif a.cmd == "import":
        cands = capture_import.import_file(a.path)
        print(json.dumps([{k: v for k, v in c.items() if k != "params"} for c in cands], indent=2))
        if a.send is not None:
            c = cands[a.send]
            _report(rpitx.send_pulses(discovery.candidate_to_train(c), c["repeats"], label=c["label"]))


def _sweep(a):
    """Fire a plan quickly from the terminal. Numbers match the app's Discover counter."""
    names = [n for n in discovery.PLANS if n != "learn"] if a.name == "all" else [a.name]
    ctx = {"my_address": 0x5A5A5}
    try:
        from web import store  # use the real learn address if one exists
        ctx["my_address"] = store.load().get("my_address") or 0x5A5A5
    except Exception:  # noqa: BLE001
        pass
    seq = [(n, i, c) for n in names for i, c in enumerate(discovery.build_plan(n, ctx), 1)]
    if a.name != "all":
        seq = [x for x in seq if x[1] >= a.start]
    print(f"{len(seq)} guesses, {a.dwell:.1f}s watch time each. Watch the stick! Ctrl+C the moment it reacts.\n")
    recent = []
    try:
        for n, i, c in seq:
            res = rpitx.send_pulses(discovery.candidate_to_train(c), c["repeats"], label=c["label"])
            mark = "" if res.ok else "  ✗ " + (res.error.strip().splitlines() or ["failed"])[-1]
            print(f"  {n:>7} #{i:<4} {c['label']}{mark}", flush=True)
            recent.append((n, i, c))
            if not res.ok and len(recent) == 1:
                print("\nFirst send failed — fix that before sweeping:\n" + res.error)
                return
            time.sleep(a.dwell)
    except KeyboardInterrupt:
        print("\n\nStopped. Your reaction lags a little, so the hit is probably one of these:")
        for n, i, c in recent[-4:]:
            print(f"  {n} #{i}: {c['label']}")
        n, i, _ = recent[-1] if recent else (a.name, 1, None)
        print(f"\nNext: in the app, Discover → pick '{n}' → Start at #{max(1, i - 3)} with a longer watch time,")
        print("then use ◀︎ ▶︎ to find the exact one and hit 'That did something!'.")
        print(f"Or re-run here:  python3 -m tx.cli sweep {n} --start {max(1, i - 3)} --dwell 2")
        return
    print("\nDone — nothing stopped it. Try another plan, or a longer --dwell.")


if __name__ == "__main__":
    main()
