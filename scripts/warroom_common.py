"""Shared helpers for the War Room refresh scripts.
Week math, PT stamps, FAIL-CLOSED exclude lists with robust identity matching, the deny-pending gate,
and "newest Fantrax file by scrape timestamp"."""
import json, re, unicodedata
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
PT = ZoneInfo("America/Los_Angeles")
WEEK1 = date(2026, 9, 10)  # Thursday; weeks run Thu-Wed

# ---------- text normalization (round 5) ----------
# NFKC folds fullwidth/compatibility forms ('ｐｅｎｄｉｎｇ' -> 'pending'); every format char (Unicode category Cf:
# U+200B-U+200D, U+2060, U+FEFF, soft hyphen U+00AD, bidi marks...) is removed so 'pen\u200bding' -> 'pending'.
_CONFUSABLE = str.maketrans({
    # Cyrillic lookalikes
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0443": "y", "\u0445": "x",
    "\u0456": "i", "\u0458": "j", "\u0455": "s", "\u0501": "d", "\u04bb": "h", "\u043a": "k", "\u043c": "m",
    "\u043d": "h", "\u0442": "t", "\u0432": "b", "\u0457": "i", "\u0491": "r", "\u0410": "A", "\u0412": "B",
    "\u0415": "E", "\u041a": "K", "\u041c": "M", "\u041d": "H", "\u041e": "O", "\u0420": "P", "\u0421": "C",
    "\u0422": "T", "\u0425": "X", "\u0423": "Y", "\u0406": "I", "\u0408": "J", "\u0405": "S",
    # Greek lookalikes
    "\u03bf": "o", "\u03b1": "a", "\u03b5": "e", "\u03b9": "i", "\u03ba": "k", "\u03bd": "v", "\u03c1": "p",
    "\u03c4": "t", "\u03c5": "u", "\u03c7": "x", "\u0391": "A", "\u0392": "B", "\u0395": "E", "\u0396": "Z",
    "\u0397": "H", "\u0399": "I", "\u039a": "K", "\u039c": "M", "\u039d": "N", "\u039f": "O", "\u03a1": "P",
    "\u03a4": "T", "\u03a5": "Y", "\u03a7": "X",
})
def prep(s):
    """NFKC + drop every format (Cf) char + NBSP -> space. Use before ANY pending check or name match."""
    s = unicodedata.normalize("NFKC", str(s if s is not None else ""))
    return "".join(" " if ch == "\u00a0" else ch for ch in s if unicodedata.category(ch) != "Cf")

def non_latin(s):
    """True if the text has any letter that is not Latin script (Cyrillic, Greek, ...)."""
    return any(unicodedata.category(ch).startswith("L") and "LATIN" not in unicodedata.name(ch, "") for ch in prep(s))

def fold(s):
    """prep() + map Cyrillic/Greek lookalikes to Latin, so 'p\u0435nding' is read as 'pending'."""
    s = prep(s).translate(_CONFUSABLE)
    # round 6: strip accents/diacritics after NFKC ('p\u00e9nding' -> 'pending')
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", s)

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

# Real player names that contain a team/position code as a name part (KC Concepcion, Jordan van den Berg).
# Seeded here and extended from every name found in data/ (load_known_names), so those tokens are never stripped.
_KNOWN_CODE_NAMES = {("kc", "concepcion"), ("jordan", "van", "den", "berg")}
_KNOWN_LOADED = set()
# Rec/output/exclude files are not roster sources (a rec can't vouch for its own name).
KNOWN_SKIP = {"warroom.json", "free-agents.json", "season-ending.json", "do-not-pitch.json", "green-dots.json",
              "green-dots-status.json"}
NAME_FIELDS = ("player", "name", "fullName", "playerName", "greenDot")

def _raw_tokens(name):
    n = unicodedata.normalize("NFKD", prep(name)).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"['`]", "", n.replace("\u2019", "'"))
    return re.findall(r"[a-z]+", n)

def _is_code(t):
    return len(t) > 1 and (t in TEAM_CODES or t in POS_CODES)

def load_known_names(data_dir):
    """Add every real name in data_dir/**/*.json (player/name/... fields) that contains a code token."""
    d = Path(data_dir)
    if not d.is_dir() or str(d.resolve()) in _KNOWN_LOADED:
        return
    _KNOWN_LOADED.add(str(d.resolve()))
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in NAME_FIELDS and isinstance(v, str):
                    t = [x for x in _raw_tokens(re.sub(r"\([^)]*\)", " ", v)) if x not in NAME_SUFFIX]
                    if len(t) >= 2 and not non_latin(v) and any(_is_code(x) for x in t):
                        _KNOWN_CODE_NAMES.add(tuple(t))
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for f in d.rglob("*.json"):
        if f.name in KNOWN_SKIP:
            continue
        try:
            walk(json.loads(f.read_text()))
        except Exception:
            continue

