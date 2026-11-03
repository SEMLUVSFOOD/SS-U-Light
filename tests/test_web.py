import os
import tempfile

os.environ["ULIGHT_MOCK"] = "1"
os.environ["ULIGHT_CODES"] = os.path.join(tempfile.mkdtemp(), "codes.json")

from web.app import app  # noqa: E402
from web import engine as eng  # noqa: E402


def test_flow():
    c = app.test_client()
    assert c.get("/").status_code == 200
    s = c.get("/api/state").get_json()
    assert s["radio"]["mock"] is True
    r = c.post("/api/color", json={"id": "red"}).get_json()
    assert r["unmapped"]
    assert c.post("/api/discovery/start", json={"plan": "timing", "dwell_ms": 600}).get_json()["ok"]
    r = c.post("/api/discovery/step", json={"dir": 1}).get_json()
    assert r["discovery"]["paused"]
    hit = c.post("/api/discovery/hit", json={}).get_json()["hit"]
    assert c.post("/api/codes/confirm", json={"action": "red", "candidate": hit["candidate"]}).get_json()["ok"]
    r = c.post("/api/color", json={"id": "red"}).get_json()
    assert r["ok"] and r["tx"]["mock"]
    assert c.post("/api/color", json={"hex": "#ee1122"}).get_json()["id"] == "red"
    c.post("/api/stop", json={})
    eng.engine.replace(None)
