#!/usr/bin/env python3
"""Build data/free-agents.json from the newest Fantrax FA scrape (a JSON with a 'freeAgents' list).
Season-ending players (data/season-ending.json, REQUIRED: missing/invalid = fail) and FAs flagged IR are
excluded; rows that cannot be identified (no name and no id) are dropped. Bill's passes (do-not-pitch) are
NOT removed here; they only leave the waiver recs.
Usage: build_free_agents.py [--scrape FILE | --glob PATTERN] [--data-dir DIR] [--out FILE] [--exclude "A,B"]"""
import argparse, sys, os
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
from warroom_common import (season_ending, Excluder, identifiable, latest, load_json, write_json, iso_pt,
                            scrape_time, assert_no_pending, ListError, PendingError)

VALID = {"QB", "RB", "WR", "TE", "DL", "LB", "DB"}
IR_WORDS = {"ir", "ir-r", "pup", "pup-r", "nfi", "out for season", "season-ending", "season ending"}

def is_ir(p):
    for k in ("injury", "status", "injury_text"):
        t = str(p.get(k) or "").lower()
        if not t:
            continue
        if any(w in t for w in ("out for season", "season-ending", "season ending")):
            return True
        toks = {x.strip(" -,()") for x in t.replace("/", " ").split()}
        if toks & IR_WORDS:
            return True
    return False

def build(scrape, data_dir, asof, extra=()):
    se = season_ending(data_dir)
    ex = Excluder([{"name": n} for n in extra])
    out, seen = [], set()
    for p in scrape["freeAgents"]:
        if not identifiable(p) or se.match(p) or ex.match(p) or is_ir(p):
            continue
        pos = (p.get("pos") or "").split(",")[0].replace("(R)", "").strip()
        if pos not in VALID:
            continue
        key = (p.get("player"), p.get("team"))
        if key in seen:
            continue
        seen.add(key)
        r = p.get("rosteredPct")
        if isinstance(r, str):
            r = float(r.strip("%")) if r.strip("%") else None
        if r is not None and r >= 100:
            continue
        out.append({"player": p.get("player"), "pos": pos, "team": p.get("team"),
                    "fpg": p.get("fpg"), "last3Fpg": p.get("last3Fpg"), "rosteredPct": r})
    out.sort(key=lambda x: -(x["fpg"] or 0))
    d = {"sample": False, "asOf": asof, "source": "Fantrax", "players": out}
    assert_no_pending(d, "free-agents.json")
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scrape"); ap.add_argument("--glob", default="/workspace/fantrax-scrape-*-newsletter.json")
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parent.parent / "data"))
    ap.add_argument("--out"); ap.add_argument("--asof"); ap.add_argument("--exclude", default="")
    a = ap.parse_args()
    if a.scrape:
        f = Path(a.scrape); scrape = load_json(f); t = scrape_time(scrape)
    else:
        f, scrape, t = latest(a.glob, "freeAgents")
    if not f:
        sys.exit("FAIL: no FA scrape with a scrape timestamp found")
    asof = a.asof or (iso_pt(t) if t else None)
    if not asof:
        sys.exit(f"FAIL: {f} has no scrape timestamp")
    try:
        d = build(scrape, a.data_dir, asof, [n for n in a.exclude.split(",") if n.strip()])
    except (ListError, PendingError) as e:
        sys.exit(f"FAIL: {e}")
    write_json(a.out or Path(a.data_dir) / "free-agents.json", d)
    print(f"free-agents: {len(d['players'])} players from {f.name}, asOf {asof}")

if __name__ == "__main__":
    main()
