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
from warroom_common import (season_ending, do_not_pitch, rec_keys, identifiable, latest, load_json, write_json,
                            iso_pt, now_pt, parse_now, week_for, assert_no_pending, ListError, PendingError, PT)

def build(w, data_dir, now, raw=None, raw_name=None, fa=None, fa_asof=None):
    # Deny-pending gate on the INPUT plan: anything pending stops the run (nothing is written).
    assert_no_pending(w, "warroom.json input")
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
        # only the week header and scrape stamp are read from the raw file; trades/claims are never read.
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
    FA = {}
    for p in (fa or {}).get("freeAgents", []):
        for k in rec_keys(p):
            if not k.startswith("i:"):
                FA.setdefault(k, p)
    wv, blocked = [], []
    for r in out.get("waivers") or []:
        if not isinstance(r, dict) or not identifiable(r):
            blocked.append(r); continue          # a rec we cannot identify is never published
        if se.match(r) or dnp.match(r):
            continue
        r = dict(r)
        p = next((FA[k] for k in rec_keys(r) if k in FA), None)
        if fa is not None:
            r["stats"] = (f"{p.get('fpg')} FP/G season, {p.get('rosteredPct')}% rostered; FA as of {fa_asof}"
                          if p else "Not in the latest FA scrape; confirm availability")
        wv.append(r)
    for i, r in enumerate(wv, 1):
        r["rank"] = i
    out["waivers"] = wv
    if blocked:
        notes.append(f"{len(blocked)} recommendation(s) withheld: no player name or id.")
    if notes:
        out["refreshNotes"] = notes
    else:
        out.pop("refreshNotes", None)
    assert_no_pending(out, "warroom.json output")
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parent.parent / "data"))
    ap.add_argument("--raw-glob", default="/workspace/fantrax-raw-*.json")
    ap.add_argument("--fa-glob", default="/workspace/fantrax-scrape-*-newsletter.json")
    ap.add_argument("--no-fantrax", action="store_true", help="skip box-only Fantrax inputs (CI)")
    ap.add_argument("--now", help="override clock (tests)")
    a = ap.parse_args()
    now = parse_now(a.now) if a.now else now_pt()
    P = Path(a.data_dir) / "warroom.json"
    w = load_json(P)
    if w is None:
        sys.exit("FAIL: data/warroom.json missing")
    raw = rawf = fa = faf = fa_asof = None
    if not a.no_fantrax:
        rawf, raw, _ = latest(a.raw_glob, "rosters", now)
        faf, fa, fat = latest(a.fa_glob, "freeAgents", now)
        if faf:
            fa_asof = iso_pt(fat)
    try:
        d = build(w, a.data_dir, now, raw, rawf.name if rawf else None, fa, fa_asof)
    except (ListError, PendingError) as e:
        sys.exit(f"FAIL: {e}")
    write_json(P, d)
    print(f"warroom: week {d['week']}, {len(d['waivers'])} waiver recs, raw={rawf.name if rawf else None}, fa={faf.name if faf else None}")

if __name__ == "__main__":
    main()
