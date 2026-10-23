"""Shared helpers for the War Room refresh scripts.
Week math, PT stamps, FAIL-CLOSED exclude lists with robust identity matching, the deny-pending gate,
and "newest Fantrax file by scrape timestamp"."""
import json, re, unicodedata
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
PT = ZoneInfo("America/Los_Angeles")
WEEK1 = date(2026, 9, 10)  # Thursday; weeks run Thu-Wed

class ListError(Exception): pass
class PendingError(Exception): pass

def now_pt():
    return datetime.now(PT).replace(second=0, microsecond=0)

class AmbiguousTime(ValueError): pass

def localize_pt(naive):
    """Attach PT to a naive time. Ambiguous (Nov 1 1:00-1:59 AM, happens twice) or nonexistent
    (spring-forward gap) wall times raise AmbiguousTime: give an explicit offset instead."""
    a, b = naive.replace(tzinfo=PT, fold=0), naive.replace(tzinfo=PT, fold=1)
    if a.utcoffset() != b.utcoffset():
        raise AmbiguousTime(f"{naive.isoformat()} is ambiguous or nonexistent in PT; pass an explicit offset (-07:00 or -08:00)")
    return a

def parse_now(s):
    """--now override. A value with no offset is read as PT (not the box's zone); ambiguous DST times fail."""
    dt = datetime.fromisoformat(s)
    return (localize_pt(dt) if dt.tzinfo is None else dt).astimezone(PT)

def iso_pt(dt=None):
    return (dt or now_pt()).astimezone(PT).replace(microsecond=0).isoformat()

def week_for(d):
    """week = 1 + floor((date_PT - Sep 10 2026) / 7)."""
    if isinstance(d, datetime):
        d = d.astimezone(PT).date()
    return 1 + (d - WEEK1).days // 7

# ---------- identity matching ----------
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
POS_TEAM = r"(?:QB|RB|WR|TE|K|DL|DE|DT|EDGE|LB|ILB|OLB|DB|CB|S|FS|SS|[A-Z]{2,3})"
def clean_name(n):
    """Strip decorations before matching: '(GB)', '(LB, GB)', ' - LB GB', ' – GB', 'E.Cooper' -> 'E. Cooper'."""
    n = unicodedata.normalize("NFKC", str(n or "")).replace("\u00a0", " ")
    n = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", " ", n)                                      # (GB) / [LB-GB]
    n = re.sub(r"\s+[-\u2013\u2014|/]\s+.*$", "", n)                                    # ' - LB GB'
    n = re.sub(r"(?:[\s,]+" + POS_TEAM + r")+\s*$", lambda m: "" if len(n[:m.start()].split()) >= 2 else m.group(0), n)  # trailing 'LB GB'
    n = re.sub(r"\b([A-Za-z])\.(?=[A-Za-z]{2,})", r"\1. ", n)                          # E.Cooper -> E. Cooper
    return n

def norm(n):
    n = clean_name(n)
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"['\u2019`]", "", n)            # D'Marco -> dmarco
    n = re.sub(r"(?<=\b[a-z])\.(?=[a-z]\b)", "", n)  # d.j -> dj
    n = n.replace(".", "")
    n = re.sub(r"[^a-z0-9, ]+", " ", n)          # collapse other punctuation (hyphens etc.)
    n = SUFFIX.sub("", n)
    return " ".join(n.replace(",", " , ").split()).replace(" , ", ", ").strip(" ,")

def name_keys(name):
    """Keys for a name: full normalized form, 'Last, First' reordered, and first-initial+last ('e cooper')."""
    if not name or not str(name).strip():
        return set()
    raw = clean_name(name)
    forms = [raw]
    if "," in raw:
        last, _, first = raw.partition(",")
        forms.append(f"{first} {last}")
    keys = set()
    for f in forms:
        n = norm(f)
        if not n:
            continue
        keys.add("n:" + n)
        parts = n.split()
        if len(parts) >= 2:
            keys.add(f"i:{parts[0][0]}|{parts[-1]}")
    return keys

ID_FIELDS = ("id", "playerId", "fantraxId", "fantrax_id", "player_id")
def rec_ids(r):
    return {"id:" + str(r[k]).strip().lower() for k in ID_FIELDS if isinstance(r, dict) and r.get(k) not in (None, "")}

def rec_keys(r):
    """Identity keys for a rec/FA row (dict) or a bare name."""
    if isinstance(r, str):
        return name_keys(r)
    nm = r.get("player") or r.get("name")
    return rec_ids(r) | name_keys(nm)

# Seed floor: these must always be on the season-ending list. A wiped or truncated list fails the run.
REQUIRED_SEASON_ENDING = ({"name": "Edgerrin Cooper", "team": "GB"},)