def name_tokens(name):
    """Letter-only tokens. Text is prep()'d (NFKC, format chars removed) first. A name with ANY non-Latin letter
    (e.g. a Cyrillic 'о' in 'Edgerrin C\u043eoper') returns [] = unidentifiable, so it is never published.
    Split on ANY non-letter (|, comma, period, parens, dash, digits, spaces); apostrophes are removed first so
    Ja'Marr stays one token. Known team/position/status codes and Jr./III suffixes are dropped (multi-letter only;
    single letters are kept as initials) EXCEPT where the code is part of a real player's name found in data/
    (KC Concepcion keeps 'kc', Jordan van den Berg keeps 'den')."""
    if non_latin(name):
        return []
    toks = _raw_tokens(name)
    keep = set()
    for kn in _KNOWN_CODE_NAMES:
        L = len(kn)
        for i in range(len(toks) - L + 1):
            if tuple(toks[i:i + L]) == kn:
                keep |= set(range(i, i + L)); break
    return [t for i, t in enumerate(toks) if i in keep or not (len(t) > 1 and (_is_code(t) or t in NAME_SUFFIX))]

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
    load_known_names(data_dir)
    pl = _load_list(Path(data_dir) / "season-ending.json", "season-ending")
    ex = Excluder(pl)
    missing = [r["name"] for r in REQUIRED_SEASON_ENDING if not ex.match(r["name"])]
    if missing:
        raise ListError(f"season-ending list is missing required seed entries {missing} (fail closed)")
    return ex

def do_not_pitch(data_dir, week, today=None):
    today = today or now_pt().date()
    load_known_names(data_dir)
    keep = []
    # do-not-pitch MAY be empty, but only as an explicit valid object: {"players": []}.
    for p in _load_list(Path(data_dir) / "do-not-pitch.json", "do-not-pitch", allow_empty=True):
        # Bill's rule: a pass covers ONLY the fantasy week it was given. 'weeks' must contain the current week.
        # No/invalid 'weeks': applies only if 'since' falls in the current week; otherwise ignored (never forever).
        wk = p.get("weeks")
        if not (isinstance(wk, list) and wk):
            try:
                wk = [week_for(date.fromisoformat(str(p.get("since"))))]
            except (TypeError, ValueError):
                wk = []
        if week not in wk:
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
COMPLETED = {"completed"}   # round 9: exactly "completed" (after fold + strip + lower); anything else stops the run
# Free-text rules (round 5): WHOLE words / whole status phrases only, never fragments, so 'suspended', 'dependent',
# 'must-spend', 'preview', 'reviewed', 'encounter', 'queued', 'submits', 'proposition', 'countering' are fine.
# Text is fold()'ed first (NFKC, format chars removed, Cyrillic/Greek lookalikes -> Latin).
TXT_ZERO = re.compile(r"\b(?:0|no|zero|none)\s+pending\b(?:\s+(?:claims?|bids?|trades?|offers?|waivers?|moves?))?"
                      r"|\bpending\s*[:=]?\s*(?:0|none)(?:\s*/\s*0)*(?![\d.])", re.I)
NEG_OFFER = re.compile(r"\b(?:not|no|never|without|isn'?t)\s+(?:an?\s+|the\s+|any\s+)?(?:formal\s+|real\s+|actual\s+|trade\s+)?offers?\b", re.I)
STRICT_TXT = re.compile(
    r"\bpend(?:ing)?\b"                                   # pending / PEND
    r"|\bawaiting\b|\bawait(?:s|ed)?\s+(?:approval|response|acceptance|processing|league|commish|commissioner|review)\b"
    r"|\bcountered\b|\bcounter[\s_-]?offer(?:s|ed)?\b"   # Countered / counter offer / counteroffer
    r"|\bsubmitted\b"
    r"|\bpropos(?:e|es|ed|al|als|ing)\b"                  # proposed / proposal (not 'proposition')
    r"|\b(?:in|under|league|for)[\s_-]*review\b"          # in review / in_review / under review / league review
    r"|\b(?:in|on)\s+(?:the\s+)?(?:waiver\s+|claims?\s+|bid\s+)?queue\b"
    # an offer as a TRANSACTION (negated 'not an offer' removed first); the verb 'offers upside' is fine
    r"|\btrade\s+offers?\b|\boffers?\s+(?:sent|made|out|submitted|extended|open|on\s+the\s+table)\b"
    r"|\b(?:sent|send|sending|made|make|making|extend(?:ed)?|placed|got|received|accept(?:ed)?)\s+(?:an?\s+|the\s+|our\s+|his\s+)?offers?\b"
    r"|\boffered\s+(?:to|him|them|us|me|an?|\$|\d)"
    r"|\boutstanding\s+(?:bids?|claims?|trades?|offers?|waivers?|faab)\b"
    r"|\b(?:still|is|are|remains?)\s+outstanding\b|^\s*outstanding\s*$"
    # round 6: queued claim / claim queued (bare 'queued', 'queued up' still fine), pended, waiting on approval,
    # 'offer: Emerson for Lloyd' (an offer spelled out after a colon/dash)
    r"|\bqueued\s+(?:claims?|bids?|waivers?|trades?|offers?|moves?|faab|drops?|adds?)\b"
    r"|\b(?:claims?|bids?|waivers?|trades?|offers?|moves?|faab|drops?|adds?)\s+(?:is\s+|are\s+|was\s+|were\s+|still\s+|now\s+)*queued\b"
    r"|\bpended\b"
    r"|\bwaiting\s+(?:on|for)\s+(?:the\s+)?(?:approval|response|acceptance|processing|league|commish|commissioner|review)\b"
    r"|\boffers?\s*[:\u2013\u2014-]\s*\S", re.I)
