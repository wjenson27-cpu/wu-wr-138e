#!/usr/bin/env python3
"""Date-agnostic War Room refresh of data/warroom.json.

The day's routine still writes the editorial plan (lineup reasons, news). This script, run after it or on its own:
- computes week = 1 + floor((today_PT - 2026-09-10) / 7) and stamps asOf/lastUpdated/freshness.plan in PT;
- reads the latest Fantrax raw scrape (fantrax-raw-*.json) for the week header + roster stamp only
  (it never reads or copies bids, claims, trades or anything pending);
- reads the latest FA scrape (fantrax-scrape-*-newsletter.json) to refresh waiver stats;
- drops season-ending players (data/season-ending.json) and Bill's passes (data/do-not-pitch.json) from waiver recs, re-ranks 1..N;
- applies the no-pending rule to the whole file.
Usage: build_warroom.py [--data-dir DIR] [--raw-glob G] [--fa-glob G] [--now ISO]"""
import argparse, os, re, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
from warroom_common import (season_ending, do_not_pitch, norm, latest, load_json, write_json,
                            iso_pt, now_pt, week_for, strip_pending, PT)

def build(w, data_dir, now, raw=None, raw_name=None, fa=None, fa_asof=None):
    week = week_for(now)
    stamp = iso_pt(now)
    out = dict(w)
    notes = []
    if out.get("week") not in (None, week):
        notes.append(f"Editorial plan was written for week {out.get('week')}; current week is {week}. Re-run the newsletter routine.")
    out["week"] = week
    out["asOf"] = stamp
    out["lastUpdated"] = stamp
    fr = dict(out.get("freshness") or {})
    fr["plan"] = stamp
    if fa_asof:
        fr["waivers"] = fa_asof
    out["freshness"] = fr
    if raw:
        hdr = raw.get("week7_header") or raw.get("weekHeader") or {}
        rw = None
        m = re.search(r"week\s*(\d+)", str(hdr), re.I)
        if m:
            rw = int(m.group(1))
        if rw and rw != week:
            notes.append(f"Fantrax header says week {rw}; date math says {week}.")
        out["fantraxRaw"] = {"file": raw_name, "scraped": raw.get("scraped")}
    se = season_ending(data_dir)
    dnp = do_not_pitch(data_dir, week, now.date())
    FA = {norm(p["player"]): p for p in (fa or {}).get("freeAgents", [])}
    wv = []
    for r in out.get("waivers") or []:
        n = norm(r.get("player"))
        if n in se or n in dnp:
            continue
        r = dict(r)
        p = FA.get(n)
        if fa is not None:
            r["stats"] = (f"{p.get('fpg')} FP/G season, {p.get('rosteredPct')}% rostered; FA as of {fa_asof}"
                          if p else "Not in the latest FA scrape; confirm availability")
        wv.append(r)
    for i, r in enumerate(wv, 1):
        r["rank"] = i
    out["waivers"] = wv
    if notes:
        out["refreshNotes"] = notes
    else:
        out.pop("refreshNotes", None)
    return strip_pending(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parent.parent / "data"))
    ap.add_argument("--raw-glob", default="/workspace/fantrax-raw-*.json")
    ap.add_argument("--fa-glob", default="/workspace/fantrax-scrape-*-newsletter.json")
    ap.add_argument("--no-fantrax", action="store_true", help="skip box-only Fantrax inputs (CI)")
    ap.add_argument("--now", help="override clock (tests)")
    a = ap.parse_args()
    now = datetime.fromisoformat(a.now).astimezone(PT) if a.now else now_pt()
    P = Path(a.data_dir) / "warroom.json"
    w = load_json(P)
    if w is None:
        sys.exit("FAIL: data/warroom.json missing")
    raw = rawf = fa = faf = fa_asof = None
    if not a.no_fantrax:
        rawf, raw = latest(a.raw_glob, "rosters")
        faf, fa = latest(a.fa_glob, "freeAgents")
        if faf:
            fa_asof = iso_pt(datetime.fromtimestamp(faf.stat().st_mtime, PT))
    d = build(w, a.data_dir, now, raw, rawf.name if rawf else None, fa, fa_asof)
    write_json(P, d)
    print(f"warroom: week {d['week']}, {len(d['waivers'])} waiver recs, raw={rawf.name if rawf else None}, fa={faf.name if faf else None}")

if __name__ == "__main__":
    main()
