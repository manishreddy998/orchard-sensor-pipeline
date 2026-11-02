"""Capture README screenshots from a running dashboard: python scripts/screenshots.py http://localhost:8599"""
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
SHOTS = [("Codling moth timing", "pest_timing.png"), ("Sensor health", "sensor_health.png"),
         ("Late data", "late_data.png"), ("Label assistant", "label_assistant.png")]

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome") if "--chrome" in sys.argv else p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 1000})
    pg.goto(URL)
    pg.wait_for_selector("text=Orchard sensor pipeline", timeout=60000)
    pg.wait_for_timeout(4000)
    for tab, name in SHOTS:
        pg.get_by_role("tab", name=tab).click()
        pg.wait_for_timeout(3500)
        pg.screenshot(path=f"docs/img/{name}", full_page=True)
    b.close()
