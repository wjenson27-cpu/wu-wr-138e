#!/usr/bin/env python3
"""Score Eddie's recommendation ledger (data/recs.json) and write the War Room summary (data/recs-summary.json).

Points only come from real Fantrax scrape files in --sources (default /workspace):
  1. fantrax-week{W}-box-details-*.json  (starters, any team)
  2. fantrax-*.json with a week{W}Fpts / wk{W}Fpts number on a roster row, or a Fantrax note
     "N pts if started" on a row in a scrape taken during week W
  3. an entry's "delta": {name: [before_file, after_file]} -> season fpts difference between two scrapes
A side with no real source stays null. A rec is scored only when both sides have points; it is
VERIFIED only when both came from a source file. Nothing is estimated.

Privacy: only recs whose week is past, or whose decision is "completed"/"past", are published. Anything
pending (unprocessed claims, bids, open offers) or in a future week makes the run fail (exit 1) and
writes nothing.
"""
import argparse, glob, json, os, re, sys, unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEASON_START = date(2026, 9, 10)
TYPES = ("waiver_add", "start_sit", "trade", "faab", "green_dot")
DONE = ("completed", "past")
PENDING_RE = re.compile(r"\b(pending|queued claim|claim queued|awaiting|submitted|proposed|open offer|offer sent|in review|outstanding)\b", re.I)


def pt_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-7)))


def week_of(d):
    return 1 + (d - SEASON_START).days // 7


def norm(name):
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", s)
    return re.sub(r"[^a-z]+", "", s)