def _load_list(path, kind, allow_empty=False):
    p = Path(path)
    if not p.exists():
        raise ListError(f"{kind} list missing: {p} (fail closed)")
    try:
        d = json.loads(p.read_text())
    except Exception as e:
        raise ListError(f"{kind} list is not valid JSON: {p}: {e}")
    pl = d.get("players") if isinstance(d, dict) else None
    if not isinstance(pl, list):
        raise ListError(f"{kind} list has no 'players' array: {p}")
    if not pl and not allow_empty:
        raise ListError(f"{kind} list is empty: {p} (fail closed)")
    for i, e in enumerate(pl):
        if not isinstance(e, dict) or not (isinstance(e.get("name"), str) and e["name"].strip() or e.get("ids") or e.get("id")):
            raise ListError(f"{kind} list entry {i} has neither a name nor an id: {p}")
    return pl

def _entry_keys(e):
    k = name_keys(e.get("name"))
    for a in e.get("aliases") or []:
        k |= name_keys(a)
    ids = list(e.get("ids") or []) + ([e["id"]] if e.get("id") else [])
    k |= {"id:" + str(i).strip().lower() for i in ids}
    return k

TEAM_CODES = {"ari", "atl", "bal", "buf", "car", "chi", "cin", "cle", "dal", "den", "det", "gb", "gnb", "hou", "ind",
              "jax", "jac", "kc", "kan", "lv", "lvr", "lac", "lar", "la", "mia", "min", "ne", "nwe", "no", "nor", "nyg",
              "nyj", "phi", "pit", "sf", "sfo", "sea", "tb", "tam", "ten", "was", "wsh", "fa"}
POS_CODES = {"qb", "rb", "wr", "te", "dl", "de", "dt", "edge", "lb", "ilb", "olb", "mlb", "db", "cb", "fs", "ss", "saf",
             "idp", "flex", "ir", "pup", "nfi", "res", "sus", "out", "dnp", "bn", "def", "dst"}
NAME_SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}

def name_tokens(name):
    """Letter-only tokens. Split on ANY non-letter (|, comma, period, parens, dash, digits, spaces); apostrophes are
    removed first so Ja'Marr stays one token. Known team/position/status codes and Jr./III suffixes are dropped
    (multi-letter codes only; single letters are kept as initials)."""
    n = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"['`]", "", n.replace("\u2019", "'"))
    toks = re.findall(r"[a-z]+", n)
    return [t for t in toks if not (len(t) > 1 and (t in TEAM_CODES or t in POS_CODES or t in NAME_SUFFIX))]

class Excluder:
    """Token matching. An entry {first ... last} matches a rec when
    (a) the rec's tokens equal {first, last} as a multiset, in any order, or
    (b) the rec's tokens contain last AND (first OR first-initial as a lone letter).
    Ids match too. Darius/Amari/Eric Cooper and Cooper DeJean do not match Edgerrin Cooper."""
    def __init__(self, entries):
        self.entries = []
        for e in entries:
            names = [e.get("name")] + list(e.get("aliases") or [])
            ids = {str(x).strip().lower() for x in list(e.get("ids") or []) + ([e["id"]] if e.get("id") else [])}
            fl = []
            for nm in names:
                t = name_tokens(nm)
                if len(t) >= 2:
                    fl.append((t[0], t[-1]))
                    if "," in str(nm):   # 'Cooper, Edgerrin' entry form
                        fl.append((t[-1], t[0]))
            self.entries.append((fl, ids))
    def match(self, r):
        nm = r if isinstance(r, str) else (r.get("player") or r.get("name") if isinstance(r, dict) else None)
        toks = name_tokens(nm)
        rid = {i[3:] for i in rec_ids(r)} if isinstance(r, dict) else set()
        from collections import Counter
        tc = Counter(toks)
        for fl, ids in self.entries:
            if rid & ids:
                return True
            for first, last in fl:
                if tc == Counter([first, last]):
                    return True
                if last in tc and (first in tc or (first[0] in tc and tc[first[0]] >= 1 and len(first) > 1)):
                    if last != first or tc[last] >= 2:
                        return True
        return False

def season_ending(data_dir):
    pl = _load_list(Path(data_dir) / "season-ending.json", "season-ending")
    ex = Excluder(pl)
    missing = [r["name"] for r in REQUIRED_SEASON_ENDING if not ex.match(r["name"])]
    if missing:
        raise ListError(f"season-ending list is missing required seed entries {missing} (fail closed)")
    return ex