# --- top-level schema of warroom.json; any other top-level key is unknown and fails the run ---
WARROOM_KEYS = {"schemaVersion", "sample", "asOf", "lastUpdated", "season", "week", "opponent", "freshness",
                "lockTimes", "lineup", "injuryWatch", "byes", "waivers", "drops", "trades", "idp", "boxSafety", "news",
                "fantraxRaw", "refreshNotes"}
FA_KEYS = {"sample", "asOf", "source", "players", "lastUpdated"}
FA_FIELDS = {"player", "pos", "team", "fpg", "last3Fpg", "rosteredPct", "id", "playerId", "fantraxId"}
# --- general sections: narrow rule ---
PENDING_KEY = re.compile(r"pending|claimsqueue|claims?$|bids?$|offers?$|queue|outstanding|submitted|proposal", re.I)
STATUS_KEY = re.compile(r"(status|state)$", re.I)
# status VALUES in general sections: word-start match (so 'Suspended' is fine, 'pending-review' / 'in_review' are not)
PENDING_VAL = re.compile(r"\b(?:pend\w*|propos\w*|submit\w*|queued?|review\w*|await\w*|counter\w*|request\w*"
                         r"|processing|offer\w*|outstanding)\b", re.I)
TXT_ALWAYS = re.compile(r"\bPEND\b|awaiting\s+approval|\boutstanding\s+(?:bid|claim|trade|offer)", re.I)
TXT_PEND = re.compile(r"\bpending\b", re.I)
# general sections only: a 'pending' whose subject is not a transaction (Greenlaw appeal pending, MRI results pending)
TXT_NONTXN = re.compile(r"\b(?:appeals?|mri|results?|tests?|scans?|x-?rays?|hearings?|rulings?|decisions?|evaluations?"
                        r"|exams?|suspensions?|reviews?|discipline)\s+(?:is\s+|are\s+|still\s+)*pending\b", re.I)
TXT_CTX = re.compile(r"\bbids?\b|\bclaims?\b|\btrades?\b|\bfaab\b|\boffers?\b|\$\s*\d|\bwaivers?\b", re.I)

def strict_text_hit(t):
    """True if free text inside a strict section reads as pending. Non-Latin letters fail closed."""
    if non_latin(t):
        return True
    t = fold(t).replace("_", " ")
    t = TXT_ZERO.sub(" ", t)
    t = NEG_OFFER.sub(" ", t)
    return bool(STRICT_TXT.search(t))

def general_text_hit(t):
    t = fold(t)
    if TXT_ALWAYS.search(t):
        return True
    # round 6: the appeal/MRI/results/review-pending exemption applies per sentence, and only when that sentence has
    # no bid/claim/trade/FAAB/offer/waiver/$ word ('trade review pending', 'claim results pending' still block).
    t = TXT_ZERO.sub(" ", t)
    rest = " ".join(s if TXT_CTX.search(s) else TXT_NONTXN.sub(" ", s) for s in re.split(r"(?<=[.;!?\n])", t))
    return bool(TXT_PEND.search(rest) and TXT_CTX.search(rest))

def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield str(k); yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)

def _status_norm(st):
    return " ".join(fold(st).lower().replace("_", " ").split()).replace(" ", "-")

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
    if "status" in r:
        st = r["status"]
        if not isinstance(st, str) or non_latin(st) or _status_norm(st) not in {c.replace(" ", "-") for c in COMPLETED}:
            hits.append(f"{path}.status={st!r} (not a completed status)")   # null / number / '' / pending ... all block
    if sec in ("bids", "claims") and r.get("status") is None:
        hits.append(f"{path} (bid/claim with no completed status)")
    for t in _strings(r):
        if strict_text_hit(t):
            hits.append(f"{path}: {t[:60]!r}"); break
    return hits

def find_pending(o, path="", in_offer=False, schema="warroom"):
    """Fail-closed pending gate. Returns offending paths; empty = clean.
    STRICT (waivers/trades/drops/bids/claims): only allowlisted keys; a status key must hold a completed value
    (null/number/'' block; bids/claims must carry one); free text blocks on whole pending words/phrases
    (pending, PEND, awaiting, Countered, counter offer, submitted, proposed/proposal, in/under review, in queue,
    an offer that is not negated, outstanding bid/claim...) but NOT on fragments (suspended, dependent, preview,
    reviewed, encounter, queued, submits, proposition) or on '0 pending' / 'no pending' / 'pending 0/0';
    any non-Latin letter blocks; booleans/objects block. Unknown top-level keys block.
    GENERAL (lineup, news, injuryWatch...): pending-like keys block; *status/*state values block when they are
    not strings (numbers, booleans, lists) or start a pending word; free text blocks on PEND / 'awaiting approval'
    anywhere, or 'pending' next to bid/claim/trade/FAAB/offer/waiver/$N (appeal/MRI/results pending is fine).
    All text is NFKC-normalized, format chars removed and Cyrillic/Greek lookalikes folded before matching."""
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
                    elif any(strict_text_hit(t) for t in _strings(r)):
                        hits.append(f"{p}[{i}] pending-like text")
            else:
                hits += find_pending(v, p, False, schema)
        return hits
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}.{k}"
            fk = fold(k)
            if fk != "bid" and PENDING_KEY.search(fk):
                hits.append(p); continue
            if STATUS_KEY.search(fk):
                if isinstance(v, str) and PENDING_VAL.search(fold(v).replace("_", " ").replace("-", " ")):
                    hits.append(p); continue
                if (v is None or (isinstance(v, str) and not fold(v).strip())) and re.match(r"\.(lineup|news)\b", path):
                    hits.append(f"{p} (null/empty status)"); continue   # round 6: lineup/news status must be set
                if v is not None and not isinstance(v, str):
                    hits.append(f"{p} (non-string status)"); continue
            if isinstance(v, bool) and re.search(r"submit|pend|propos|queue|outstanding", fk, re.I):
                hits.append(p); continue
            hits += find_pending(v, p, False, schema)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            hits += find_pending(v, f"{path}[{i}]", False, schema)
    elif isinstance(o, str):
        if general_text_hit(o):
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

