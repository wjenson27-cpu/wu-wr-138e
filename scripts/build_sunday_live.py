#!/usr/bin/env python3
"""Rebuild data/sunday/live.json and data/td-parlay.json from the League HQ checkout
and the newest Fantrax raw scrape on the box. Never invents numbers: anything the
sources do not carry is written as null.

Usage: python3 scripts/build_sunday_live.py [--hq /workspace/wheels-up-hq-ghpages] [--scrapes /workspace]
"""
import argparse, glob, json, os, re
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FANTRAX_NAMES = {"eddies": "Eagle Ridge Eddies", "ultron": "Ultron"}
DISPLAY = {"eddies": "Eagleridge Eddie's", "ultron": "Ultron"}
INJ = {"INJURED": "Q", "INJURED_DOUBTFUL": "D", "INJURED_OUT": "OUT", "INJURY_LIST": "IR"}
POS_ORDER = ["QB", "RB", "WR", "TE", "DL", "LB", "DB"]


def newest_raw(scrapes):
    files = glob.glob(os.path.join(scrapes, "fantrax-raw-*.json"))
    files = [f for f in files if not f.endswith(".orig.json")]
    def key(f):
        m = re.search(r"(\d{4}-\d{2}-\d{2})-(am|pm)", f)
        return (m.group(1), m.group(2)) if m else ("", "")
    return max(files, key=key)


def parse_pt(s):
    # "2026-10-31 ~06:40 PDT" -> ISO with offset
    m = re.search(r"(\d{4}-\d{2}-\d{2})\D+(\d{1,2}):(\d{2})\s*(PDT|PST)?", s or "")
    if not m:
        return None
    off = "-08:00" if m.group(4) == "PST" else "-07:00"
    return "%sT%02d:%s:00%s" % (m.group(1), int(m.group(2)), m.group(3), off)


def injury(tags):
    codes = [INJ[t] for t in tags or [] if t in INJ]
    for c in ("OUT", "IR", "D", "Q"):
        if c in codes:
            return c
    return ""


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def starters(raw, fantrax_name):
    team = next(t for t in raw["rosters"] if t["team"] == fantrax_name)
    out = []
    for p in team["players"]:
        if p.get("slot") != "active":
            continue
        pos = p["pos"].split(",")[0]
        out.append({"player": p["name"], "pos": pos, "nflTeam": p.get("nfl") or None,
                    "status": None, "points": None, "projection": None,
                    "injury": injury(p.get("injury_tags"))})
    out.sort(key=lambda r: POS_ORDER.index(r["pos"]) if r["pos"] in POS_ORDER else 99)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hq", default="/workspace/wheels-up-hq-ghpages")
    ap.add_argument("--scrapes", default="/workspace")
    a = ap.parse_args()
    raw_path = newest_raw(a.scrapes)
    raw = json.load(open(raw_path))
    hdr = raw.get("week8_header") or {}
    week = int(re.search(r"Week (\d+)", hdr.get("week", "")).group(1))
    score = [num(x) for x in (hdr.get("score") or "-").split("-")]
    if len(score) != 2:
        score = [None, None]
    # header score is "featured-opponent" from the featured club's view
    teams = []
    for i, tid in enumerate(["eddies", "ultron"]):
        rec = raw.get("records", {}).get(FANTRAX_NAMES[tid])
        teams.append({
            "id": tid, "name": DISPLAY[tid],
            "record": re.sub(r"-0$", "", rec) if rec else None,
            "score": score[i],
            "projection": num(hdr.get("eddies_proj" if i == 0 else "opp_proj")),
            "starters": starters(raw, FANTRAX_NAMES[tid]),
        })
    live = {
        "schemaVersion": 1, "sample": False,
        "updatedAt": parse_pt(raw.get("scraped")),
        "season": 2026, "week": week, "opponent": "ultron",
        "source": "Fantrax read-only scrape %s (League HQ sync)" % os.path.basename(raw_path),
        "dataNote": "Team score and projected final are Fantrax matchup totals. Per-player points, projections and game status are not in the scrape and are left null.",
        "teams": teams,
    }
    hq = json.load(open(os.path.join(a.hq, "data", "td-parlay.json")))
    picks = []
    for i, o in enumerate(hq.get("owners") or hq.get("participants") or []):
        w = (o.get("weeks") or {}).get(str(week)) or {}
        if not w.get("player"):
            continue
        td = w.get("td") or ""
        picks.append({"week": week, "participant": "Entry %d" % (i + 1), "pick": w["player"],
                      "result": td if td in ("Yes", "No") else ("N/A" if td == "N/A" else "pending")})
    parlay = {"schemaVersion": 1, "sample": False, "updatedAt": live["updatedAt"], "season": 2026,
              "note": "League anytime-TD picks for Week %d from the HQ sheet (updated %s). Entries are unlabeled on purpose." % (week, hq.get("updated")),
              "picks": picks}
    for rel, obj in (("data/sunday/live.json", live), ("data/td-parlay.json", parlay)):
        with open(os.path.join(ROOT, rel), "w") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print("wrote live.json (%s, %s) and %d parlay picks from %s" % (live["updatedAt"], hdr.get("score"), len(picks), raw_path))


if __name__ == "__main__":
    main()
