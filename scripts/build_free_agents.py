#!/usr/bin/env python3
"""Build data/free-agents.json from a Fantrax FA scrape (a JSON with a 'freeAgents' list).
Season-ending players (data/season-ending.json) and any FA flagged IR/out-for-season are always excluded.
Usage: build_free_agents.py [--scrape FILE | --glob PATTERN] [--data-dir DIR] [--asof ISO] [--exclude "A,B"]"""
import argparse, sys, os
from datetime import datetime
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
from warroom_common import season_ending, norm, latest, load_json, write_json, iso_pt, PT

VALID = {"QB", "RB", "WR", "TE", "DL", "LB", "DB"}
IR_RE = ("ir", "out for season", "season-ending", "season ending", "pup", "nfi")

def is_ir(p):
    t = " ".join(str(p.get(k) or "") for k in ("injury", "status")).lower()
    return any(x == t.strip() or x in t.split() or (len(x) > 3 and x in t) for x in IR_RE)

def build(scrape, data_dir, asof, extra=()):
    ex = season_ending(data_dir) | {norm(n) for n in extra}
    out, seen = [], set()
    for p in scrape["freeAgents"]:
        if norm(p["player"]) in ex or is_ir(p):
            continue
        pos = (p.get("pos") or "").split(",")[0].replace("(R)", "").strip()
        if pos not in VALID:
            continue
        key = (p["player"], p.get("team"))
        if key in seen:
            continue
        seen.add(key)
        r = p.get("rosteredPct")
        if isinstance(r, str):
            r = float(r.strip("%")) if r.strip("%") else None
        if r is not None and r >= 100:
            continue
        out.append({"player": p["player"], "pos": pos, "team": p.get("team"),
                    "fpg": p.get("fpg"), "last3Fpg": p.get("last3Fpg"), "rosteredPct": r})
    out.sort(key=lambda x: -(x["fpg"] or 0))
    return {"sample": False, "asOf": asof, "source": "Fantrax", "players": out}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scrape"); ap.add_argument("--glob", default="/workspace/fantrax-scrape-*-newsletter.json")
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parent.parent / "data"))
    ap.add_argument("--asof", help="default: scrape file mtime in PT")
    ap.add_argument("--exclude", default="")
    a = ap.parse_args()
    f = Path(a.scrape) if a.scrape else latest(a.glob, "freeAgents")[0]
    if not f:
        sys.exit("FAIL: no FA scrape found")
    scrape = load_json(f)
    asof = a.asof or iso_pt(datetime.fromtimestamp(f.stat().st_mtime, PT))
    d = build(scrape, a.data_dir, asof, [n for n in a.exclude.split(",") if n.strip()])
    write_json(Path(a.data_dir) / "free-agents.json", d)
    print(f"free-agents: {len(d['players'])} players from {f.name}, asOf {asof}")

if __name__ == "__main__":
    main()
