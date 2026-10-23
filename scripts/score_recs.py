#!/usr/bin/env python3
"""Score Eddie's recommendation ledger (data/recs.json) and write the War Room summary (data/recs-summary.json).

Points only come from real Fantrax scrape files in --sources (default /workspace):
  1. fantrax-week{W}-box-details-*.json  (starters, any team)
  2. fantrax-*.json with a week{W}Fpts / wk{W}Fpts number on a roster row, or a Fantrax note
     "N pts if started" on a row in a scrape taken during week W
  3. an entry's "delta": {name: [before_file, after_file]} -> season fpts difference between two scrapes
A side with no real source stays null. A rec is scored only when both sides have points; it is
VERIFIED only when both came from a source file. Nothing is estimated.

Each side gets a basis: box_score (Fantrax box score / roster week points), fantrax_note (Fantrax "N pts if
started" on a bench player), derived (season-points delta between two scrapes) or inferred (the alternative was
not named in the call). A call is VERIFIED only when both sides are box_score/fantrax_note and nothing is
inferred; the headline hit rate counts only those.

Privacy (fail closed: exit 1, nothing written):
  - every rec must be from a PAST week (current-week recs are rejected before any processing), with an int week,
    a date in that week or the week before and not after today, a finished decision, and only known keys;
  - every string (recs and learning notes, NFKC-folded, zero-width removed, non-Latin letters rejected) is
    checked for pending/claim/bid/offer wording;
  - the same pending-name gate as warroom.json (warroom_common.resolve_pending + pending_names on the newest
    raw Fantrax scrape and the private name list): any unresolved pending move, including our own pending count
    with no names, stops the run; any rec or note naming a pending player is dropped, then
    scrub_pending_names runs over the whole output.
"""
import argparse, glob, json, os, re, sys, unicodedata
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import warroom_common as wc
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEASON_START = date(2026, 9, 10)
TYPES = ("waiver_add", "start_sit", "trade", "faab", "green_dot")
DONE = ("completed", "past")
PENDING_RE = re.compile(r"pend|queue|await|submit|propos|outstanding|in review|processe?s|processing|\bplaced\b"
                        r"|\bruns?\s+(?:mon|tue|wed|thu|fri|sat|sun|tonight|tomorrow)|\bclaim\s+in\b|no reply|\bcounter"
                        r"|\boffer(?:ed|s|ing)?\b|\bnot yet\b|\bthis week\b|\buntil\s+(?:mon|tue|wed|thu|fri|sat|sun)", re.I)
REC_KEYS = {"id", "date", "week", "type", "player", "call", "alternative", "reason", "decision", "delta", "alt_inferred",
            "status", "result", "pts_player", "pts_alt", "verified", "source", "basis", "basis_player", "basis_alt"}
NOTE_KEYS = {"week", "note", "adjustment"}
TOP_KEYS = {"schemaVersion", "team", "note", "recs", "learning"}
VERIFIED_BASES = ("box_score", "fantrax_note")
PRIVATE_PENDING = os.environ.get("WARROOM_PENDING_NAMES") or "/workspace/eddie-private/pending-names.json"


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
        """(pts, source_file, basis) or (None, None, None)."""
        key = norm(player)
        for f in sorted(glob.glob(str(self.dir / f"fantrax-week{week}-box-details-*.json"))):
            d = self.doc(os.path.basename(f))
            if not isinstance(d, dict) or d.get("week") != week:
                continue
            for row in _rows(d.get("matchups")):
                if norm(_name(row)) == key and _num(row.get("pts")) is not None:
                    return _num(row["pts"]), os.path.basename(f), "box_score"
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
                        return _num(row[k]), os.path.basename(f), "box_score"
                if sd and week_of(sd) == week:
                    note = " ".join(str(row.get(k) or "") for k in ("note", "notes"))
                    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:fpts|pts)\s+if started", note, re.I)
                    if m:
                        return float(m[1]), os.path.basename(f), "fantrax_note"
        if delta and player in delta:
            a, b = delta[player]
            da, db = self.doc(a), self.doc(b)
            if da and db and _scrape_date(da) and _scrape_date(db) and week_of(_scrape_date(db)) == week:
                fa = [_num(r.get("fpts")) for r in _rows(da) if norm(_name(r)) == key and _num(r.get("fpts")) is not None]
                fb = [_num(r.get("fpts")) for r in _rows(db) if norm(_name(r)) == key and _num(r.get("fpts")) is not None]
                if len(set(fa)) == 1 and len(set(fb)) == 1 and fb[0] >= fa[0]:
                    return fb[0] - fa[0], f"{b} minus {a} (season fpts)", "derived"
        return None, None, None