# ---------- round 8: own-team move scrub (drop, don't fail) ----------
# Our own moves publish ONLY from structured records with a completed status (strict sections above). Free text is
# never trusted to describe them. A free-text sentence is DROPPED (the refresh continues) when, after fold():
#  1. it names us (Eddie / Eddies / Eddie's / Eagle Ridge / ERE / we / us / our / my / me / I / you) AND a move word or $N;
#  2. it has a move word or $N AND an unfinished word (pending, awaiting, proposed, waiting, queued, submitted,
#     request, counter, not yet, in progress, targeting, pitched, will, going to, planned) - whoever the subject;
#  3. it has a move word or $N AND an in-flight verb (placed, put, sent, processes, runs, is in, '$N on', filed,
#     lodged, entered) - unless another league team / owner / 'they' / 'nobody' / 'league' is the sentence subject.
# Other teams' finished moves stay. A news item whose text is fully dropped is removed.
OWN = re.compile(r"\b(?:eddies?|eddie'?s|eagle\s+ridge|ere|we|us|our|ours|my|me|i|you|your)\b", re.I)
MOVE = re.compile(r"\$\s*\d|\b(?:add(?:s|ed|ing)?|pick(?:s|ed|ing)?\s*-?\s*ups?|pickups?|deals?|drop(?:s|ped|ping)?"
                  r"|bid\w*|claim\w*|trad(?:e|es|ed|ing)|offer\w*|faab|waiv\w*|acquir\w*|swap\w*)\b"
                  r"|\b\w+-for-\w+\b", re.I)                                  # 'Lloyd-for-Emerson'

UNFINISHED = re.compile(r"\b(?:(?:not|never|\w+n't)\s+(?:\w+\s+){0,2}?(?:processed|accepted|approved|completed?|done|final|through|cleared)|pend\w*|await\w*|propos\w*|waiting|queue\w*|submit\w*|request\w*|counter\w*|not\s+yet"
                        r"|in\s+progress|targeting|pitch\w*|will|going\s+to|planned)\b", re.I)
IN_FLIGHT = re.compile(r"\b(?:plac(?:e|ed|es|ing)|put|puts|sent|send\w*|process(?:es|ing)?|runs?|is\s+in|are\s+in"
                       r"|filed|lodged|entered|out\s+to)\b|\$\s*\d+\s+on\b|\bbid\w*\s+on\b", re.I)
# a '.' right after a single capital letter (initials: 'D. Reed', 'J. Cooper') does not end a sentence
SENTENCE = re.compile(r"(?:\b(?:[A-Z]|Jr|Sr|St|Mr|Mrs|Ms|Dr|vs)\.|[^.;!?\n\r\u2028\u2029\u2026])+[.;!?\n\r\u2028\u2029\u2026]*|[.;!?\n\r\u2028\u2029\u2026]+")
SCRUB_SKIP_SECTIONS = {"schemaVersion", "sample", "asOf", "lastUpdated", "season", "week", "freshness", "lockTimes",
                       "byes", "fantraxRaw", "refreshNotes"}
SCRUB_SKIP_KEYS = {"player", "pos", "nflTeam", "team", "id", "playerId", "fantraxId", "date",
                   "time", "status", "faabMin", "faabMax", "bid", "rank", "opponent", "url", "href",
                   "verdict", "slot"}
_OTHER = {}

def other_teams(data_dir=None):
    """Words that name another league team as a sentence subject: team ids (substation, morningside...), owners'
    first/last names (Nathan, Kelly...) from data/hq/teams.json, plus they/nobody/league. Upper-case abbrevs
    (SUB, LAB, TTA) are matched case-sensitively in own_move_sentence. Generic name words (Top, Old...) are not used."""
    from pathlib import Path
    p = Path(data_dir or Path(__file__).resolve().parent.parent / "data") / "hq" / "teams.json"
    if str(p) not in _OTHER:
        s, ab = {"they", "nobody", "league"}, set()
        try:
            for t in json.loads(p.read_text()).get("teams", []):
                if t.get("id") == "eddies":
                    continue
                for v in (t.get("id"), t.get("owner")):
                    if isinstance(v, str):
                        s.update(re.findall(r"[a-z]{3,}", fold(v).lower()))
                if isinstance(t.get("abbrev"), str):
                    ab.add(fold(t["abbrev"]).upper())
        except Exception:
            pass
        _OTHER[str(p)] = (s, ab)
    return _OTHER[str(p)]

