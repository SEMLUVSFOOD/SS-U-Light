"""
Screenshot the dashboard at phone size (light + dark) for design review.
    ULIGHT_MOCK=1 python -m web.app &        # in another terminal
    python scripts/screenshot.py [out_dir]   # pip install playwright && playwright install chromium
"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://localhost:8080/"
out = sys.argv[1] if len(sys.argv) > 1 else "docs/screens"

with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ("light", "dark"):
        pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1, color_scheme=scheme)
        pg.goto(URL); pg.wait_for_timeout(800)
        pg.screenshot(path=f"{out}/control-{scheme}.png", full_page=True)
        pg.click("#t-discover"); pg.click("#d-start"); pg.wait_for_timeout(2500)
        pg.screenshot(path=f"{out}/discover-{scheme}.png", full_page=True)
        pg.click("#d-hit"); pg.wait_for_timeout(600)
        pg.click("#t-codes"); pg.wait_for_timeout(1200)
        pg.screenshot(path=f"{out}/codes-{scheme}.png", full_page=True)
        pg.click("#t-control"); pg.request.post(URL + "api/stop")
        pg.close()
    b.close()
print("saved to", out)