def _texts(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield str(k)
            yield from _texts(v)
    elif isinstance(o, list):
        for v in o:
            yield from _texts(v)


def text_hit(t):
    """Pending-like wording after NFKC fold + zero-width removal; any non-Latin letter fails closed."""
    if wc.non_latin(t):
        return True
    f = wc.fold(t)
    return bool(PENDING_RE.search(f) or wc.general_text_hit(t) or wc.strict_text_hit(t))


def check_ledger(ledger, cur_week, today):
    """Raises ValueError before any scoring if a rec or note can't be published."""
    if not isinstance(ledger, dict) or set(ledger) - TOP_KEYS or not isinstance(ledger.get("recs"), list):
        raise ValueError("ledger: bad top-level shape or unknown key")
    for r in ledger["recs"]:
        rid = r.get("id") if isinstance(r, dict) else None
        if not isinstance(r, dict) or set(r) - REC_KEYS:
            raise ValueError(f"{rid}: unknown field(s) {sorted(set(r) - REC_KEYS) if isinstance(r, dict) else r}")
        wk = r.get("week")
        if type(wk) is not int or wk < 1:
            raise ValueError(f"{rid}: week must be an int")
        if wk >= cur_week:
            raise ValueError(f"{rid}: week {wk} is not past (current week {cur_week})")
        try:
            d = date.fromisoformat(str(r.get("date")))
        except ValueError:
            raise ValueError(f"{rid}: bad date")
        if d > today or week_of(d) not in (wk - 1, wk):
            raise ValueError(f"{rid}: date {d} does not match week {wk}")
        if r.get("type") not in TYPES:
            raise ValueError(f"{rid}: unknown type {r.get('type')}")
        if r.get("decision") not in DONE:
            raise ValueError(f"{rid}: decision must be completed/past")
        if r.get("alt_inferred") not in (None, True, False):
            raise ValueError(f"{rid}: alt_inferred must be a boolean")
        for t in _texts({k: v for k, v in r.items() if k not in ("delta", "source")}):
            if text_hit(t):
                raise ValueError(f"{rid}: pending-like text {t!r}")
    for n in ledger.get("learning") or []:
        if not isinstance(n, dict) or set(n) - NOTE_KEYS or type(n.get("week")) is not int:
            raise ValueError(f"learning: bad note {n!r}")
        if n["week"] >= cur_week:
            raise ValueError(f"learning: week {n['week']} is not past")
        for t in _texts(n):
            if text_hit(t):
                raise ValueError(f"learning W{n['week']}: pending-like text {t!r}")


def eligible(rec, cur_week):
    check_ledger({"recs": [rec]}, cur_week, SEASON_START + timedelta(days=7 * cur_week))
    return True


def score(ledger, src, cur_week):
    for r in ledger["recs"]:
        pp, sp, bp = src.lookup(r["week"], r["player"], r.get("delta"))
        pa, sa, ba = (src.lookup(r["week"], r["alternative"], r.get("delta")) if r.get("alternative") else (None, None, None))
        if r.get("alt_inferred") and ba:
            ba = "inferred"
        if pp is None and r.get("status") == "scored" and r.get("verified") == "VERIFIED":
            continue  # source files not on this machine: keep the earlier verified score
        r["pts_player"], r["pts_alt"], r["basis_player"], r["basis_alt"] = pp, pa, bp, ba
        if pp is not None and pa is not None:
            order = ["box_score", "fantrax_note", "derived", "inferred"]
            r["basis"] = max((bp, ba), key=order.index)
            r["status"] = "scored"
            r["result"] = "hit" if pp > pa else "miss" if pp < pa else "push"
            r["verified"] = "VERIFIED" if r["basis"] in VERIFIED_BASES else "UNVERIFIED"
            r["source"] = "; ".join(sorted({sp, sa}))
        else:
            r["status"], r["result"], r["verified"], r["basis"] = "open", None, "UNVERIFIED", None
            missing = [n for n, v in ((r["player"], pp), (r.get("alternative") or "no alternative named", pa)) if v is None]
            r["source"] = (sp + "; " if sp else "") + "no real points for " + ", ".join(missing)
    return ledger


def summary(ledger, cur_week, now):
    pub = list(ledger["recs"])
    scored = [r for r in pub if r.get("status") == "scored"]
    ver = [r for r in scored if r.get("verified") == "VERIFIED"]
    def rate(rs):
        h = sum(r["result"] == "hit" for r in rs); m = sum(r["result"] == "miss" for r in rs)
        return {"hits": h, "misses": m, "pushes": len(rs) - h - m, "scored": len(rs),
                "hitRate": round(h / (h + m), 3) if h + m else None}
    by_type = {}
    for t in TYPES:
        by_type[t] = rate([r for r in ver if r["type"] == t])
        by_type[t]["all"] = rate([r for r in scored if r["type"] == t])
        by_type[t]["total"] = sum(r["type"] == t for r in pub)
    keyed = sorted(scored, key=lambda r: (r["pts_player"] - r["pts_alt"], r["id"]))
    slim = lambda r: {k: r.get(k) for k in ("id", "date", "week", "type", "player", "call", "alternative", "reason", "status",
                                            "result", "pts_player", "pts_alt", "verified", "basis", "basis_player",
                                            "basis_alt", "source")}
    notes = sorted(ledger.get("learning", []), key=lambda n: n["week"])
    return {
        "generatedAt": now.isoformat(timespec="minutes"), "week": cur_week,
        "overall": rate(ver), "overallAll": rate(scored), "total": len(pub),
        "verified": len(ver), "unverified": len(pub) - len(ver),
        "byType": by_type,
        "best": [slim(r) for r in reversed(keyed[-3:]) if r["result"] == "hit"],
        "worst": [slim(r) for r in keyed[:3] if r["result"] == "miss"],
        "latestLearning": notes[-1] if notes else None,
        "recs": [slim(r) for r in pub],
    }


def pending_gate(ledger, raw, raw_name, names_path, today):
    """warroom.json's gate: fail closed on unresolved pending moves (incl. our own count); drop recs/notes naming a
    pending player. Returns the names found."""
    try:
        wc.check_raw_source(raw, raw_name)
        names = wc.pending_names(raw, None) + wc.resolve_pending(raw, names_path, today)
    except wc.PendingError as e:
        raise ValueError(str(e))
    if not names:
        return []
    rx = wc._name_rx(names)
    if rx is None:
        return names
    hit = lambda o: any(rx.search(wc.fold(t).lower()) for t in _texts(o))
    ledger["recs"] = [r for r in ledger["recs"] if not hit({k: v for k, v in r.items() if k != "source"})]
    ledger["learning"] = [n for n in ledger.get("learning") or [] if not hit(n)]
    return names


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=str(ROOT / "data" / "recs.json"))
    ap.add_argument("--out", default=str(ROOT / "data" / "recs-summary.json"))
    ap.add_argument("--sources", default=os.environ.get("WU_SOURCES", "/workspace"))
    ap.add_argument("--raw-glob", default="/workspace/fantrax-raw-*.json")
    ap.add_argument("--pending-names", default=PRIVATE_PENDING, help="private pending-name list (never published)")
    ap.add_argument("--today", help="YYYY-MM-DD (PT); default today PT")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    now = pt_now()
    today = date.fromisoformat(a.today) if a.today else now.date()
    cur = week_of(today)
    try:
        ledger = json.loads(Path(a.ledger).read_text())
        check_ledger(ledger, cur, today)
        rawf, raw, _ = wc.latest(a.raw_glob, "rosters")
        if raw is None:
            raise ValueError("no raw Fantrax scrape, so the pending gate can't run")
        names = pending_gate(ledger, raw, rawf.name, a.pending_names, today)
        ledger = score(ledger, Sources(a.sources), cur)
        out = summary(ledger, cur, now)
        if names:
            out, _ = wc.scrub_pending_names(out, names)
        for t in _texts(out):
            if wc.non_latin(t):
                raise ValueError(f"non-Latin text in output {t!r}")
    except (ValueError, OSError) as e:
        print(f"score_recs: {e}; nothing written", file=sys.stderr)
        return 1
    if not a.dry_run:
        Path(a.ledger).write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n")
        Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    o, oa = out["overall"], out["overallAll"]
    print(f"week {cur}: {out['total']} recs; verified {o['hits']}-{o['misses']}-{o['pushes']}; "
          f"all scored {oa['hits']}-{oa['misses']}-{oa['pushes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