def do_not_pitch(data_dir, week, today=None):
    today = today or now_pt().date()
    keep = []
    # do-not-pitch MAY be empty, but only as an explicit valid object: {"players": []}.
    for p in _load_list(Path(data_dir) / "do-not-pitch.json", "do-not-pitch", allow_empty=True):
        wk = p.get("weeks")
        if wk is not None and week not in wk:
            continue
        if p.get("until") and date.fromisoformat(p["until"]) < today:
            continue
        keep.append(p)
    return Excluder(keep)

def identifiable(r):
    """A rec is publishable only with a real player name (at least 2 letter tokens). Id-only or null-name recs are
    blocked, because without a name we cannot prove they are not on an exclude list whose entry has no id."""
    nm = r if isinstance(r, str) else (r.get("player") or r.get("name") if isinstance(r, dict) else None)
    return len(name_tokens(nm)) >= 2

# ---------- deny-pending gate ----------
# --- strict (fail-closed) sections: allowlisted keys + allowlisted status values only ---
STRICT_SECTIONS = {"waivers", "trades", "drops", "bids", "claims"}
STRICT_FIELDS = {
    "waivers": {"rank", "player", "pos", "nflTeam", "team", "why", "stats", "faabMin", "faabMax", "bid", "drop", "tag",
                "id", "playerId", "fantraxId", "status"},
    "drops": {"rank", "player", "pos", "nflTeam", "team", "reason", "id", "playerId", "fantraxId", "status"},
    "trades": {"with", "give", "get", "why", "status", "date", "time"},
    "bids": {"player", "pos", "team", "bid", "status", "date", "id", "playerId", "fantraxId"},
    "claims": {"player", "pos", "team", "bid", "status", "date", "id", "playerId", "fantraxId"},
}
COMPLETED = {"completed", "complete", "processed", "executed", "accepted-and-processed", "accepted and processed"}
STRICT_WORDS = re.compile(r"pend|review|counter|await|submit|outstanding|queue|propos|offer(?:ed)?\b|in.?progress", re.I)
# --- top-level schema of warroom.json; any other top-level key is unknown and fails the run ---
WARROOM_KEYS = {"schemaVersion", "sample", "asOf", "lastUpdated", "season", "week", "opponent", "freshness",
                "lockTimes", "lineup", "injuryWatch", "byes", "waivers", "drops", "trades", "idp", "boxSafety", "news",
                "fantraxRaw", "refreshNotes"}
FA_KEYS = {"sample", "asOf", "source", "players", "lastUpdated"}
FA_FIELDS = {"player", "pos", "team", "fpg", "last3Fpg", "rosteredPct", "id", "playerId", "fantraxId"}
# --- general sections: narrow rule ---
PENDING_KEY = re.compile(r"pending|claimsqueue|claims?$|bids?$|offers?$|queue|outstanding|submitted|proposal", re.I)
STATUS_KEY = re.compile(r"(status|state)$", re.I)
PENDING_VAL = re.compile(r"pend|propos|submit|queue|review|await|counter|request|process(?!ed)|offer|outstanding", re.I)
TXT_ALWAYS = re.compile(r"\bPEND\b|awaiting\s+approval|\boutstanding\s+(?:bid|claim|trade|offer)", re.I)
TXT_PEND = re.compile(r"\bpending\b", re.I)
TXT_ZERO = re.compile(r"\b(?:0|no|zero)\s+pending\b", re.I)
TXT_CTX = re.compile(r"\bbids?\b|\bclaims?\b|\btrades?\b|\bfaab\b|\boffers?\b|\$\s*\d|\bwaivers?\b", re.I)

def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield str(k); yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)

def _strict_record(sec, r, path):
    hits = []
    if not isinstance(r, dict):
        return [f"{path} (not a record)"]
    allowed = STRICT_FIELDS.get(sec, set())
    for k, v in r.items():
        if k not in allowed:
            hits.append(f"{path}.{k} (unknown key)")
        elif isinstance(v, bool) or (isinstance(v, (dict,)) ):
            hits.append(f"{path}.{k} (unexpected type)")
    st = r.get("status")
    if st is not None and " ".join(str(st).lower().replace("_", " ").split()).replace(" ", "-") not in {c.replace(" ", "-") for c in COMPLETED}:
        hits.append(f"{path}.status={st!r} (not a completed status)")
    if sec in ("bids", "claims") and st is None:
        hits.append(f"{path} (bid/claim with no completed status)")
    for t in _strings(r):
        if STRICT_WORDS.search(t):
            hits.append(f"{path}: {t[:60]!r}"); break
    return hits

