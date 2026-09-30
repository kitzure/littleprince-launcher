#!/usr/bin/env python3
"""Drive /tmp/bbtest.html (the shipped bbDraw) in real Chromium and assert the layout."""
import json

from playwright.sync_api import sync_playwright

PAD = 44
MAXW = 694 - 2 * PAD
PAGE_BOTTOM = 510 - 40 + 16      # content bottom + one line of descender slack
HEAD_BAND_BOTTOM = 3 + 72
results = {}


def check(name, box, x0=PAD - 6, x1=694 - PAD + 6, ytop=82, ybot=PAGE_BOTTOM):
    r = {"box": box, "ok": True, "why": []}
    if box["empty"]:
        r["ok"] = False
        r["why"].append("nothing drawn")
    else:
        if box["minx"] < x0:
            r["ok"] = False
            r["why"].append("left margin broken (%d < %d)" % (box["minx"], x0))
        if box["maxx"] > x1:
            r["ok"] = False
            r["why"].append("right margin broken (%d > %d)" % (box["maxx"], x1))
        if box["miny"] < ytop:
            r["ok"] = False
            r["why"].append("overlaps the header band (%d < %d)" % (box["miny"], ytop))
        if box["maxy"] > ybot:
            r["ok"] = False
            r["why"].append("glued to the bottom (%d > %d)" % (box["maxy"], ybot))
    results[name] = r


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 900, "height": 760})
    page.goto("file:///tmp/bbtest.html")
    page.wait_for_timeout(300)
    data = page.evaluate("window.__run()")
    for key, val in data.items():
        if "body" in val:
            check(key, val["body"])
        if "header" in val:
            hb = val["header"]
            hr = {"box": hb, "ok": not hb["empty"] and hb["minx"] >= PAD - 6
                  and hb["maxx"] <= 694 - PAD + 6 and hb["miny"] >= 6
                  and hb["maxy"] <= HEAD_BAND_BOTTOM, "why": []}
            if hb["empty"]:
                hr["ok"] = False
                hr["why"].append("no title drawn in the band")
            if hb["maxx"] > 694 - PAD + 6:
                hr["why"].append("title overflows the band (maxx %d)" % hb["maxx"])
            results[key + ".header"] = hr
    # screenshots of the most important cases
    cases = {
        "A": ("whatsupp", None),
        "B": ("這張公告是在帳號網站的 Admin → Billboard 加的，遊戲裡一開佈告欄就會見到，"
              "而且文字要懂得自動換行，不要黏在卡片的最底邊。", None),
        "D": ("A picture with a caption under it.", "#c94f4f"),
        "F": ("", None),
    }
    for tag, (text, colour) in cases.items():
        page.evaluate(
            """([t,c])=>{
                 BOARD=[{title:'測試公告'}]; BSEL=0;
                 document.getElementById('bb-text').value=t;
                 if(c){ const cv=document.createElement('canvas'); cv.width=600; cv.height=900;
                        const x=cv.getContext('2d'); x.fillStyle=c; x.fillRect(0,0,600,900);
                        x.fillStyle='#fff'; x.font='600 60px sans-serif'; x.fillText('PIC',30,90);
                        BBIMG=cv; } else { BBIMG=null; }
                 bbDraw();
               }""", [text, colour])
        page.locator("#bb-canvas").screenshot(path="/tmp/card_%s.png" % tag)
    browser.close()

print(json.dumps(results, indent=1))
bad = [k for k, v in results.items() if not v["ok"]]
print("\nFAILURES:", bad if bad else "none")