def own_move_sentence(s, data_dir=None):
    f = TXT_ZERO.sub(" ", fold(s))                        # '0 pending claims' / 'pending 0/0' is not unfinished
    if not MOVE.search(f):
        return False
    if OWN.search(f) or UNFINISHED.search(f):
        return True
    if IN_FLIGHT.search(f):
        body = re.sub(r"^\s*[^:]{0,40}:\s*", "", f)                  # 'League moves: Saltese ...' -> 'Saltese ...'
        first = re.findall(r"[A-Za-z]+", body)[:1]
        words, abbrevs = other_teams(data_dir)
        return not (first and (first[0].lower() in words or first[0] in abbrevs))
    return False

def scrub_text(t, data_dir=None):
    """Returns (kept text, dropped sentences)."""
    kept, dropped, after_drop = [], [], False
    for m in SENTENCE.finditer(t):
        sen = m.group(0)
        if own_move_sentence(sen, data_dir) or (after_drop and ORPHAN.match(fold(sen))):
            dropped.append(sen); after_drop = True      # round 9: an orphan 'Processes Wed.' after a drop goes too
        else:
            kept.append(sen); after_drop = False
    return "".join(kept).strip(), [d.strip() for d in dropped]

def scrub_own_moves(w, data_dir=None):
    """Round 8: drop own-team move text from free text. Returns (new warroom dict, [(path, dropped sentence)])."""
    log = []
    def walk(o, path):
        if isinstance(o, str):
            k, d = scrub_text(o, data_dir)
            log.extend((path, x) for x in d)
            return k
        if isinstance(o, dict):
            out = {}
            for key, v in o.items():
                if isinstance(key, str) and any(own_move_sentence(m.group(0), data_dir) for m in SENTENCE.finditer(key)):
                    log.append((f"{path}.{key}", "(key)")); continue     # round 9: keys are text too
                out[key] = v if key in SCRUB_SKIP_KEYS else walk(v, f"{path}.{key}")
            return out
        if isinstance(o, list):
            out = []
            for i, v in enumerate(o):
                nv = walk(v, f"{path}[{i}]")
                if (isinstance(v, str) and v.strip() and not nv) or (
                        isinstance(v, dict) and isinstance(v.get("text"), str) and v["text"].strip() and not nv.get("text")):
                    continue                                   # whole line dropped
                out.append(nv)
            return out
        return o
    if not isinstance(w, dict):
        return w, log
    return {k: (v if k in SCRUB_SKIP_SECTIONS else walk(v, f".{k}")) for k, v in w.items()}, log


# ---------- round 9: input-side rules + private pending-name safety net ----------
MOVE_SECTIONS = ("trades", "bids", "claims", "drops")
PENDING_SOURCE = re.compile(r"pending|claims?[\s_-]*queue|trade[\s_-]*offers?|/offers?\b|/claims?\b|/bids?\b|proposal", re.I)

def completed_past(r, today):
    """A move record counts as done only with status exactly 'completed' AND a date strictly before today (PT)."""
    if not isinstance(r, dict) or _status_norm(str(r.get("status", ""))) != "completed":
        return False
    try:
        d = datetime.fromisoformat(str(r.get("date") or "")[:10]).date()
    except ValueError:
        return False                                   # missing / bad date = not completed
    return d < today

def ingest_moves(w, today):
    """Round 9 INPUT rule: a move record that carries a status is ingested only if completed_past(); else excluded.
    (Non-completed statuses already stop the run in the pending gate; this removes completed-but-future/undated.)
    Returns (plan, excluded count)."""
    out, n = dict(w), 0
    for sec in MOVE_SECTIONS:
        v = out.get(sec)
        if isinstance(v, list):
            keep = [r for r in v if not (isinstance(r, dict) and "status" in r) or completed_past(r, today)]
            n += len(v) - len(keep)
            out[sec] = keep
    return out, n

def check_raw_source(raw, raw_name=None):
    """Round 9 hard fail: a Fantrax input that IS a pending / claim-queue / trade-offer page or file stops the run.
    (Only the week header and scrape stamp are ever ingested from a roster scrape; its other keys are not read.)"""
    if not isinstance(raw, dict):
        return
    for label, v in (("file", raw_name), ("url", raw.get("url")), ("page", raw.get("page")), ("source", raw.get("source"))):
        if isinstance(v, str) and PENDING_SOURCE.search(fold(v)):
            raise PendingError(f"Fantrax input {label} {v!r} is a pending/claims/offers source (run stopped, nothing written)")

def pending_names(raw=None, path=None):
    """Private pending-name list: players in our current pending claims/bids/offers. Read from the raw scrape's
    private fields (eddies_pending_private, eddies_pending_names) and an optional private JSON file (list of names or
    {"names": [...]}) that lives OUTSIDE the repo. Never written to data/."""
    names = []
    def add(x):
        if isinstance(x, str) and x.strip():
            names.append(x)
        elif isinstance(x, dict):
            for k in ("player", "name", "add", "get", "drop", "give"):
                v = x.get(k)
                for y in (v if isinstance(v, list) else [v]):
                    add(y)
        elif isinstance(x, list):
            for y in x: add(y)
    if isinstance(raw, dict):
        for src in (raw, raw.get("trades") if isinstance(raw.get("trades"), dict) else {}):
            for k in ("eddies_pending_private", "eddies_pending_names"):
                add(src.get(k))
    if path:
        try:
            d = json.loads(open(path).read())
            add(d.get("names") if isinstance(d, dict) and "names" in d else d)
        except FileNotFoundError:
            pass
    return names

COUNT_KEY = re.compile(r"pending.*count|count.*pending", re.I)
# round 10: any numeric-ish field whose key names pending / claims / queue / num counts (pendingClaims, numPending...)
COUNT_ANY = re.compile(r"pending|claims?|queue|num|waiting", re.I)

