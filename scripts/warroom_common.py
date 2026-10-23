"""Shared helpers for the War Room refresh scripts (week math, PT stamps, exclude lists, no-pending rule)."""
import json, re, unicodedata
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PT = timezone(timedelta(hours=-7))

WEEK1 = date(2026, 9, 10)  # Thursday; weeks run Thu-Wed

def now_pt():
    return datetime.now(PT).replace(second=0, microsecond=0)

def iso_pt(dt=None):
    return (dt or now_pt()).astimezone(PT).replace(microsecond=0).isoformat()

def week_for(d):
    """week = 1 + floor((date - Sep 10 2026) / 7)."""
    if isinstance(d, datetime):
        d = d.astimezone(PT).date()
    return 1 + (d - WEEK1).days // 7

def norm(n):
    n = unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.']", "", n).replace("-", " ")
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", n)
    return " ".join(n.split())

def load_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text())

def season_ending(data_dir):
    d = load_json(Path(data_dir) / "season-ending.json", {"players": []})
    return {norm(p["name"]) for p in d.get("players", [])}

def do_not_pitch(data_dir, week, today=None):
    today = today or now_pt().date()
    d = load_json(Path(data_dir) / "do-not-pitch.json", {"players": []})
    out = set()
    for p in d.get("players", []):
        wk = p.get("weeks")
        if wk is not None and week not in wk:
            continue
        until = p.get("until")
        if until and date.fromisoformat(until) < today:
            continue
        out.add(norm(p["name"]))
    return out

PENDING_KEY = re.compile(r"pending|claims?$|bids?$|offers?$", re.I)

def strip_pending(o):
    """No-pending rule: drop any key that looks like pending bids/claims/trades/offers, recursively.
    (The War Room 'bid' field is a recommendation, not a pending bid, and is kept.)"""
    if isinstance(o, dict):
        return {k: strip_pending(v) for k, v in o.items() if not (PENDING_KEY.search(k) and k != "bid")}
    if isinstance(o, list):
        return [strip_pending(v) for v in o if not (isinstance(v, dict) and str(v.get("status", "")).lower() == "pending")]
    return o

def has_pending(o):
    if isinstance(o, dict):
        return any((PENDING_KEY.search(k) and k != "bid") or has_pending(v) for k, v in o.items()) or str(o.get("status", "")).lower() == "pending"
    if isinstance(o, list):
        return any(has_pending(v) for v in o)
    return False

def latest(globpat, must_have=None):
    """Newest file matching glob (by name, which carries the date, then mtime) that has key must_have."""
    files = sorted(Path("/").glob(globpat.lstrip("/")), key=lambda p: (p.name, p.stat().st_mtime), reverse=True)
    for f in files:
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if must_have is None or (isinstance(d, dict) and must_have in d):
            return f, d
    return None, None

def write_json(p, d):
    Path(p).write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
