#!/usr/bin/env python3
"""Build data/player-values.json for the Wheels Up trade calculator.

Rest-of-season values for the 2026 redraft. Weekly player stats come from the
public Sleeper API and are scored with this league's Fantrax rules (PPR, TE
premium, RB carry bonus, 6-point passing TDs, and the IDP table). The page
reads the JSON file only. It does not call Sleeper.

Run from the repo root:

    python3 scripts/build_player_values.py

Re-run after each week's games lock (Tuesday is a good habit). If Sleeper is
unreachable the script stops and leaves the old file alone.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Snapshots of the public league files. Refresh these from the HQ data
# folder before a rebuild so names match the current rosters.
ROSTER_DIR = ROOT / "data" / "hq" / "rosters"
OUT_PATH = ROOT / "data" / "player-values.json"
FAAB_PATH = ROOT / "data" / "hq" / "faab.json"

SLEEPER = "https://api.sleeper.app/v1"
SEASON = 2026
REGULAR_SEASON_WEEKS = 14  # Fantrax lastRegularSeasonPeriod
RECENCY = 0.72  # each older week is worth 72% of the next week
# A player with 3+ games keeps his own rate. One or two games blend toward
# the median of established players at the position (3-game prior).
TRUST_GAMES = 3
USER_AGENT = "wheels-up-league-hq/player-values"

# First-name nicknames. Used only when the rest of the name and the position
# point at exactly one Sleeper player. Periods, Jr., and hyphens are already
# handled by norm_name.
NICK_GROUPS = (
    {"greg", "gregory"},
    {"ken", "kenneth", "kenny"},
    {"cam", "cameron"},
    {"nate", "nathan", "nathaniel"},
    {"josh", "joshua"},
    {"dax", "daxton"},
    {"mike", "michael"},
    {"chris", "christopher"},
    {"will", "william"},
    {"matt", "matthew"},
    {"tony", "anthony"},
    {"rob", "robert", "robbie"},
    {"nick", "nicholas"},
    {"dan", "daniel"},
    {"alex", "alexander"},
    {"pat", "patrick"},
    {"ben", "benjamin"},
    {"sam", "samuel"},
    {"tom", "thomas"},
    {"joe", "joseph"},
    {"jake", "jacob"},
    {"zach", "zachary", "zac"},
    {"dave", "david"},
    {"steve", "steven", "stephen"},
    {"jeff", "jeffrey"},
    {"jon", "jonathan"},
    {"gabe", "gabriel"},
    {"kam", "kamren"},
    {"quan", "jartavius"},
)

POS_MAP = {
    "QB": "QB",
    "RB": "RB",
    "FB": "RB",
    "WR": "WR",
    "TE": "TE",
    "DL": "DL",
    "DE": "DL",
    "DT": "DL",
    "NT": "DL",
    "EDGE": "DL",
    "LB": "LB",
    "ILB": "LB",
    "OLB": "LB",
    "MLB": "LB",
    "DB": "DB",
    "CB": "DB",
    "S": "DB",
    "FS": "DB",
    "SS": "DB",
}

# League-wide starter demand. Fantrax rosterInfo for hms8onqvmsb3ulsx, 2026:
# 1 QB, 1 RB, 1 WR, 1 TE, 3 RWT, 1 DL, 1 LB, 2 DB, 3 ID. 14 teams.
MIN_STARTERS = {"QB": 14, "RB": 14, "WR": 14, "TE": 14, "DL": 14, "LB": 14, "DB": 28}
SKILL_FLEX = 14 * 3
IDP_FLEX = 14 * 3
SKILL_POS = ("RB", "WR", "TE")
IDP_POS = ("DL", "LB", "DB")
ALL_POS = ("QB", "RB", "WR", "TE", "DL", "LB", "DB")

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        sys.exit(f"Could not reach {url}\n{exc}\nNo values were written.")
    except json.JSONDecodeError as exc:
        sys.exit(f"Bad JSON from {url}\n{exc}\nNo values were written.")


def norm_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("'", "").replace(".", "")
    text = text.replace("-", " ")
    cleaned = []
    for ch in text:
        if ch.isalpha() or ch.isspace():
            cleaned.append(ch)
    parts = [p for p in "".join(cleaned).split() if p not in SUFFIXES]
    return " ".join(parts)


def map_position(player: dict) -> str | None:
    raw = player.get("position") or ""
    if raw in POS_MAP:
        return POS_MAP[raw]
    for pos in player.get("fantasy_positions") or []:
        if pos in POS_MAP:
            return POS_MAP[pos]
    return None


def num(stats: dict, key: str) -> float:
    value = stats.get(key)
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def intervals(stat: float, every: float, cap: float) -> int:
    """How many scoring chunks fit in stat, from 0 up to cap. Fantrax floors."""
    if stat <= 0 or every <= 0:
        return 0
    span = min(stat, cap)
    return int((span + 1e-9) / every)


def band_intervals(stat: float, start: float, end: float, every: float) -> int:
    if stat <= start or every <= 0:
        return 0
    span = min(stat, end) - start
    if span <= 0:
        return 0
    return int((span + 1e-9) / every)


def score_week(stats: dict, pos: str) -> float:
    """Fantrax scoringCategorySettings for Wheels Up Collective, 2026."""
    pts = 0.0

    pass_yd = num(stats, "pass_yd")
    pts += intervals(pass_yd, 25, 600) * 1
    pts += band_intervals(pass_yd, 200, 600, 100) * 6
    pts += num(stats, "pass_td") * 6
    pts += num(stats, "pass_td_50p") * 6  # bonus on top of the TD
    pts += num(stats, "pass_int") * -3
    pts += num(stats, "pass_int_td") * -3
    pts += num(stats, "pass_2pt") * 2

    pts += intervals(num(stats, "rush_att"), 7, 50) * 1
    rush_yd = num(stats, "rush_yd")
    pts += intervals(rush_yd, 10, 500) * 1
    pts += intervals(rush_yd, 100, 500) * 6
    pts += num(stats, "rush_td") * 6
    # rush_td_40p includes 50+ yard scores. Both the 40-49 and 50+ bonuses are +6.
    pts += num(stats, "rush_td_40p") * 6
    pts += num(stats, "rush_2pt") * 2

    rec = num(stats, "rec")
    if pos == "TE":
        pts += rec * 1.5
        pts += num(stats, "rec_fd") * 0.5
    else:
        pts += rec * 1.0
    rec_yd = num(stats, "rec_yd")
    pts += intervals(rec_yd, 10, 600) * 1
    pts += intervals(rec_yd, 100, 600) * 6
    pts += num(stats, "rec_td") * 6
    pts += num(stats, "rec_td_50p") * 6
    pts += num(stats, "rec_2pt") * 2

    pts += num(stats, "fum_lost") * -3
    pts += intervals(num(stats, "kr_yd"), 10, 500)
    pts += intervals(num(stats, "pr_yd"), 10, 500)
    pts += (num(stats, "st_td") + num(stats, "kr_td") + num(stats, "pr_td")) * 6

    solo = num(stats, "idp_tkl_solo")
    ast = num(stats, "idp_tkl_ast")
    pts += solo * 2
    pts += ast * 1
    tackles = num(stats, "idp_tkl")
    if tackles <= 0:
        tackles = solo + ast
    pts += intervals(tackles, 5, 40) * 3
    sacks = num(stats, "idp_sack")
    pts += intervals(sacks, 0.5, 15) * 3
    pts += num(stats, "idp_tkl_loss") * 3
    pts += num(stats, "idp_pass_def") * (4 if pos == "DL" else 3)
    pts += num(stats, "idp_int") * 6
    pts += intervals(num(stats, "idp_int_ret_yd"), 10, 200)
    pts += num(stats, "idp_ff") * 3
    pts += num(stats, "idp_fum_rec") * 3
    pts += intervals(num(stats, "idp_fum_ret_yd"), 10, 200)
    # Sleeper QB hits include sacks almost all of the time. Pay the extras only.
    pts += max(0.0, num(stats, "idp_qb_hit") - sacks) * 1
    pts += num(stats, "idp_def_td") * 6
    pts += max(num(stats, "idp_blk_kick"), num(stats, "blk_kick")) * 6
    # Player-level safeties and "stuffs" are not in this feed. See README.
    return pts


def played(stats: dict) -> bool:
    if num(stats, "gms_active") > 0 or num(stats, "gp") > 0:
        return True
    return num(stats, "off_snp") > 0 or num(stats, "def_snp") > 0


def availability(player: dict, roster_note: str) -> tuple[float, str]:
    """Light rest-of-season discount. A one-week IR stash is not a season-ender."""
    status = (player.get("injury_status") or "").strip().lower()
    notes = f"{player.get('injury_notes') or ''} {roster_note or ''}".lower()
    severe = any(
        word in notes
        for word in ("acl", "achilles", "pup", "ir-r", "out indefinitely", "season-ending", "season ending")
    )
    label = ""
    mult = 1.0
    if severe:
        mult, label = 0.25, "out a while"
    elif status in {"ir", "injured reserve", "pup", "nfi"} or "injured reserve" in notes:
        mult, label = 0.4, "IR"
    elif "ir slot" in notes or "(reserve)" in notes:
        # Parked in a fantasy IR slot, usually questionable, not done for the year.
        mult, label = 0.88, "IR slot"
    elif status == "out" or re_search_out(notes):
        mult, label = 0.75, "Out"
    elif status == "doubtful":
        mult, label = 0.85, "Doubtful"
    elif status in {"questionable", "q"}:
        mult, label = 0.97, "Q"
    elif status == "suspended":
        mult, label = 0.6, "suspended"
    if not player.get("team"):
        mult = min(mult, 0.35)
        label = label or "no NFL team"
    return mult, label


def re_search_out(notes: str) -> bool:
    return " out" in f" {notes}" and "out indefinitely" not in notes


def split_flag(flag: str) -> tuple[str, str]:
    for sep in (" — ", " – ", " - "):
        if sep in flag:
            name, detail = flag.split(sep, 1)
            return name.strip(), detail.strip()
    return "", ""


def load_rosters():
    rows = []
    injury_notes = {}
    ir_keys = set()
    for path in sorted(ROSTER_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        data = json.loads(path.read_text())
        team_id = data.get("teamId") or path.stem
        roster = data.get("roster") or {}
        for name in roster.get("IR") or []:
            ir_keys.add(norm_name(name))
        on_club = set()
        for pos, names in roster.items():
            if pos == "IR" or pos not in ALL_POS:
                continue
            for name in names:
                on_club.add(norm_name(name))
        for flag in (data.get("injuryFlags") or data.get("flags") or []):
            name, detail = split_flag(str(flag))
            key = norm_name(name)
            # Ignore a flag left behind after the player changed clubs.
            if key and detail and key in on_club:
                injury_notes[key] = detail
        for pos, names in roster.items():
            if pos == "IR" or pos not in ALL_POS:
                continue
            for name in names:
                rows.append({"teamId": team_id, "pos": pos, "name": name, "key": norm_name(name)})
    return rows, injury_notes, ir_keys


def nickname_keys(key: str) -> list[str]:
    parts = key.split()
    if len(parts) < 2:
        return []
    first, rest = parts[0], parts[1:]
    alts = []
    for group in NICK_GROUPS:
        if first not in group:
            continue
        for alt in group:
            if alt != first:
                alts.append(" ".join([alt, *rest]))
    return alts


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - rank) + ordered[hi] * (rank - lo)


def main() -> None:
    state = fetch_json(f"{SLEEPER}/state/nfl")
    if str(state.get("season")) != str(SEASON) or state.get("season_type") != "regular":
        sys.exit(
            f"Sleeper is not in the {SEASON} regular season "
            f"(got season={state.get('season')} type={state.get('season_type')}). "
            "No values were written."
        )
    current_week = int(state["week"])
    completed = list(range(1, current_week))
    if not completed:
        sys.exit("No completed 2026 weeks yet. No values were written.")

    print(f"Sleeper week {current_week}. Scoring completed weeks {completed[0]}–{completed[-1]}.")
    players_raw = fetch_json(f"{SLEEPER}/players/nfl")
    weekly = {}
    for week in completed:
        weekly[week] = fetch_json(f"{SLEEPER}/stats/nfl/regular/{SEASON}/{week}")
        print(f"  week {week}: {len(weekly[week])} stat rows")

    teams_by_week = {}
    for week, stats in weekly.items():
        teams_by_week[week] = {
            pid.replace("TEAM_", "")
            for pid in stats
            if str(pid).startswith("TEAM_")
        }
    all_teams = set().union(*teams_by_week.values()) if teams_by_week else set()
    bye_taken = {
        team: any(team not in teams_by_week[week] for week in completed)
        for team in all_teams
    }

    catalog = {}
    for pid, player in players_raw.items():
        if not str(pid).isdigit() or not isinstance(player, dict):
            continue
        pos = map_position(player)
        full = player.get("full_name") or ""
        if not pos or not full:
            continue
        catalog[pid] = player

    # points[pid][week] = scored points, only for games played
    points = defaultdict(dict)
    for week, stats_by_player in weekly.items():
        for pid, stats in stats_by_player.items():
            if pid not in catalog or not played(stats):
                continue
            pos = map_position(catalog[pid])
            points[pid][week] = score_week(stats, pos)

    weeks_remaining = max(0, REGULAR_SEASON_WEEKS - len(completed))
    last_week = completed[-1]

    roster_rows, injury_notes, ir_keys = load_rosters()

    built = []
    for pid, weeks in points.items():
        player = catalog[pid]
        pos = map_position(player)
        games = len(weeks)
        if games < 1 or pos not in ALL_POS:
            continue
        weight_sum = 0.0
        weighted_pts = 0.0
        for week, pts in weeks.items():
            weight = RECENCY ** (last_week - week)
            weight_sum += weight
            weighted_pts += pts * weight
        raw_ppg = weighted_pts / weight_sum if weight_sum else 0.0
        played = sorted(weeks)
        recent = played[-3:]
        last3 = sum(weeks[w] for w in recent) / len(recent) if recent else 0.0
        team = player.get("team") or ""
        built.append(
            {
                "pid": pid,
                "name": player["full_name"],
                "key": norm_name(player["full_name"]),
                "pos": pos,
                "nflTeam": team or "FA",
                "team": team,
                "games": games,
                "rawPpg": raw_ppg,
                "last3Ppg": last3,
                "player": player,
            }
        )

    by_pos = defaultdict(list)
    for row in built:
        by_pos[row["pos"]].append(row)

    priors = {}
    for pos, rows in by_pos.items():
        sample = [r["rawPpg"] for r in rows if r["games"] >= TRUST_GAMES and r["rawPpg"] > 0]
        if len(sample) < 8:
            sample = [r["rawPpg"] for r in rows if r["games"] >= 2 and r["rawPpg"] > 0]
        priors[pos] = statistics.median(sample) if sample else 0.0

    for row in built:
        games = row["games"]
        if games >= TRUST_GAMES:
            row["adjPpg"] = row["rawPpg"]
        else:
            prior = priors.get(row["pos"], 0.0)
            # 1 game -> one-third own rate. 2 games -> two-thirds.
            row["adjPpg"] = (row["rawPpg"] * games + prior * (TRUST_GAMES - games)) / TRUST_GAMES

    # Starter pool, then replacement = best player at the position who does not start.
    ranked = {pos: sorted(rows, key=lambda r: -r["adjPpg"]) for pos, rows in by_pos.items()}
    starter_ids = set()
    for pos, count in MIN_STARTERS.items():
        for row in ranked.get(pos, [])[:count]:
            starter_ids.add(row["pid"])

    def fill_flex(positions: tuple[str, ...], slots: int) -> None:
        pool = []
        for pos in positions:
            for row in ranked.get(pos, []):
                if row["pid"] not in starter_ids:
                    pool.append(row)
        pool.sort(key=lambda r: -r["adjPpg"])
        for row in pool[:slots]:
            starter_ids.add(row["pid"])

    fill_flex(SKILL_POS, SKILL_FLEX)
    fill_flex(IDP_POS, IDP_FLEX)

    replacement = {}
    for pos, rows in ranked.items():
        outside = [r for r in rows if r["pid"] not in starter_ids]
        replacement[pos] = outside[0]["adjPpg"] if outside else 0.0

    # Match roster rows onto Sleeper ids. Position breaks ties.
    by_key = defaultdict(list)
    for row in built:
        by_key[row["key"]].append(row)

    matched_pid_by_roster = {}
    unmatched = []
    ambiguous = []

    def choose(cands: list[dict], pos: str):
        same = [c for c in cands if c["pos"] == pos]
        pool = same or cands
        pool = sorted(pool, key=lambda c: (-c["games"], -c["adjPpg"]))
        return pool[0], len({c["pid"] for c in pool}) > 1 and len(same) != 1

    for roster in roster_rows:
        cands = by_key.get(roster["key"]) or []
        nick_match = False
        if not cands:
            nick_pool = []
            for alt in nickname_keys(roster["key"]):
                for cand in by_key.get(alt) or []:
                    if cand["pos"] == roster["pos"]:
                        nick_pool.append(cand)
            # Only accept a nickname when one player fits. Two Gregorys stay unmatched.
            unique = {c["pid"]: c for c in nick_pool}
            if len(unique) == 1:
                cands = list(unique.values())
                nick_match = True
        if not cands:
            unmatched.append(roster)
            continue
        pick, is_ambiguous = choose(cands, roster["pos"])
        matched_pid_by_roster[(roster["teamId"], roster["name"])] = pick["pid"]
        if nick_match:
            pick.setdefault("rosterAliases", set()).add(roster["name"])
        if is_ambiguous and not nick_match:
            ambiguous.append(
                {
                    "teamId": roster["teamId"],
                    "name": roster["name"],
                    "position": roster["pos"],
                    "used": pick["name"],
                    "also": sorted({c["name"] for c in cands if c["pid"] != pick["pid"]}),
                }
            )

    notes_by_pid = {}
    ir_pids = set()
    for roster in roster_rows:
        pid = matched_pid_by_roster.get((roster["teamId"], roster["name"]))
        if not pid:
            continue
        if roster["key"] in injury_notes:
            notes_by_pid[pid] = injury_notes[roster["key"]]
        if roster["key"] in ir_keys:
            ir_pids.add(pid)

    records = []
    for row in built:
        player = row["player"]
        note = notes_by_pid.get(row["pid"], "")
        if row["pid"] in ir_pids and "ir slot" not in note.lower() and "reserve" not in note.lower():
            note = (note + " IR slot").strip()
        mult, injury = availability(player, note)
        bye_left = 0 if (row["team"] and bye_taken.get(row["team"])) or not row["team"] else 1
        if weeks_remaining == 0:
            bye_left = 0
        expected = max(0.0, weeks_remaining - bye_left) * mult
        vor = row["adjPpg"] - replacement.get(row["pos"], 0.0)
        trade_ppg = max(0.0, vor)
        value = round(trade_ppg * expected, 1)
        aliases = []
        records.append(
            {
                "name": row["name"],
                "position": row["pos"],
                "nflTeam": row["nflTeam"],
                "value": value,
                "ppg": round(row["adjPpg"], 1),
                "last3Ppg": round(row["last3Ppg"], 1),
                "games": row["games"],
                "asOf": date.today().isoformat(),
                "injury": injury,
                "pid": row["pid"],
                "key": row["key"],
                "vorPpg": round(vor, 2),
                "expectedGames": round(expected, 2),
                "starterPool": row["pid"] in starter_ids,
                "_aliases": aliases,
            }
        )

    # Attach roster spellings that differ from the Sleeper name.
    alias_for = defaultdict(set)
    for roster in roster_rows:
        pid = matched_pid_by_roster.get((roster["teamId"], roster["name"]))
        if not pid:
            continue
        alias_for[pid].add(roster["name"])

    by_pid = {row["pid"]: row for row in records}
    for pid, names in alias_for.items():
        row = by_pid.get(pid)
        if not row:
            continue
        for name in sorted(names):
            if norm_name(name) != row["key"] and name != row["name"]:
                row["_aliases"].append(name)

    # FAAB: price a fringe starter (bottom 30% of players who clear replacement
    # by at least half a point per game) at the median *serious* waiver bid.
    # Serious = settled claims of $10 or more in data/faab.json. The $1–$9
    # claims are dart throws, not the price of a lineup player.
    claim_amounts = []
    if FAAB_PATH.exists():
        faab_doc = json.loads(FAAB_PATH.read_text())
        for claim in faab_doc.get("claims") or []:
            amount = claim.get("amount") or 0
            if amount >= 10:
                claim_amounts.append(amount)
    anchor = statistics.median(claim_amounts) if claim_amounts else 15
    clearers = [r for r in records if r["vorPpg"] >= 0.5]
    cutoff = percentile([r["vorPpg"] for r in clearers], 0.30) if clearers else 0
    fringe = [r for r in clearers if r["vorPpg"] <= cutoff] or clearers
    fringe_value = statistics.median([r["value"] for r in fringe]) if fringe else 0
    points_per_dollar = round(fringe_value / anchor, 3) if anchor else 0

    # Public records: drop internal keys the page does not need, keep aliases.
    public = []
    for row in records:
        item = {
            "name": row["name"],
            "position": row["position"],
            "nflTeam": row["nflTeam"],
            "value": row["value"],
            "ppg": row["ppg"],
            "last3Ppg": row["last3Ppg"],
            "games": row["games"],
            "asOf": row["asOf"],
        }
        if row["injury"]:
            item["injury"] = row["injury"]
        if row["_aliases"]:
            item["aliases"] = row["_aliases"]
        public.append(item)
    public.sort(key=lambda r: (-r["value"], r["position"], r["name"]))

    unmatched_out = [
        {"teamId": r["teamId"], "name": r["name"], "position": r["pos"]}
        for r in unmatched
    ]
    # Same player name left unmatched on two clubs should be listed once per club.

    payload = {
        "asOf": date.today().isoformat(),
        "season": SEASON,
        "leagueType": "redraft",
        "weekThrough": completed[-1],
        "weeksRemaining": weeks_remaining,
        "byeWeeksAssumedLeft": 1,
        "method": (
            "Each player's 2026 weekly Sleeper stat line is scored with this league's "
            "Fantrax rules, including TE premium (1.5 per catch and +0.5 per TE receiving "
            "first down), +1 per 7 carries, 6-point passing touchdowns, the long-score "
            "bonuses, and the IDP tackle/sack/turnover table. Recent weeks count more "
            f"(each older week is weighted {RECENCY}). Players with three or more games "
            "keep that rate. A one- or two-game sample is blended toward the position's "
            "established median so one blow-up week cannot set the price. Value is that rate "
            "minus the replacement starter at the position — 14 teams, the real starting "
            "slots — times games left in the 14-week regular season, with one bye removed "
            "if that NFL team has not had one yet. IR, Out, and season-ending notes trim "
            "the games left. Playoff weeks are not included. Stuffs and individual safeties "
            "are not in the public weekly feed, so those two categories are left out."
        ),
        "lineup": {
            "QB": 1,
            "RB": 1,
            "WR": 1,
            "TE": 1,
            "RWT": 3,
            "DL": 1,
            "LB": 1,
            "DB": 2,
            "ID": 3,
            "source": (
                "Fantrax rosterInfo for league hms8onqvmsb3ulsx (2026): "
                "1 QB, 1 RB, 1 WR, 1 TE, 3 RB/WR/TE, 1 DL, 1 LB, 2 DB, 3 IDP flex. "
                "scoring.html prints the IDP slots only."
            ),
        },
        "replacementPpg": {pos: round(replacement.get(pos, 0), 2) for pos in ALL_POS},
        "faab": {
            "pointsPerDollar": points_per_dollar,
            "anchorDollars": anchor,
            "fringeValue": round(fringe_value, 1),
            "note": (
                f"${anchor:g} is the median settled waiver bid of $10 or more. "
                f"That buys a fringe starter worth about {fringe_value:.1f} value points "
                f"on this board, so one FAAB dollar is {points_per_dollar} value points."
            ),
        },
        "unmatchedRostered": unmatched_out,
        "ambiguous": ambiguous,
        "counts": {
            "players": len(public),
            "rosterSpots": len(roster_rows),
            "unmatched": len(unmatched_out),
        },
        "players": public,
    }

    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {OUT_PATH} ({len(public)} players).")
    print(f"FAAB: {payload['faab']['note']}")
    print(f"Unmatched rostered: {len(unmatched_out)}")
    for row in unmatched_out:
        print(f"  {row['teamId']:12} {row['position']:3} {row['name']}")
    if ambiguous:
        print(f"Ambiguous name matches: {len(ambiguous)}")
        for row in ambiguous:
            print(f"  {row['teamId']:12} {row['name']} -> {row['used']} also {row['also']}")

    print("\nTop of the board")
    for pos in ALL_POS:
        group = [r for r in public if r["position"] == pos][:5]
        print(f" {pos}")
        for row in group:
            print(f"   {row['value']:7.1f}  {row['ppg']:5.1f} ppg  {row['games']}g  {row['name']} ({row['nflTeam']})")


if __name__ == "__main__":
    main()