def _num(v):
    """int for ints/floats/numeric strings, 1 for True, else None."""
    if v is True:
        return 1
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str) and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", v):
        v = float(v)
    if isinstance(v, (int, float)):
        import math
        return math.ceil(v) if v > 0 else (0 if v == 0 else None)   # round 11: any > 0 counts as at least 1
    return None

def pending_count(raw=None, path=None):
    """Highest pending count field anywhere in the raw scrape or the private file's counts. Keys matching
    pending/claims/queue/num with an int, float, numeric string or True (=1) count; None/False/text are ignored."""
    best = 0
    def walk(o):
        nonlocal best
        if isinstance(o, dict):
            for k, v in o.items():
                n = _num(v) if isinstance(k, str) and COUNT_ANY.search(k) else None
                if n is not None:
                    best = max(best, n)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(raw)
    if path:
        try:
            d = json.loads(open(path).read())
            walk(d.get("counts") if isinstance(d, dict) else None)
        except (OSError, ValueError):
            pass
    return best

def _name_rx(names):
    pats = set()
    for n in names:
        toks = re.findall(r"[a-z][a-z'-]+", fold(n).lower())
        if not toks:
            continue
        pats.add(r"\s+".join(map(re.escape, toks)))
        last = [t for t in toks if t not in ("jr", "sr", "ii", "iii", "iv")] or toks
        pats.add(re.escape(last[-1]))               # round 10: last name alone, ANY length ('Lee'), as a whole word
    return re.compile(r"\b(?:" + "|".join(sorted(pats, key=len, reverse=True)) + r")\b") if pats else None

ORPHAN = re.compile(r"^[\W\d_]*(?:(?:process\w*|runs?|clears?|goes|through|is|are|in|on|at|by|until|before|after|"
                    r"mon|tue|wed|thu|fri|sat|sun|\w+day|tonight|tomorrow|today|am|pm|pt|noon|midnight|waivers?)\b[\W\d_]*)+$",
                    re.I)

def drop_named(t, rx):
    """Drop sentences naming a pending player, plus any orphan timing/processing fragment right after a drop."""
    kept, dropped, after_drop = [], [], False
    for m in SENTENCE.finditer(t):
        sen = m.group(0)
        if rx.search(fold(sen).lower()) or (after_drop and ORPHAN.match(fold(sen))):
            dropped.append(sen.strip()); after_drop = True
        else:
            kept.append(sen); after_drop = False
    return "".join(kept).strip(), dropped

def scrub_pending_names(o, names):
    """Round 9 OUTPUT safety net over EVERY string value and key: a dict entry whose key names a pending player is
    removed; a list item (record) with any non-free-text value naming one is removed; free text drops the sentence."""
    rx = _name_rx(names)
    log = []
    if rx is None:
        return o, log
    TEXT = {"text", "why", "reason", "note", "notes", "stats", "title", "label", "summary", "detail"}
    def hit(x):
        return isinstance(x, str) and bool(rx.search(fold(x).lower()))
    def walk(v, path, key=None):
        if isinstance(v, str):
            if key in TEXT or key is None:
                k, d = drop_named(v, rx)
                log.extend((path, x) for x in d)
                return k
            return v
        if isinstance(v, dict):
            out = {}
            for k, x in v.items():
                if hit(k):
                    log.append((f"{path}.{k}", "(key)")); continue
                out[k] = walk(x, f"{path}.{k}", k)
            return out
        if isinstance(v, list):
            out = []
            for i, x in enumerate(v):
                p = f"{path}[{i}]"
                if isinstance(x, dict) and any(hit(y) for kk, y in x.items() if kk not in TEXT) or \
                   isinstance(x, dict) and any(hit(z) for kk, y in x.items() if kk not in TEXT and isinstance(y, list) for z in y):
                    log.append((p, "(record)")); continue
                if isinstance(x, str) and hit(x) and key not in TEXT:
                    log.append((p, x)); continue
                nx = walk(x, p, key)
                if isinstance(x, str) and x.strip() and not nx:
                    continue
                if isinstance(x, dict) and isinstance(x.get("text"), str) and x["text"].strip() and not nx.get("text"):
                    continue
                out.append(nx)
            return out
        return v
    return walk(o, ""), log


# ---------- round 10: resolve every pending item to names, or fail closed ----------
# 'claim(s)/bid(s)/offer(s)' must not run on into a lower-case letter ('positions_offered', 'bidder' are not sources)
QUEUE_KEY = re.compile(r"(?i:pending|queue)|(?i:claim|bid|offer)s?(?![a-z])")   # any list/dict under such a key is a pending source
TXN_LIST_KEY = re.compile(r"(?i:transaction|txn|move|request|log)s?(?![a-z])|(?i:activit|history|waiver[\s_-]*wire)")
NAME_FIELDS = ("player", "name", "add", "adds", "drop", "drops", "give", "get", "offered", "requested", "players")
ACTION_NAME = re.compile(r"\b(?:add|drop|claim|waive|trade|get|give)s?\s+((?:[A-Z][A-Za-z.'\-]+\s+){0,3}?[A-Z][a-z][A-Za-z.'\-]*)"
                         r"(?=\s+(?:[A-Z]{1,3}(?:,[A-Z]{1,3})*\s+[A-Z]{2,3}\b|[A-Z]{2,3}\b)|\s*(?:/|$|,|\())")
