#!/usr/bin/env python3
"""Build data/trade-finder.json — rest-of-season trade ideas for the Eddies.

Recommend-only. This script reads league files that are already in the repo
and writes a ranked list. It does not send, propose, or enter a trade, and it
does not contact Fantrax.

Run from the repo root:

    python3 scripts/build_trade_finder.py
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import warroom_common as wc  # noqa: E402

SCRAPE_PATH = ROOT / "data" / "sources" / "fantrax-raw-2026-10-30-am.json"
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
# Surplus Bill said we can move. Brooks and Gray are listed in the room and are not here.
LB_OUT = ("Fred Warner", "Frankie Luvu", "Trenton Simpson", "Tyrice Knight")
WR_OUT = ("Ja'Kobi Lane", "Kendrick Bourne", "Chimere Dike")

# Playable = would start on a thin roster. Usable = real surplus / a back we'd want.
# Bars are rest-of-season points on the week-8 scale (about 10 games left).
PLAYABLE = {"QB": 120, "RB": 80, "WR": 70, "TE": 70, "DL": 80, "LB": 80, "DB": 80}
USABLE = {"QB": 160, "RB": 90, "WR": 100, "TE": 90, "DL": 120, "LB": 120, "DB": 120}
THIN_AT = {"LB": 2, "DL": 2, "DB": 3, "WR": 3, "RB": 2}
# Lineup value is mostly the healthy roster, plus weight for the two thin spots
# (Hall's quad, and Karlaftis as the only DL) sitting.
HEALTHY_W, HALL_W, DL_W = 0.65, 0.25, 0.10
MIN_DELTA = 3.0
MIN_PARTNER_DELTA = -8.0
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


def give_packages(by_name: dict[str, Player]) -> list[list[Player]]:
    lbs = [by_name[n] for n in LB_OUT if n in by_name]
    wrs = [by_name[n] for n in WR_OUT if n in by_name]
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


def fit_score(give, get, eddies_delta, partner_delta, healthy_delta, playable, usable, block_get, block_give, surplus_piece, starts_for_them, gives_starter) -> int | None:
    got = get[0]
    holes = sent_holes(give, usable, playable)
    if max(p.ros for p in give) < 70 and not any(p.pos == "LB" for p in give):
        return None
    # A piece that would not start, sent at a position they are not thin at, does nothing for them.
    if not holes and not starts_for_them:
        return None
    if got.pos == "RB":
        if usable.get("RB", 0) < 3:
            return None
        score = 22 + (10 if usable["RB"] >= 4 else 6)
    elif got.pos == "DL":
        if usable.get("DL", 0) < 3:
            return None
        score = 14 + (10 if usable["DL"] >= 4 else 6)
    else:
        return None
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
    elif holes and partner_delta >= MIN_PARTNER_DELTA:
        score += 8
    elif starts_for_them and partner_delta >= -4:
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
    deep = usable.get("RB", 0) if get.pos == "RB" else usable.get("DL", 0)
    kind = "back" if get.pos == "RB" else "lineman"
    room = "RB" if get.pos == "RB" else "DL"
    even = " Their lineup stays about even." if partner_delta < 1 else ""
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
    usable = [
        p for p in players
        if p.pos == pos and p.usable() and not p.assumed and p.mult >= 0.85 and p.slot != "ir"
    ]
    usable.sort(key=lambda p: (-p.ros, p.name))
    if len(usable) < 3:
        return []
    best = usable[0].name
    out = []
    for p in usable:
        if p.name == best:
            continue
        if len(usable) - 1 < 2:
            continue
        out.append(p)
    return out


def consider(eddies, partner_players, give, get, playable, usable, eddies_starters, their_block, our_block):
    if get.season_ending or any(p.season_ending for p in give):
        return None
    if any(p.name in KEEPS for p in give):
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


def build() -> dict:
    scrape = load_json(SCRAPE_PATH)
    idp = load_json(IDP_PATH)
    latest = load_json(RANK_DIR / "latest.json")
    board = load_json(RANK_DIR / latest["file"])
    values = load_json(VALUES_PATH)
    teams_doc = load_json(TEAMS_PATH)
    season = wc.season_ending(ROOT / "data")
    week = int(idp.get("week") or latest.get("week") or 8)
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
        for raw in entry.get("players") or []:
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
    missing = [n for n in list(LB_OUT) + list(WR_OUT) if n not in by_name]
    if missing:
        raise SystemExit(f"Eddies surplus names missing from the scrape: {missing}")
    for keep in KEEPS:
        if keep not in by_name:
            raise SystemExit(f"Keep {keep} is not on the Eddies roster")

    _, starters = optimize(eddies["players"])
    packages = give_packages(by_name)
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
        gets = spare_candidates(team["players"], "RB") + spare_candidates(team["players"], "DL")
        for get in gets:
            for give in packages:
                row = consider(
                    eddies["players"], team["players"], give, get, playable, usable,
                    starters, team["block"], our_block,
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
    if not any(p["pos"] == "DL" for idea in ideas for p in idea["get"]):
        notes.append(
            "No club has three usable DLs to spare, so none of these ideas bring back a second defensive lineman."
        )

    e_play = count_pos(eddies["players"], lambda p: p.playable())
    e_use = count_pos(eddies["players"], lambda p: p.usable())
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
        "excludedSeasonEnding": ["Edgerrin Cooper", "Tremaine Edmunds"],
        "displayNames": {DISPLAY_FULL: "TTAB"},
        "eddied": {
            "needs": "RB depth (Hall is the only healthy back; Charbonnet is an ACL tag) and a second DL behind Karlaftis.",
            "surplus": {
                "LB": list(LB_OUT),
                "WR": list(WR_OUT),
            },
            "playable": {k: e_play[k] for k in ("RB", "WR", "DL", "LB", "DB")},
            "usable": {k: e_use[k] for k in ("RB", "WR", "DL", "LB", "DB")},
        },
        "method": {
            "offense": (
                "Offensive ROS points = per-game rate times games left from this week through week 17, "
                "minus one if that NFL bye is still ahead. The rate is the week-board consensus in "
                "data/rankings (Wheels Up points). A bye or a blank consensus uses last-3 actuals from that "
                "file. If the player is missing there, the rate is data/player-values.json ppg times 0.90, "
                "the median ratio of the week-8 board to that older file. There is no separate offensive ROS rank file."
            ),
            "idp": (
                "IDP ROS points are rosPts from data/idp-rankings.json (weeks 8-17, byes already zeroed). "
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
                "Fit is 0-100. The other club must be deep at the spot they give (3+ usable RBs, or 3+ usable DLs) "
                "and we do not ask for their best one. The piece the Eddies send has to be a fit: it fills a thin "
                "IDP spot (fewer than 2 usable LBs or DLs, or fewer than 3 usable DBs) or a thin WR room, or it "
                "would actually start for them. Their lineup can drop at most 8 points in a real hole, or 4 when "
                "it is an upgrade rather than a hole. Eddies need at least 3 blended points, and giving up someone "
                "who is in the healthy lineup has to leave that healthy lineup ahead too. Bench surplus scores a "
                "bit higher than a starter. A name already on a trade block scores higher. "
                "Jordyn Brooks and Cedric Gray are never outgoing."
            ),
            "bars": {"playable": PLAYABLE, "usable": USABLE, "thinIfFewerThan": THIN_AT},
            "lineup": "1 QB, 1 RB, 1 WR, 1 TE, 3 RB/WR/TE, 1 DL, 1 LB, 2 DB, 3 IDP. Greedy, same slots as the trade tab.",
        },
        "sources": {
            "rosters": "data/sources/fantrax-raw-2026-10-30-am.json",
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


def main() -> None:
    doc = build()
    OUT_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {OUT_PATH} ({len(doc['ideas'])} ideas)")
    for idea in doc["ideas"]:
        give = ", ".join(p["name"] for p in idea["give"])
        get = ", ".join(p["name"] for p in idea["get"])
        print(
            f"  {idea['rank']}. {idea['partner']}  give {give}  get {get}  "
            f"delta {idea['valueDelta']}  fit {idea['fitScore']}"
        )


if __name__ == "__main__":
    main()
