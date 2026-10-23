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
COMPLETED = {"completed", "complete", "processed", "executed", "accepted-and-processed", "accepted and processed"}
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