TEXT_NAME = re.compile(r"[+\-\u2212]\s*([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+)+)")

# ---------- pending-names-capture: who is "us", and what counts as a name ----------
OWN_KEY = re.compile(r"(?i:eddie|eagle[\s_-]*ridge)|^(?:my|own)(?:[A-Z_]|$)|^(?i:my|own)[\s_-]|(?i:^t_ere\d*$)|(?i:^ere$)")
OWN_VAL = re.compile(r"(?i:eddie|eagle\s*ridge|^ere$|^t_ere\d*$|bill\s+jenson)")
OWN_ID_FIELDS = ("name", "team", "teamName", "team_name", "teamId", "team_id", "id", "owner", "abbrev", "fantraxTeamId")
_OWN_IDS = None

def _own_ids():
    """Our Fantrax team id(s) from data/hq/fantrax-team-ids.json ('eddies')."""
    global _OWN_IDS
    if _OWN_IDS is None:
        try:
            from pathlib import Path
            ids = json.loads((Path(__file__).resolve().parent.parent / "data/hq/fantrax-team-ids.json").read_text())
            _OWN_IDS = {str(ids["eddies"]).lower()} if ids.get("eddies") else set()
        except Exception:
            _OWN_IDS = set()
    return _OWN_IDS

def is_own_key(k):
    if not isinstance(k, str):
        return False
    f = fold(k)
    return bool(OWN_KEY.search(f)) or f.strip().lower() in _own_ids()

def is_own_record(d):
    """A dict whose identity field (name/team/teamId/...) names us (homoglyph-folded)."""
    if not isinstance(d, dict):
        return False
    for k in OWN_ID_FIELDS:
        v = d.get(k)
        if isinstance(v, str) and (OWN_VAL.search(fold(v)) or fold(v).strip().lower() in _own_ids()):
            return True
    return False

NAME_LIKE = re.compile(r"[A-Za-z][A-Za-z'\-]*\.?(?:\s+[A-Za-z][A-Za-z'\-]*\.?)+")
NAME_JUNK = {"tbd", "pending claim", "pending bid", "pending trade", "hidden", "unknown", "n a", "none", "player"}

def name_key(n):
    """Normalized key for a NAME-LIKE player name (2+ Latin words, no digits/commas); None otherwise."""
    if not isinstance(n, str) or non_latin(n):
        return None
    f = " ".join(fold(n).split())
    if not NAME_LIKE.fullmatch(f) or sum(c.isalpha() for c in f) < 4:
        return None
    k = re.sub(r"[^a-z ]", " ", f.lower()); k = " ".join(k.split())
    return None if k in NAME_JUNK else k

def distinct_names(names):
    return {k for k in (name_key(n) for n in names) if k}

def _own_count(o):
    """Our pending count: same key matching (COUNT_ANY) and coercion (_num) as pending_count, on any key whose path
    names us (eddie / eagle ridge / my* / own* / our team id) or inside a record whose identity field names us."""
    best = 0
    def walk(x, own=False):
        nonlocal best
        if isinstance(x, dict):
            own = own or is_own_record(x)
            for k, v in x.items():
                o2 = own or is_own_key(k)
                n = _num(v) if isinstance(k, str) and COUNT_ANY.search(k) else None
                if n is not None and o2:
                    best = max(best, n)
                else:
                    walk(v, o2)
        elif isinstance(x, list):
            for v in x: walk(v, own)
    walk(o)
    return best

def _item_names(x):
    out = []
    if isinstance(x, str):
        out += ACTION_NAME.findall(x) + TEXT_NAME.findall(x)
        if not out and re.fullmatch(r"[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+)+", x.strip()):
            out.append(x.strip())
    elif isinstance(x, list):
        for y in x: out += _item_names(y)
    elif isinstance(x, dict):
        for k in NAME_FIELDS:
            if k in x: out += _item_names(x[k])
        if isinstance(x.get("action"), str):
            out += _item_names(x["action"])
    return [n for n in out if isinstance(n, str) and n.strip()]

PENDING_FLAG = re.compile(r"pending|queued|awaiting|in[_\s-]?progress|unprocessed", re.I)

def _pt_date(v):
    """Date in PT for an ISO-ish stamp ('2026-10-22 19:15', '2026-10-22T23:30-10:00', '20261022'); None if unparseable.
    A stamp with an offset is converted to PT; one without is read as PT."""
    try:
        dt = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(PT).date() if dt.tzinfo else dt.date()

def _txn_pending(t, today):
    if not isinstance(t, dict):
        return True
    # round 11: an explicit pending flag (pending: true, isPending, queued, awaiting...) wins over any status
    for k, v in t.items():
        if isinstance(k, str) and k != "status" and PENDING_FLAG.search(k) and v not in (None, False, 0, "", [], {}) \
                and not (isinstance(v, str) and v.strip().lower() in ("false", "no", "0")):
            return True
    st = t.get("status")
    if not isinstance(st, str) or non_latin(st):
        return True                                       # missing / non-string / look-alike letters
    st = prep(st).strip().lower()                         # NFKC + zero-width removal + strip + case only (no accent fold)
    # round 10b (approved): Fantrax 'processed' WITH a past date counts as completed; nothing else does
    if st not in ("completed", "processed"):
        return True                                       # pending / queued / processing / processed-pending ...
    for k in ("date", "datetime_pdt", "datetime", "time_pdt"):
        if t.get(k):
            d = _pt_date(t[k])
            return d is None or d >= today
    return True                                           # completed with no date

