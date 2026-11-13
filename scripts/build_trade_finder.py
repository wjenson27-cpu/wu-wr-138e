#!/usr/bin/env python3
"""Build data/trade-finder.json — rest-of-season trade ideas for the Eddies.

Recommend-only. This script reads league files that are already in the repo
and writes a ranked list. It does not send, propose, or enter a trade, and it
does not contact Fantrax. Pending bids and pending trades on the scrape are
not copied into the output.

Run from the repo root:

    python3 scripts/build_trade_finder.py
    python3 scripts/build_trade_finder.py --scrape data/sources/fantrax-raw-2026-11-12-pm-normalized.json
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import warroom_common as wc  # noqa: E402

DEFAULT_SCRAPE = ROOT / "data" / "sources" / "fantrax-raw-2026-11-12-pm-normalized.json"
SCRAPE_PATH = DEFAULT_SCRAPE
IDP_PATH = ROOT / "data" / "idp-rankings.json"
RANK_DIR = ROOT / "data" / "rankings"
VALUES_PATH = ROOT / "data" / "player-values.json"
TEAMS_PATH = ROOT / "data" / "hq" / "teams.json"
OUT_PATH = ROOT / "data" / "trade-finder.json"

# 2026 NFL bye weeks. Same map the contingency board uses.
BYE = {
    "ARI": 14, "ATL": 11, "BAL": 13, "BUF": 7, "CAR": 5, "CHI": 10, "CIN": 6,
    "CLE": 11, "DAL": 14, "DEN": 10, "DET": 6, "GB": 11, "HOU": 8, "IND": 13,
    "JAX": 7, "KC": 5, "LV": 13, "LAC": 7, "LAR": 11, "MIA": 6, "MIN": 6,
    "NE": 11, "NO": 8, "NYG": 8, "NYJ": 13, "PHI": 10, "PIT": 9, "SF": 8,
    "SEA": 11, "TB": 10, "TEN": 9, "WAS": 7,
}
POS_MAP = {
    "QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE",
    "DL": "DL", "DE": "DL", "DT": "DL", "NT": "DL", "EDGE": "DL",
    "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB",
    "DB": "DB", "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB",
}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
# First-token nicknames, same pairs the rankings board uses. Formal name is the key.
_NICK_GROUPS = (
    ("nathan", "nate"), ("michael", "mike", "mikey"), ("christopher", "chris"),
    ("matthew", "matt"), ("joshua", "josh"), ("william", "will", "bill", "billy"),
    ("daniel", "dan", "danny"), ("david", "dave"), ("anthony", "tony"),
    ("cameron", "cam"), ("zachary", "zach", "zack", "zac"),
    ("jonathan", "jon", "jonathon", "johnathan"),
    ("robert", "rob", "bob", "bobby", "robbie"), ("benjamin", "ben", "benny"),
    ("thomas", "tom", "tommy"), ("nicholas", "nick", "nic", "nicky"),
    ("alexander", "alex"), ("jacob", "jake"), ("samuel", "sam", "sammy"),
    ("joseph", "joe", "joey"), ("gregory", "greg"), ("kenneth", "ken", "kenny"),
    ("daxton", "dax"), ("kamren", "kam"), ("patrick", "pat"),
    ("jeffrey", "jeff", "jeffery"), ("steven", "steve", "stephen"),
    ("andrew", "andy", "drew"), ("richard", "rick", "rich", "ricky"),
    ("mitchell", "mitch"), ("gabriel", "gabe"), ("philip", "phil", "phillip"),
    ("theodore", "ted", "teddy"), ("timothy", "tim", "timmy"),
    ("charles", "charlie", "chuck"), ("edward", "ed", "eddie"),
    ("frederick", "fred", "freddie", "freddy"), ("ronald", "ron", "ronnie"),
    ("donald", "don"), ("douglas", "doug"), ("james", "jim", "jimmy"),
    ("vincent", "vince", "vinny"), ("dominic", "dom", "dominick"),
    ("terrence", "terry", "terence"), ("lawrence", "larry"), ("peter", "pete"),
    ("walter", "walt"), ("wesley", "wes"), ("bradley", "brad"),
)
FIRST = {token: group[0] for group in _NICK_GROUPS for token in group}

# Keeps. The LB room is deep because these two stay.
KEEPS = ("Jordyn Brooks", "Cedric Gray")
# Upside holds. Never outgoing, even if a surplus list or the trade block names them.
HOLDS = ("Josh Downs",)
# Surplus the club can move. Brooks, Gray, and Downs are not here.
# A name that is not on the roster is warned and skipped, not fatal.
LB_OUT = ("Fred Warner", "Frankie Luvu", "Trenton Simpson")
WR_OUT = ("Jalen Coker",)
# Incoming spots. RB and DL stay. LB and DB are in because the club wants one more quality IDP.
INCOMING = ("RB", "DL", "LB", "DB")

# Playable = would start on a thin roster. Usable = real surplus / a back we'd want.
# Bars are absolute rest-of-season points, set on the week-8 board (about 10 games).
# They are not rescaled when the scrape week moves.
PLAYABLE = {"QB": 120, "RB": 80, "WR": 70, "TE": 70, "DL": 80, "LB": 80, "DB": 80}
USABLE = {"QB": 160, "RB": 90, "WR": 100, "TE": 90, "DL": 120, "LB": 120, "DB": 120}
THIN_AT = {"LB": 2, "DL": 2, "DB": 3, "WR": 3, "RB": 2}
# A partner is deep enough to give this spot. Never their best, and at least two usable stay.
DEEP_AT = {"RB": 3, "DL": 3, "LB": 3, "DB": 3}
# Dedicated starters. Flex spots are covered by the depth bars, not by these counts.
STARTERS = {"QB": 1, "RB": 1, "WR": 1, "TE": 1, "DL": 1, "LB": 1, "DB": 2}
KIND = {"RB": "back", "DL": "lineman", "LB": "linebacker", "DB": "defensive back"}
# Lineup value is mostly the healthy roster, plus weight for the two thin spots
# (Hall's quad, and Karlaftis as the only DL) sitting.
HEALTHY_W, HALL_W, DL_W = 0.65, 0.25, 0.10
MIN_DELTA = 3.0
# A deep room, or a real hole, can give this many lineup points and still be a fit.
# Tuned so a third DL or a spare linebacker is not dropped for a one-point miss.
MIN_PARTNER_DELTA = -12.0
TARGET_IDEAS = 10
PV_SCALE = 0.90  # median week-8 board pts / player-values ppg, players over 8 ppg

DISPLAY_FULL = "Towner Top Aga Bottom"


def display_name(full: str) -> str:
    """Club label. The one long Fantrax name is shown as TTAB."""
    if (full or "").strip().casefold() == DISPLAY_FULL.casefold():
        return "TTAB"
    return full


def norm_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("'", "").replace(".", "").replace("-", " ")
    parts = []
    for ch in text:
        parts.append(ch if ch.isalpha() or ch.isspace() else " ")
    tokens = [p for p in "".join(parts).split() if p not in SUFFIXES]
    if tokens and tokens[0] in FIRST:
        tokens[0] = FIRST[tokens[0]]
    return " ".join(tokens)


def round1(n: float) -> float:
    return round(float(n) + 0.0, 1)


def load_json(path: Path):
    return json.loads(path.read_text())


def map_positions(raw: str) -> list[str]:
    out = []
    for part in (raw or "").replace("/", ",").split(","):
        pos = POS_MAP.get(part.strip().upper())
        if pos and pos not in out:
            out.append(pos)
    return out


def games_left(nfl: str, week: int) -> int:
    horizon = 17 - week + 1
    bye = BYE.get((nfl or "").upper())
    if bye is not None and bye >= week:
        horizon -= 1
    return max(horizon, 0)


def injury_mult(slot: str, tags: list, text: str) -> float:
    """Fantrax tag discount. IR and season-ending are handled by the caller.

    An ACL in the injury text is treated as a long absence. Achilles is that
    severe only with a tear, rupture, surgery, or an Out/IR tag. A Questionable
    Achilles tag stays a normal Q discount.
    """
    blob = (text or "").lower()
    tagset = {str(t).upper() for t in (tags or [])}
    if slot == "ir" or "IR" in tagset or "injured reserve" in blob:
        return 0.0
    if any(w in blob for w in ("suspended", "pup", "nfi")) or "O" in tagset:
        return 0.0
    severe = any(w in blob for w in ("tear", "torn", "rupture", "surgery", "season"))
    if "acl" in blob or ("achilles" in blob and severe):
        return 0.15
    if "D" in tagset or "doubtful" in blob:
        return 0.35
    if "Q" in tagset or "questionable" in blob:
        return 0.9
    return 1.0


def index_by_name(rows, name_key: str, better_key: str | None = None) -> dict:
    out = {}
    for row in rows:
        key = norm_name(row.get(name_key) or "")
        if not key:
            continue
        prev = out.get(key)
        if prev is None:
            out[key] = row
            continue
        if better_key and (row.get(better_key) or 0) > (prev.get(better_key) or 0):
            out[key] = row
    return out


class Player:
    def __init__(self, name, pos, eligible, nfl, slot, ros, mult, source, season_ending):
        self.name = name
        self.pos = pos
        self.eligible = tuple(eligible)
        self.nfl = nfl or ""
        self.slot = slot
        self.ros = float(ros)
        self.mult = float(mult)
        self.source = source
        self.season_ending = bool(season_ending)
        # An active IDP missing from both value files is assumed to be a real
        # body so a data gap is not treated as an empty room.
        self.assumed = source.startswith("slot tier: active")

    @property
    def lineup_ok(self) -> bool:
        return (not self.season_ending) and self.slot != "ir" and self.mult >= 0.3 and self.ros > 0

    def playable(self) -> bool:
        return self.lineup_ok and (self.assumed or self.ros >= PLAYABLE.get(self.pos, 80))

    def usable(self) -> bool:
        return self.lineup_ok and (self.assumed or self.ros >= USABLE.get(self.pos, 95))

    def public(self) -> dict:
        return {
            "name": self.name,
            "pos": self.pos,
            "nfl": self.nfl,
            "ros": round1(self.ros),
        }


def optimize(players: list[Player]) -> tuple[float, set[str]]:
    """Greedy Wheels Up lineup. Same slots as the trade tab: 1 QB, 1 RB, 1 WR,
    1 TE, 3 RB/WR/TE, 1 DL, 1 LB, 2 DB, 3 IDP. A DL/LB player can fill either."""
    used: set[str] = set()
    total = 0.0

    def take(positions: list[str], count: int, primary_only: bool) -> int:
        nonlocal total
        if count <= 0:
            return 0
        pool = [
            p for p in players
            if p.name not in used and p.lineup_ok
            and any(pos in p.eligible for pos in positions)
            and (not primary_only or p.pos in positions)
        ]
        pool.sort(key=lambda p: (-p.ros, p.name))
        got = 0
        for p in pool:
            if got >= count:
                break
            used.add(p.name)
            total += p.ros
            got += 1
        return got

    for pos, n in (("QB", 1), ("RB", 1), ("WR", 1), ("TE", 1), ("DL", 1), ("LB", 1)):
        got = take([pos], n, True)
        take([pos], n - got, False)
    got = take(["DB"], 2, True)
    take(["DB"], 2 - got, False)
    take(["RB", "WR", "TE"], 3, False)
    take(["DL", "LB", "DB"], 3, False)
    return total, used


def blend(players: list[Player]) -> tuple[float, float]:
    """Healthy lineup, plus Hall sitting and Karlaftis sitting. Returns (blended, healthy)."""
    healthy, _ = optimize(players)
    hall, _ = optimize([p for p in players if norm_name(p.name) != "breece hall"])
    karl, _ = optimize([p for p in players if norm_name(p.name) != "george karlaftis"])
    blended = HEALTHY_W * healthy + HALL_W * hall + DL_W * karl
    return blended, healthy


def count_pos(players: list[Player], pred) -> dict:
    """Count each eligible position. A DL/LB counts in both. IDP is unique players."""
    counts = {pos: 0 for pos in ("QB", "RB", "WR", "TE", "DL", "LB", "DB")}
    idp = set()
    for p in players:
        if not pred(p):
            continue
        for pos in p.eligible:
            if pos in counts:
                counts[pos] += 1
        if any(pos in ("DL", "LB", "DB") for pos in p.eligible):
            idp.add(p.name)
    counts["IDP"] = len(idp)
    return counts


def offense_rate(rank_row: dict | None, pv_row: dict | None) -> tuple[float | None, str]:
    if rank_row and not rank_row.get("bye"):
        pts = rank_row.get("pts")
        if isinstance(pts, (int, float)) and pts > 0:
            return float(pts), "week-board consensus"
    if rank_row:
        recent = (rank_row.get("sources") or {}).get("recent") or {}
        pts = recent.get("pts")
        if isinstance(pts, (int, float)) and pts > 0:
            return float(pts), "last-3 actuals"
    if pv_row and isinstance(pv_row.get("ppg"), (int, float)) and pv_row["ppg"] > 0:
        return float(pv_row["ppg"]) * PV_SCALE, "player-values ppg x 0.90"
    return None, "unvalued"


def build_player(raw: dict, week: int, idp_idx: dict, rank_idx: dict, pv_idx: dict, season) -> Player:
    name = raw["name"]
    key = norm_name(name)
    eligible = map_positions(raw.get("pos") or "")
    idp = idp_idx.get(key)
    if idp and idp.get("pos") in POS_MAP.values() and idp["pos"] not in eligible:
        eligible.append(idp["pos"])
    if not eligible:
        eligible = ["WR"]
    primary = idp["pos"] if idp and idp.get("pos") in eligible else eligible[0]
    slot = raw.get("slot") or "active"
    tags = raw.get("injury_tags") or []
    text = raw.get("injury_text") or ""
    ending = bool(season.match(name))
    mult = 0.0 if ending else injury_mult(slot, tags, text)
    source = "unvalued"
    base = 0.0
    games = games_left(raw.get("nfl") or "", week)
    if primary in ("DL", "LB", "DB") and idp and isinstance(idp.get("rosPts"), (int, float)):
        base = float(idp["rosPts"])
        source = "idp rosPts"
        # Rankings already discount a tag they knew about. A new Fantrax tag still applies.
        if idp.get("injury") and mult in (0.9, 0.35):
            mult = 0.0 if ending or slot == "ir" else 1.0
    elif primary in ("DL", "LB", "DB"):
        pv = pv_idx.get(key)
        ppg = pv.get("ppg") if pv else None
        if isinstance(ppg, (int, float)) and ppg >= 8:
            base = float(ppg) * games * PV_SCALE
            source = "player-values ppg x 0.90"
        elif slot == "active" and not ending:
            base = 100.0
            source = "slot tier: active IDP missing from both files"
        elif slot == "reserve" and not ending:
            base = 50.0
            source = "slot tier: reserve IDP missing from both files"
    elif primary in ("QB", "RB", "WR", "TE"):
        rate, source = offense_rate(rank_idx.get(key), pv_idx.get(key))
        if rate is not None:
            base = rate * games
    ros = 0.0 if mult <= 0 else base * mult
    return Player(name, primary, eligible, raw.get("nfl") or "", slot, ros, mult, source, ending)


def block_names(block: dict) -> set[str]:
    found = set()
    for line in (block or {}).get("players") or []:
        # "Zach Charbonnet RB SEA" — drop a trailing POS TEAM pair.
        parts = str(line).split()
        if len(parts) >= 3 and parts[-2].upper() in POS_MAP and parts[-1].isupper():
            parts = parts[:-2]
        found.add(norm_name(" ".join(parts)))
    return found


def team_id_map(teams_doc: dict) -> dict[str, str]:
    out = {}
    for team in teams_doc.get("teams") or []:
        out[(team.get("name") or "").strip().casefold()] = team["id"]
    # Fantrax spells a few clubs the same as teams.json. TTAB's id is ttab.
    return out


def _player_named(by_name: dict, name: str):
    if name in by_name:
        return by_name[name]
    key = norm_name(name)
    for roster_name, player in by_name.items():
        if norm_name(roster_name) == key:
            return player
    return None


def _blocked_names() -> dict[str, str]:
    """Normalized name -> the list it came from. Keeps and holds are never outgoing."""
    out = {}
    for name in list(KEEPS) + list(HOLDS):
        out[norm_name(name)] = name
    return out


def resolve_surplus(names, by_name: dict) -> list:
    """Rostered surplus players, in list order. Missing names warn and are skipped.
    A keep or a hold is never returned, even if the surplus list names them."""
    blocked = _blocked_names()
    found = []
    missing = []
    held = []
    for name in names:
        if norm_name(name) in blocked:
            held.append(name)
            continue
        player = _player_named(by_name, name)
        if player is None:
            missing.append(name)
            continue
        found.append(player)
    if held:
        warnings.warn(
            "surplus names are holds or keeps and are not outgoing: " + ", ".join(held),
            RuntimeWarning,
            stacklevel=2,
        )
    if missing:
        warnings.warn(
            "surplus names not on the Eddies roster, skipped: " + ", ".join(missing),
            RuntimeWarning,
            stacklevel=2,
        )
    return found


def rostered_holds(by_name: dict) -> list[str]:
    """Hold names that are actually on the roster. A dropped hold warns and is skipped."""
    found = []
    missing = []
    for name in HOLDS:
        player = _player_named(by_name, name)
        if player is None:
            missing.append(name)
        else:
            found.append(player.name)
    if missing:
        warnings.warn(
            "hold names not on the Eddies roster, skipped: " + ", ".join(missing),
            RuntimeWarning,
            stacklevel=2,
        )
    return found


def depth_count(pos: str, usable: dict, playable: dict) -> int:
    """WR depth uses playable bodies. Every other spot uses the usable bar."""
    if pos == "WR":
        return int(playable.get(pos, 0))
    return int(usable.get(pos, 0))


def needs_line(players: list, usable: dict, playable: dict) -> str:
    """Healthy/usable counts against the dedicated starting slots, plus any depth-bar miss."""
    parts = []
    for pos in ("QB", "RB", "WR", "TE", "DL", "LB", "DB"):
        n = int(usable.get(pos, 0))
        slots = STARTERS[pos]
        who = [
            p.name for p in sorted(players, key=lambda p: (-p.ros, p.name))
            if p.pos == pos and p.usable()
        ]
        slot_word = "slot" if slots == 1 else "slots"
        if n <= 2 and who:
            parts.append(f"{n} usable {pos} ({', '.join(who)}) for {slots} starting {slot_word}")
        else:
            parts.append(f"{n} usable {pos} for {slots} starting {slot_word}")
    text = "; ".join(parts) + "."
    short = []
    for pos in ("RB", "WR", "DL", "LB", "DB"):
        n = depth_count(pos, usable, playable)
        bar = THIN_AT[pos]
        if n < bar:
            kind = "playable" if pos == "WR" else "usable"
            short.append(f"{pos} is short of the depth bar ({n} {kind}, bar {bar})")
    if short:
        text += " " + ". ".join(short) + "."
    return text


def repo_rel(path: Path) -> str:
    path = path.resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


_SLOT_RANK = {"active": 0, "reserve": 1, "ir": 2}


def dedupe_rows(rows: list) -> list:
    """One row per player. Fantrax sometimes lists the same name on two slots."""
    best = {}
    order = []
    for raw in rows or []:
        key = norm_name(raw.get("name") or "")
        if not key:
            continue
        prev = best.get(key)
        if prev is None:
            best[key] = raw
            order.append(key)
            continue
        prev_rank = _SLOT_RANK.get(prev.get("slot") or "active", 9)
        raw_rank = _SLOT_RANK.get(raw.get("slot") or "active", 9)
        if raw_rank < prev_rank:
            best[key] = raw
    return [best[key] for key in order]


def give_packages(lbs: list[Player], wrs: list[Player]) -> list[list[Player]]:
    """Singles, plus an offense-for-IDP 2-for-1 (one surplus LB and one surplus WR).

    A WR sent for an RB is offense for offense. That is allowed when the other
    fit bars clear. It is not a separate filter.
    """
    packages = [[p] for p in lbs + wrs]
    for lb in lbs:
        for wr in wrs:
            packages.append([lb, wr])
    return packages


def sent_holes(give: list[Player], usable: dict, playable: dict) -> list[str]:
    """Positions we send that this club is actually thin at.

    An IDP in the package has to hit an IDP hole. A bench WR is the reason
    only when the package is WRs and they are short at WR. A throw-in WR
    does not make a thick LB room into a trade.
    """
    idp = [p for p in give if p.pos in ("LB", "DL", "DB")]
    holes = []
    if idp:
        for p in idp:
            thin = (
                (p.pos == "LB" and usable.get("LB", 0) < 2)
                or (p.pos == "DL" and usable.get("DL", 0) < 2)
                or (p.pos == "DB" and usable.get("DB", 0) < 3)
            )
            if thin and p.pos not in holes:
                holes.append(p.pos)
        return holes
    if any(p.pos == "WR" for p in give) and playable.get("WR", 0) < 3:
        return ["WR"]
    return []


def need_points(pos: str, usable: dict, playable: dict) -> int:
    if pos == "LB":
        return 24 if usable.get("LB", 0) == 0 else 16
    if pos == "DL":
        return 22 if usable.get("DL", 0) == 0 else 14
    if pos == "DB":
        return 20 if usable.get("DB", 0) <= 1 else 12
    if pos == "WR":
        return 16 if playable.get("WR", 0) <= 1 else 10
    return 0


def fit_score(give, get, eddies_delta, partner_delta, healthy_delta, playable, usable, block_get, block_give, surplus_piece, starts_for_them, gives_starter, our_usable=None, our_playable=None) -> int | None:
    got = get[0]
    deep_need = DEEP_AT.get(got.pos)
    if deep_need is None or usable.get(got.pos, 0) < deep_need:
        return None
    holes = sent_holes(give, usable, playable)
    if max(p.ros for p in give) < 70 and not any(p.pos == "LB" for p in give):
        return None
    # A piece that would not start, sent at a position they are not thin at, does nothing for them.
    if not holes and not starts_for_them:
        return None
    base = {"RB": 22, "DL": 14, "LB": 16, "DB": 16}[got.pos]
    deep_n = usable.get(got.pos, 0)
    score = base + (10 if deep_n >= deep_need + 1 else 6)
    if our_usable is not None and got.pos in THIN_AT:
        ours = depth_count(got.pos, our_usable, our_playable or {})
        if ours < THIN_AT[got.pos]:
            score += 8
    if holes:
        score += max(need_points(pos, usable, playable) for pos in holes)
    else:
        score += 12
    if eddies_delta < MIN_DELTA:
        return None
    if gives_starter and healthy_delta < 0:
        return None
    if partner_delta >= 0:
        score += 18
    elif partner_delta >= MIN_PARTNER_DELTA:
        score += 8
    else:
        return None
    score += 8 if len(give) == 1 else 4
    if surplus_piece:
        score += 4
    if block_get:
        score += 6
    if block_give:
        score += 3
    score += min(10.0, eddies_delta / 4.0)
    return max(0, min(100, round(score)))


def why_for_them(partner: str, give: list[Player], get: Player, playable: dict, usable: dict, partner_delta: float) -> str:
    got = get.name
    sent = " and ".join(f"{p.name} ({p.pos})" for p in give)
    holes = sent_holes(give, usable, playable)
    deep = usable.get(get.pos, 0)
    kind = KIND.get(get.pos, get.pos)
    room = get.pos
    if partner_delta >= 1:
        even = ""
    elif partner_delta >= -1:
        even = " Their lineup stays about even."
    else:
        even = " Their lineup gives up a few points to make the deal."
    if holes:
        bits = []
        for pos in holes:
            n = playable.get("WR", 0) if pos == "WR" else usable.get(pos, 0)
            word = "playable" if pos == "WR" else "usable"
            bits.append(f"{n} {word} {pos}{'s' if n != 1 else ''}")
        return (
            f"{partner} is deep at {room} ({deep} usable) and short ({', '.join(bits)}), "
            f"so {got} is a {kind} they can move and {sent} fills the hole.{even}"
        )
    return (
        f"{partner} is deep at {room} ({deep} usable), so {got} is a {kind} they can move, "
        f"and {sent} would step into their lineup.{even}"
    )


def spare_candidates(players: list[Player], pos: str) -> list[Player]:
    """Usable players at pos, never their best, and at least two usable stay if he leaves."""
    deep = DEEP_AT.get(pos, 3)
    usable = [
        p for p in players
        if p.pos == pos and p.usable() and not p.assumed and p.mult >= 0.85 and p.slot != "ir"
    ]
    usable.sort(key=lambda p: (-p.ros, p.name))
    if len(usable) < deep or len(usable) - 1 < 2:
        return []
    best = usable[0].name
    return [p for p in usable if p.name != best]


def incoming_players(players: list[Player]) -> list[Player]:
    found = []
    for pos in INCOMING:
        found.extend(spare_candidates(players, pos))
    return found


def consider(eddies, partner_players, give, get, playable, usable, eddies_starters, their_block, our_block, our_usable=None, our_playable=None):
    if get.season_ending or any(p.season_ending for p in give):
        return None
    blocked = _blocked_names()
    if any(norm_name(p.name) in blocked for p in give):
        return None
    give_names = {p.name for p in give}
    e_before, e_healthy_before = blend(eddies)
    e_after, e_healthy_after = blend([p for p in eddies if p.name not in give_names] + [get])
    p_before, _ = optimize(partner_players)
    p_after, p_starters = optimize([p for p in partner_players if p.name != get.name] + give)
    eddies_delta = (e_after - e_before)
    healthy_delta = e_healthy_after - e_healthy_before
    partner_delta = p_after - p_before
    surplus = all(p.name not in eddies_starters for p in give)
    starts = any(p.name in p_starters for p in give)
    score = fit_score(
        give, [get], eddies_delta, partner_delta, healthy_delta, playable, usable,
        norm_name(get.name) in their_block,
        any(norm_name(p.name) in our_block for p in give),
        surplus,
        starts,
        any(p.name in eddies_starters for p in give),
        our_usable,
        our_playable,
    )
    if score is None:
        return None
    return {
        "give": give,
        "get": get,
        "valueDelta": eddies_delta,
        "healthyDelta": healthy_delta,
        "partnerDelta": partner_delta,
        "fitScore": score,
    }


def select(candidates: list[dict], limit: int = TARGET_IDEAS) -> list[dict]:
    """Best package per partner+player, then at most two ideas per club."""
    best = {}
    for row in candidates:
        key = (row["partnerId"], row["get"].name)
        prev = best.get(key)
        if prev is None:
            best[key] = row
            continue
        # Same incoming player: keep the package that helps the Eddies more, then the smaller one.
        rank = (row["valueDelta"], -len(row["give"]), row["fitScore"])
        old = (prev["valueDelta"], -len(prev["give"]), prev["fitScore"])
        if rank > old:
            best[key] = row
    ordered = sorted(
        best.values(),
        key=lambda r: (-r["fitScore"], -r["valueDelta"], r["partner"], r["get"].name),
    )
    for per_club in (2, 3):
        picked = []
        club_n: dict[str, int] = {}
        for row in ordered:
            if club_n.get(row["partnerId"], 0) >= per_club:
                continue
            picked.append(row)
            club_n[row["partnerId"]] = club_n.get(row["partnerId"], 0) + 1
            if len(picked) >= limit:
                break
        if len(picked) >= limit or per_club == 3:
            return picked
    return picked


def idea_record(rank: int, row: dict, playable: dict, usable: dict) -> dict:
    give = row["give"]
    get = row["get"]
    shape = "1-for-1" if len(give) == 1 else "2-for-1"
    return {
        "rank": rank,
        "partner": row["partner"],
        "partnerId": row["partnerId"],
        "record": row["record"],
        "faab": row["faab"],
        "shape": shape,
        "give": [p.public() for p in give],
        "get": [get.public()],
        "valueDelta": round1(row["valueDelta"]),
        "partnerDelta": round1(row["partnerDelta"]),
        "fitScore": row["fitScore"],
        "whyItWorksForThem": why_for_them(row["partner"], give, get, playable, usable, row["partnerDelta"]),
    }


def build(scrape_path: Path | None = None, lb_out=None, wr_out=None) -> dict:
    scrape_path = Path(scrape_path) if scrape_path else DEFAULT_SCRAPE
    lb_out = LB_OUT if lb_out is None else tuple(lb_out)
    wr_out = WR_OUT if wr_out is None else tuple(wr_out)
    scrape = load_json(scrape_path)
    idp = load_json(IDP_PATH)
    latest = load_json(RANK_DIR / "latest.json")
    board = load_json(RANK_DIR / latest["file"])
    values = load_json(VALUES_PATH)
    teams_doc = load_json(TEAMS_PATH)
    season = wc.season_ending(ROOT / "data")
    week = int(idp.get("week") or latest.get("week") or scrape.get("week") or 8)
    ids = team_id_map(teams_doc)

    idp_rows = []
    for rows in (idp.get("positions") or {}).values():
        idp_rows.extend(rows)
    idp_idx = index_by_name(idp_rows, "player", "rosPts")
    rank_idx = index_by_name(
        [p for p in board.get("players") or [] if p.get("pos") in ("QB", "RB", "WR", "TE")],
        "name",
        "pts",
    )
    pv_idx = index_by_name(values.get("players") or [], "name", "ppg")

    blocks = scrape.get("trades", {}).get("trade_block") or {}
    our_block = block_names(blocks.get("Eagle Ridge Eddies") or {})
    rosters = []
    unmatched = []
    for entry in scrape.get("rosters") or []:
        full = entry["team"]
        players = []
        for raw in dedupe_rows(entry.get("players") or []):
            player = build_player(raw, week, idp_idx, rank_idx, pv_idx, season)
            if player.source == "unvalued" and not player.season_ending and player.slot != "ir":
                unmatched.append(f"{full}: {player.name} ({player.pos})")
            players.append(player)
        rosters.append({
            "full": full,
            "id": ids.get(full.strip().casefold(), norm_name(full).replace(" ", "-")),
            "label": display_name(full),
            "players": players,
            "record": (scrape.get("records") or {}).get(full, ""),
            "faab": (scrape.get("faab_remaining") or {}).get(full),
            "block": block_names(blocks.get(full) or {}),
        })

    eddies = next(t for t in rosters if t["id"] == "eddies" or t["full"] == "Eagle Ridge Eddies")
    by_name = {p.name: p for p in eddies["players"]}
    for keep in KEEPS:
        if _player_named(by_name, keep) is None:
            raise SystemExit(f"Keep {keep} is not on the Eddies roster")
    lbs = resolve_surplus(lb_out, by_name)
    wrs = resolve_surplus(wr_out, by_name)
    holds = rostered_holds(by_name)

    _, starters = optimize(eddies["players"])
    packages = give_packages(lbs, wrs)
    our_playable = count_pos(eddies["players"], lambda p: p.playable())
    our_usable = count_pos(eddies["players"], lambda p: p.usable())
    candidates = []
    depth = []
    for team in rosters:
        playable = count_pos(team["players"], lambda p: p.playable())
        usable = count_pos(team["players"], lambda p: p.usable())
        depth.append({
            "team": team["label"],
            "teamId": team["id"],
            "record": team["record"],
            "playable": {k: playable[k] for k in ("RB", "WR", "DL", "LB", "DB")},
            "usable": {k: usable[k] for k in ("RB", "WR", "DL", "LB", "DB")},
        })
        if team["id"] == "eddies":
            continue
        gets = incoming_players(team["players"])
        for get in gets:
            for give in packages:
                row = consider(
                    eddies["players"], team["players"], give, get, playable, usable,
                    starters, team["block"], our_block, our_usable, our_playable,
                )
                if row is None:
                    continue
                row["partner"] = team["label"]
                row["partnerId"] = team["id"]
                row["record"] = team["record"]
                row["faab"] = team["faab"]
                row["playable"] = playable
                row["usable"] = usable
                candidates.append(row)

    picked = select(candidates, TARGET_IDEAS)
    ideas = []
    for i, row in enumerate(picked, start=1):
        ideas.append(idea_record(i, row, row["playable"], row["usable"]))
    notes = [
        "Each idea stands on its own. Making one would change the rest of the board.",
    ]
    for pos, label in (("DL", "defensive lineman"), ("LB", "linebacker"), ("DB", "defensive back")):
        if any(p["pos"] == pos for idea in ideas for p in idea["get"]):
            continue
        notes.append(
            f"No idea brings back a {label}. No spare {pos} cleared the fit bar "
            "(a deep room, not their best player, and both lineups)."
        )

    e_play = our_playable
    e_use = our_usable
    partner_cap = abs(MIN_PARTNER_DELTA)
    idp_week = idp.get("week")
    idp_horizon = f"week {idp_week}" if idp_week else "the file's week"
    doc = {
        "generatedAt": wc.iso_pt(),
        "recommendOnly": True,
        "label": "Recommend-only rest-of-season ideas. Nothing here is sent.",
        "week": week,
        "asOfRoster": scrape.get("scraped"),
        "team": "Eagle Ridge Eddies",
        "record": eddies["record"],
        "faab": eddies["faab"],
        "keeps": list(KEEPS),
        "holds": holds,
        "excludedSeasonEnding": ["Edgerrin Cooper", "Tremaine Edmunds"],
        "displayNames": {DISPLAY_FULL: "TTAB"},
        "eddied": {
            "needs": needs_line(eddies["players"], e_use, e_play),
            "surplus": {
                "LB": [p.name for p in lbs],
                "WR": [p.name for p in wrs],
            },
            "playable": {k: e_play[k] for k in ("RB", "WR", "DL", "LB", "DB")},
            "usable": {k: e_use[k] for k in ("RB", "WR", "DL", "LB", "DB")},
        },
        "method": {
            "offense": (
                f"Offensive ROS points = per-game rate times games left from week {week} through week 17, "
                "minus one if that NFL bye is still ahead. The rate is the week-board consensus in "
                "data/rankings (Wheels Up points). A bye or a blank consensus uses last-3 actuals from that "
                "file. If the player is missing there, the rate is data/player-values.json ppg times 0.90, "
                "the median ratio of the week-8 board to that older file. There is no separate offensive ROS rank file."
            ),
            "idp": (
                f"IDP ROS points are rosPts from data/idp-rankings.json ({idp_horizon}, byes already zeroed in that file). "
                "That file is a top cut, so a rostered IDP missing from it uses player-values ppg times 0.90 "
                "times games left when that rate is at least 8. An active IDP in neither file is a flat "
                "100 ROS (a body, so a missing rank is not an empty room). A reserve IDP in neither file is 50."
            ),
            "injury": (
                "IR, Out, PUP, NFI, and suspended are 0. Achilles or ACL text is 0.15. Doubtful is 0.35. "
                "Questionable is 0.90. An IDP the rankings file already tagged is not discounted twice. "
                "Edgerrin Cooper and Tremaine Edmunds are season-ending and are left out of every side."
            ),
            "valueDelta": (
                "Eddies' optimized lineup rest-of-season points after the swap, minus before. "
                "The lineup is 65% healthy, 25% with Breece Hall sitting, 10% with George Karlaftis sitting, "
                "so RB depth and a second DL count even when the healthy lineup is already full. "
                "partnerDelta is the other club's healthy lineup, same slots, no injury-risk weight."
            ),
            "fit": (
                "Fit is 0-100. Incoming targets are RB, DL, LB, and DB. The other club must be deep at that spot "
                f"({', '.join(f'{n}+ usable {pos}s' for pos, n in DEEP_AT.items())}) "
                "and the idea never asks for their best one. An offense-for-IDP 2-for-1 is allowed. "
                "Giving offense back for offense is allowed when the other bars clear; it is a guideline, not a filter. "
                "The piece the Eddies send has to fill a thin IDP spot (fewer than 2 usable LBs or DLs, or fewer than "
                "3 usable DBs) or a thin WR room, or it has to start for them. Their lineup can drop at most "
                f"{partner_cap:.0f} points when that piece starts for them or fills a real hole. "
                f"Eddies need at least {MIN_DELTA:.0f} blended points, and giving up someone who is in the healthy "
                "lineup has to leave that healthy lineup ahead too. A spot where the Eddies are under the depth bar "
                "scores a bit higher. Bench surplus scores a bit higher than a starter. A name already on a trade "
                "block scores higher. Jordyn Brooks, Cedric Gray, and Josh Downs are never outgoing."
            ),
            "bars": {"playable": PLAYABLE, "usable": USABLE, "thinIfFewerThan": THIN_AT},
            "lineup": "1 QB, 1 RB, 1 WR, 1 TE, 3 RB/WR/TE, 1 DL, 1 LB, 2 DB, 3 IDP. Greedy, same slots as the trade tab.",
        },
        "sources": {
            "rosters": repo_rel(scrape_path),
            "scraped": scrape.get("scraped"),
            "idp": "data/idp-rankings.json",
            "idpGeneratedAt": idp.get("generatedAt"),
            "offenseBoard": f"data/rankings/{latest['file']}",
            "offenseBoardAsOf": board.get("asOf"),
            "playerValues": "data/player-values.json",
            "playerValuesAsOf": values.get("asOf"),
            "seasonEnding": "data/season-ending.json",
        },
        "unvalued": unmatched,
        "notes": notes,
        "leagueDepth": depth,
        "ideas": ideas,
    }
    return doc


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Build data/trade-finder.json from a Fantrax roster scrape.")
    parser.add_argument(
        "--scrape",
        default=str(DEFAULT_SCRAPE),
        help="Fantrax roster scrape JSON. Default: data/sources/fantrax-raw-2026-11-12-pm-normalized.json",
    )
    parser.add_argument("--out", default=str(OUT_PATH), help="Where to write the trade-finder JSON")
    args = parser.parse_args(argv)
    doc = build(Path(args.scrape))
    out = Path(args.out)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {out} ({len(doc['ideas'])} ideas)")
    for idea in doc["ideas"]:
        give = ", ".join(p["name"] for p in idea["give"])
        get = ", ".join(p["name"] for p in idea["get"])
        print(
            f"  {idea['rank']}. {idea['partner']}  give {give}  get {get}  "
            f"delta {idea['valueDelta']}  fit {idea['fitScore']}"
        )


if __name__ == "__main__":
    main()