def find_pending(o, path="", in_offer=False, schema="warroom"):
    """Fail-closed pending gate. Returns offending paths; empty = clean.
    STRICT (waivers/trades/drops/bids/claims): only allowlisted keys; status must be a completed value
    (bids/claims must carry one); any pending/review/counter/await/submit/outstanding/queue/propos text blocks;
    booleans/objects block. Unknown top-level keys block (so a new 'outstanding' list can't slip in).
    GENERAL (lineup, news, injuryWatch...): pending-like keys or *status values block; free text blocks on
    PEND / 'awaiting approval' anywhere, or 'pending' next to bid/claim/trade/FAAB/offer/waiver/$N."""
    hits = []
    if path == "" and isinstance(o, dict):
        top = WARROOM_KEYS if schema == "warroom" else FA_KEYS
        for k, v in o.items():
            p = f".{k}"
            if k not in top:
                hits.append(f"{p} (unknown top-level key)"); continue
            if k in STRICT_SECTIONS:
                if not isinstance(v, list):
                    hits.append(f"{p} (not a list)"); continue
                for i, r in enumerate(v):
                    hits += _strict_record(k, r, f"{p}[{i}]")
            elif schema == "fa" and k == "players":
                for i, r in enumerate(v or []):
                    bad = [x for x in (r or {}) if x not in FA_FIELDS]
                    if bad or not isinstance(r, dict):
                        hits.append(f"{p}[{i}] unknown keys {bad}")
                    elif any(STRICT_WORDS.search(t) for t in _strings(r)):
                        hits.append(f"{p}[{i}] pending-like text")
            else:
                hits += find_pending(v, p, False, schema)
        return hits
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}.{k}"
            if k != "bid" and PENDING_KEY.search(k):
                hits.append(p); continue
            if STATUS_KEY.search(k) and isinstance(v, str) and PENDING_VAL.search(v):
                hits.append(p); continue
            if isinstance(v, bool) and re.search(r"submit|pend|propos|queue|outstanding", k, re.I):
                hits.append(p); continue
            hits += find_pending(v, p, False, schema)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            hits += find_pending(v, f"{path}[{i}]", False, schema)
    elif isinstance(o, str):
        if TXT_ALWAYS.search(o):
            hits.append(path)
        elif TXT_PEND.search(o):
            rest = TXT_ZERO.sub("", o)
            if TXT_PEND.search(rest) and TXT_CTX.search(rest):
                hits.append(path)
    return hits

def assert_no_pending(o, what, schema="warroom"):
    h = find_pending(o, schema=schema)
    if h:
        raise PendingError(f"pending item(s) in {what}: {h[:10]} (run stopped, nothing written)")

def has_pending(o):
    return bool(find_pending(o))

# ---------- newest Fantrax file by scrape timestamp ----------
TZ = {"PDT": "-07:00", "PST": "-08:00", "PT": None, "CDT": "-05:00", "CST": "-06:00", "UTC": "+00:00", "Z": "+00:00"}
def scrape_time(d):
    for k in ("scrapedAt", "scraped_at", "scrape_time_PT", "asOf", "scraped"):
        v = d.get(k) if isinstance(d, dict) else None
        if not isinstance(v, str):
            continue
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return (localize_pt(dt) if dt.tzinfo is None else dt).astimezone(PT)
        except AmbiguousTime:
            return None   # ambiguous PT wall time with no offset: file is skipped
        except ValueError:
            pass
        m = re.search(r"(\d{4}-\d{2}-\d{2})\D{0,3}~?(\d{1,2}):(\d{2})\s*(AM|PM)?(?:[^A-Z]*?\b(PDT|PST|PT|CDT|CST|UTC)\b)?", v)
        if m:
            h = int(m.group(2)) % 12 + (12 if m.group(4) == "PM" else 0) if m.group(4) else int(m.group(2))
            dt = datetime.fromisoformat(f"{m.group(1)}T{h:02d}:{m.group(3)}:00")
            off = TZ.get(m.group(5) or "PT")
            if off is None:
                try:
                    dt = localize_pt(dt)
                except AmbiguousTime:
                    return None
            else:
                dt = datetime.fromisoformat(dt.isoformat() + off)
            return dt.astimezone(PT)
    return None

def latest(globpat, must_have=None, now=None):
    """Newest file matching glob by its own scrape timestamp (not its name). Files with no parseable
    timestamp, or a timestamp in the future, are skipped."""
    now = now or datetime.now(PT)
    best = (None, None, None)
    for f in Path("/").glob(globpat.lstrip("/")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if must_have and not (isinstance(d, dict) and must_have in d):
            continue
        if isinstance(d, dict) and d.get("partial"):
            continue  # partial scrapes never feed the War Room
        t = scrape_time(d)
        if t is None or t > now + timedelta(minutes=5):
            continue
        if best[2] is None or t > best[2]:
            best = (f, d, t)
    return best

def load_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text())

def write_json(p, d):
    Path(p).write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