def _rows(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _rows(v)
    elif isinstance(o, list):
        for v in o:
            yield from _rows(v)


def _name(row):
    for k in ("player", "name"):
        if isinstance(row.get(k), str):
            return row[k]
    return None


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _scrape_date(doc):
    s = str(doc.get("scrapedAt") or doc.get("scraped") or "") if isinstance(doc, dict) else ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def _load(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return None


class Sources:
    def __init__(self, src_dir):
        self.dir = Path(src_dir)
        self._cache = {}

    def doc(self, name):
        if name not in self._cache:
            self._cache[name] = _load(self.dir / name)
        return self._cache[name]

    def lookup(self, week, player, delta=None):
        """(pts, source_file) or (None, None)."""
        key = norm(player)
        for f in sorted(glob.glob(str(self.dir / f"fantrax-week{week}-box-details-*.json"))):
            d = self.doc(os.path.basename(f))
            if not isinstance(d, dict) or d.get("week") != week:
                continue
            for row in _rows(d.get("matchups")):
                if norm(_name(row)) == key and _num(row.get("pts")) is not None:
                    return _num(row["pts"]), os.path.basename(f)
        for f in sorted(glob.glob(str(self.dir / "fantrax-*.json"))):
            d = self.doc(os.path.basename(f))
            if not isinstance(d, dict):
                continue
            sd = _scrape_date(d)
            for row in _rows(d):
                if norm(_name(row)) != key:
                    continue
                for k in (f"week{week}Fpts", f"wk{week}Fpts"):
                    if _num(row.get(k)) is not None:
                        return _num(row[k]), os.path.basename(f)
                if sd and week_of(sd) == week:
                    note = " ".join(str(row.get(k) or "") for k in ("note", "notes"))
                    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:fpts|pts)\s+if started", note, re.I)
                    if m:
                        return float(m[1]), os.path.basename(f)
        if delta and player in delta:
            a, b = delta[player]
            da, db = self.doc(a), self.doc(b)
            if da and db and _scrape_date(da) and _scrape_date(db) and week_of(_scrape_date(db)) == week:
                fa = [_num(r.get("fpts")) for r in _rows(da) if norm(_name(r)) == key and _num(r.get("fpts")) is not None]
                fb = [_num(r.get("fpts")) for r in _rows(db) if norm(_name(r)) == key and _num(r.get("fpts")) is not None]
                if len(set(fa)) == 1 and len(set(fb)) == 1 and fb[0] >= fa[0]:
                    return fb[0] - fa[0], f"{b} minus {a} (season fpts)"
        return None, None


def eligible(rec, cur_week):
    """True when the rec may be published. Raises ValueError for pending/future recs (fail closed)."""
    wk, dec = rec.get("week"), rec.get("decision")
    if not isinstance(wk, int) or wk < 1:
        raise ValueError(f"{rec.get('id')}: bad week")
    text = " ".join(str(rec.get(k) or "") for k in ("call", "reason", "decision", "status"))
    if PENDING_RE.search(text) or dec not in DONE:
        raise ValueError(f"{rec.get('id')}: pending or undecided rec can't be published")
    if wk > cur_week:
        raise ValueError(f"{rec.get('id')}: future week {wk}")
    return True


def score(ledger, src, cur_week):
    for r in ledger["recs"]:
        if r.get("type") not in TYPES:
            raise ValueError(f"{r.get('id')}: unknown type {r.get('type')}")
        eligible(r, cur_week)
        r.setdefault("status", "open")
        if r["week"] >= cur_week:
            r.update(status="open", result=None, pts_player=None, pts_alt=None, verified="UNVERIFIED", source=None)
            continue
        pp, sp = src.lookup(r["week"], r["player"], r.get("delta"))
        pa, sa = (src.lookup(r["week"], r["alternative"], r.get("delta")) if r.get("alternative") else (None, None))
        if pp is None and r.get("status") == "scored" and r.get("verified") == "VERIFIED":
            continue  # source files not on this machine: keep the earlier verified score
        r["pts_player"], r["pts_alt"] = pp, pa
        if pp is not None and pa is not None:
            r["status"] = "scored"
            r["result"] = "hit" if pp > pa else "miss" if pp < pa else "push"
            r["verified"] = "VERIFIED"
            r["source"] = "; ".join(sorted({sp, sa}))
        else:
            r["status"], r["result"], r["verified"] = "open", None, "UNVERIFIED"
            missing = [n for n, v in ((r["player"], pp), (r.get("alternative") or "no alternative named", pa)) if v is None]
            r["source"] = (sp + "; " if sp else "") + "no real points for " + ", ".join(missing)
    return ledger


def summary(ledger, cur_week, now):
    pub = [r for r in ledger["recs"] if eligible(r, cur_week)]
    scored = [r for r in pub if r.get("status") == "scored"]
    def rate(rs):
        h = sum(r["result"] == "hit" for r in rs); m = sum(r["result"] == "miss" for r in rs)
        return {"hits": h, "misses": m, "pushes": len(rs) - h - m, "scored": len(rs),
                "hitRate": round(h / (h + m), 3) if h + m else None}
    by_type = {t: rate([r for r in scored if r["type"] == t]) for t in TYPES}
    for t in TYPES:
        by_type[t]["total"] = sum(r["type"] == t for r in pub)
    keyed = sorted(scored, key=lambda r: (r["pts_player"] - r["pts_alt"], r["id"]))
    slim = lambda r: {k: r.get(k) for k in ("id", "date", "week", "type", "player", "call", "alternative", "reason",
                                            "status", "result", "pts_player", "pts_alt", "verified", "source")}
    notes = sorted([n for n in ledger.get("learning", []) if isinstance(n.get("week"), int) and n["week"] < cur_week],
                   key=lambda n: n["week"])
    return {
        "generatedAt": now.isoformat(timespec="minutes"), "week": cur_week,
        "overall": rate(scored), "total": len(pub),
        "verified": sum(r.get("verified") == "VERIFIED" for r in pub),
        "unverified": sum(r.get("verified") != "VERIFIED" for r in pub),
        "byType": by_type,
        "best": [slim(r) for r in reversed(keyed[-3:]) if r["result"] == "hit"],
        "worst": [slim(r) for r in keyed[:3] if r["result"] == "miss"],
        "latestLearning": notes[-1] if notes else None,
        "recs": [slim(r) for r in pub],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=str(ROOT / "data" / "recs.json"))
    ap.add_argument("--out", default=str(ROOT / "data" / "recs-summary.json"))
    ap.add_argument("--sources", default=os.environ.get("WU_SOURCES", "/workspace"))
    ap.add_argument("--today", help="YYYY-MM-DD (PT); default today PT")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    now = pt_now()
    today = date.fromisoformat(a.today) if a.today else now.date()
    cur = week_of(today)
    try:
        ledger = score(json.loads(Path(a.ledger).read_text()), Sources(a.sources), cur)
        out = summary(ledger, cur, now)
    except ValueError as e:
        print(f"score_recs: {e}; nothing written", file=sys.stderr)
        return 1
    if not a.dry_run:
        Path(a.ledger).write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n")
        Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    o = out["overall"]
    print(f"week {cur}: {out['total']} recs, {o['scored']} scored, {o['hits']}-{o['misses']}-{o['pushes']}, "
          f"verified {out['verified']} / unverified {out['unverified']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
