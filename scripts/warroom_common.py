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

class Excluder:
    """Matches on id or full normalized name; an initial-only name ('E. Cooper') matching an entry's
    initial+last is also blocked. A different full first name (Darius Cooper) is not."""
    def __init__(self, entries):
        self.entries = [(_entry_keys(e), (e.get("team") or "").upper()) for e in entries]
    def match(self, r):
        rk = rec_keys(r)
        rn = [k[2:] for k in rk if k.startswith("n:")]
        rec_initial = any(len(n.split()[0]) == 1 for n in rn if " " in n)
        for ek, _team in self.entries:
            common = rk & ek
            if any(not k.startswith("i:") for k in common):
                return True          # same id or same full (normalized / reordered) name
            if common and rec_initial:
                return True          # 'E. Cooper' vs 'Edgerrin Cooper': block (fail closed)
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
    """A rec is publishable only with a real player name. Id-only or null-name recs are blocked, because
    without a name we cannot prove they are not on an exclude list whose entry has no id."""
    nm = r if isinstance(r, str) else (r.get("player") or r.get("name") if isinstance(r, dict) else None)
    return bool(name_keys(nm))

# ---------- deny-pending gate ----------
PENDING_KEY = re.compile(r"pending|claimsqueue|claims?$|bids?$|offers?$|queue", re.I)
STATUS_KEY = re.compile(r"(status|state)$", re.I)
PENDING_VAL = {"pending", "pend", "proposed", "submitted", "claimsqueue", "claims queue", "queued", "in review",
               "awaiting", "awaiting approval", "requested", "processing", "offered"}
OFFER_ONLY_VAL = {"open"}                      # 'Open' blocks only inside trades/claims/bids/waivers
TXT_PEND = re.compile(r"\bpending\b|\bpend\b|awaiting\s+approval", re.I)
TXT_ALWAYS = re.compile(r"\bPEND\b|awaiting\s+approval", re.I)
TXT_ZERO = re.compile(r"\b(?:0|no|zero)\s+pending\b", re.I)
TXT_CTX = re.compile(r"\bbids?\b|\bclaims?\b|\btrades?\b|\bfaab\b|\boffers?\b|\$\d", re.I)
OFFER_SECTIONS = {"waivers", "trades", "bids", "claims", "drops"}

def find_pending(o, path="", in_offer=False):
    """Paths that look like pending bids/claims/trades. Empty = clean.
    - keys like pending/claimsQueue/claims/bids/offers (the rec field 'bid' is a recommendation, allowed)
    - *status/*state values pending/PEND/proposed/submitted/claimsQueue/awaiting approval... (case/space-insensitive);
      'open' only inside trades/claims/bids/waivers/drops
    - free text: 'PEND' or 'awaiting approval' anywhere; 'pending' only next to bid/claim/trade/FAAB/offer/$N
      (so 'MRI results pending' or 'Thu pending' is fine); '0 pending'/'no pending' is fine."""
    hits = []
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}.{k}"
            if k != "bid" and PENDING_KEY.search(k):
                hits.append(p); continue
            if STATUS_KEY.search(k) and isinstance(v, str):
                vv = " ".join(v.lower().split())
                if vv in PENDING_VAL or (in_offer and vv in OFFER_ONLY_VAL):
                    hits.append(p); continue
            hits += find_pending(v, p, in_offer or (path == "" and k in OFFER_SECTIONS))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            hits += find_pending(v, f"{path}[{i}]", in_offer)
    elif isinstance(o, str):
        if TXT_ALWAYS.search(o):
            hits.append(path)
        elif TXT_PEND.search(o):
            rest = TXT_ZERO.sub("", o)
            if TXT_PEND.search(rest) and TXT_CTX.search(rest):
                hits.append(path)
    return hits

def assert_no_pending(o, what):
    h = find_pending(o)
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