def resolve_pending(raw, path, today, expect_file=True):
    """-> names. Raises PendingError when any pending item cannot be resolved to a name:
    - any *pending*count >= 1 (any level) not covered by as many named items;
    - any non-empty pending / queue / claims / bids / offers collection (any level) whose entries have no name
      (id-only or nameless entries are unresolved);
    - any raw transaction whose status is not exactly 'completed' or is dated today/future (resolved via its names);
    - the private file missing or malformed while anything is pending. File may be a list or {"names": [...]}."""
    items, problems = [], []                              # items: list of name-lists, one per pending entry
    own_items = []                                        # name-lists of OUR pending entries
    def walk(o, path_="", own=False):
        if isinstance(o, dict):
            own = own or is_own_record(o)
            for k, v in o.items():
                p = f"{path_}.{k}"
                if not isinstance(k, str):
                    continue
                o2 = own or is_own_key(k)
                if _num(v) is not None or v is None or v is False:
                    continue                                  # counts handled by pending_count()
                if TXN_LIST_KEY.search(k) and isinstance(v, dict):
                    # dict-wrapped transactions ({items: [...]}) or a single transaction dict
                    lists = [x for x in v.values() if isinstance(x, list)]
                    v = [t for x in lists for t in x] if lists else [v]
                if TXN_LIST_KEY.search(k) and isinstance(v, list):
                    for i, t in enumerate(v):
                        if _txn_pending(t, today):
                            nm = _item_names(t)
                            items.append(nm)
                            if o2 or is_own_record(t): own_items.append(nm)
                            if not nm: problems.append(f"{p}[{i}] pending transaction with no name")
                    continue
                if QUEUE_KEY.search(k) and v not in (None, "", [], {}, 0, False):
                    entries = v if isinstance(v, list) else [v]
                    for i, e in enumerate(entries):
                        nm = _item_names(e)
                        items.append(nm)
                        if o2 or is_own_record(e): own_items.append(nm)
                        if not nm: problems.append(f"{p}[{i}] pending entry with no name")
                    continue
                walk(v, p, o2)
        elif isinstance(o, list):
            for v in o: walk(v, path_, own)
    walk(raw if isinstance(raw, dict) else {})
    file_names, file_ok = [], None
    if path:
        try:
            d = json.loads(open(path).read())
            lst = d if isinstance(d, list) else (d.get("names") if isinstance(d, dict) else None)
            if not isinstance(lst, list):
                raise ValueError("no names list")
            # round 10: the file must be captured from THIS scrape (same scrape stamp), else it is stale
            if isinstance(raw, dict) and raw.get("scraped") is not None:
                if not isinstance(d, dict) or str(d.get("scraped")) != str(raw.get("scraped")):
                    raise ValueError(f"stale: file scraped {d.get('scraped') if isinstance(d, dict) else None!r} "
                                     f"!= raw {raw.get('scraped')!r}")
            file_names = [n for n in lst if isinstance(n, str) and n.strip()]
            own_l = d.get("own_names") if isinstance(d, dict) else None
            # round 11: no own_names key = none of ours (other teams' names never cover our count)
            file_own = [n for n in own_l if isinstance(n, str) and n.strip()] if isinstance(own_l, list) else []
            file_ok = True
        except (OSError, ValueError) as e:
            file_ok = False
            file_err = str(e)
    count = max(pending_count(raw, path if file_ok else None), len(items))   # direct entries count too
    # count DISTINCT, NAME-LIKE names only (dups, '—', 'TBD', '1', '\u200b' never cover a count)
    all_keys = distinct_names([n for nm in items for n in nm] + (file_names + file_own if file_ok else []))
    named = len(all_keys)
    # own_names are always part of the drop filter
    names = [n for nm in items for n in nm] + (file_names + file_own if file_ok else [])
    pending_any = count >= 1 or bool(items)
    if pending_any and isinstance(raw, dict) and raw.get("scraped") in (None, ""):
        problems.append("raw scrape has no 'scraped' stamp, so the private file cannot be checked as fresh")
    if pending_any and expect_file and path and not file_ok:
        problems.append(f"private pending-name file {path} missing or malformed")
    if count > named:
        problems.append(f"{count} pending move(s) but only {named} resolved to a name")
    # our own counts (any *eddie*pending*count) must be covered by OUR named entries or the private file, not by
    # other teams' transactions
    own = _own_count(raw) if isinstance(raw, dict) else 0
    if file_ok:
        own = max(own, max([_num(v) or 0 for k, v in ((d.get("counts") or {}).items() if isinstance(d, dict) else [])
                            if any(is_own_key(part) for part in str(k).split("."))] or [0]))
    # other teams' names never cover OUR count; count distinct name-like names only
    own_have = len(distinct_names([n for nm in own_items for n in nm] + (file_own if file_ok else [])))
    if own > own_have:
        problems.append(f"{own} of our pending move(s) but only {own_have} of ours resolved to a name")
    if problems:
        raise PendingError("pending item(s) without a resolved name: " + "; ".join(problems[:5])
                           + " (private pending-name list is empty, missing or incomplete; run stopped, nothing written)")
    return names
