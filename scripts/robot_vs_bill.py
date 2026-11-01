#!/usr/bin/env python3
"""Robot vs. The Eddies scoreboard.

Locks a Robot start/sit lineup before the first kickoff, then scores it
against the Eddies Fantrax lineup. Weeks before Week 9 are refused.
Points stay null until a week is final. A bye or an inactive player scores 0.
A player who starts on both sides is counted once on each side.

Written files only keep an allowlist of keys. Personal names, bids, claims,
and trades are not stored.
"""
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from warroom_common import PT, iso_pt, parse_now

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "robot-vs-bill"
SEASON_YEAR = 2026
FIRST_WEEK = 9
WEEK1 = date(2026, 9, 10)  # Thursday
SCHEMA_VERSION = 1
SLOTS = (
    "QB", "RB", "WR", "TE",
    "FLEX", "FLEX", "FLEX",
    "DL", "LB", "DB", "DB",
    "IDP", "IDP", "IDP",
)
ELIGIBLE = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "FLEX": {"RB", "WR", "TE"},
    "DL": {"DL"},
    "LB": {"LB"},
    "DB": {"DB"},
    "IDP": {"DL", "LB", "DB"},
}
POSITIONS = {"QB", "RB", "WR", "TE", "DL", "LB", "DB"}
LOCK_KEYS = {"week", "firstKickoff", "lineup", "season"}
SCORE_KEYS = {"week", "status", "actual", "points", "bye", "inactive", "season"}
PLAYER_KEYS = {"slot", "player", "pos", "team"}
TEAM_RE = re.compile(r"^[A-Z]{2,4}$")
# Key fragments that must never be written. Built so the source does not spell them.
_BANNED_KEY = re.compile(
    "faab|waiver|bids?|claims?|" + "own" + "er|" + "trades?",
    re.I,
)


class Refusal(Exception):
    """A locked lineup cannot be changed, or the clock is past kickoff."""


def norm_name(name):
    return " ".join(str(name or "").casefold().split())


def week_file(week):
    return f"w{int(week):02d}.json"


def week_window(week):
    """NFL game window for a Fantrax week: Thursday through Monday."""
    start = WEEK1 + timedelta(days=(int(week) - 1) * 7)
    end = start + timedelta(days=4)
    if start.month == end.month:
        label = f"{start.strftime('%b')} {start.day}\u2013{end.day}"
    else:
        label = f"{start.strftime('%b')} {start.day}\u2013{end.strftime('%b')} {end.day}"
    return {"start": start.isoformat(), "end": end.isoformat(), "label": label}


def r1(value):
    return Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def num(value):
    if isinstance(value, bool) or value is None:
        raise InputError("points must be numbers")
    try:
        out = r1(value)
    except Exception as exc:
        raise InputError("points must be numbers") from exc
    if not out.is_finite():
        raise InputError("points must be numbers")
    return out


def as_float(value):
    if value is None:
        return None
    return float(value)


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def load_json(path):
    return json.loads(Path(path).read_text())


def parse_clock(value):
    if isinstance(value, datetime):
        dt = value if value.tzinfo else parse_now(value.isoformat())
    else:
        dt = parse_now(str(value))
    return dt.astimezone(PT)


class InputError(ValueError):
    """The input file is not a lineup or a score file this board can use."""


def reject_keys(obj, where):
    if isinstance(obj, dict):
        for key in obj:
            if _BANNED_KEY.search(str(key)):
                raise InputError(f"{where} has a field this board does not keep")
            reject_keys(obj[key], where)
    elif isinstance(obj, list):
        for item in obj:
            reject_keys(item, where)


def require_week(value):
    try:
        week = int(value)
    except (TypeError, ValueError):
        raise InputError("week must be an integer") from None
    if week < FIRST_WEEK:
        raise InputError(f"this board starts at week {FIRST_WEEK}")
    if week > 18:
        raise InputError("week is out of range")
    return week


def require_season(value):
    if value is None:
        return SEASON_YEAR
    try:
        season = int(value)
    except (TypeError, ValueError):
        raise InputError("season must be 2026") from None
    if season != SEASON_YEAR:
        raise InputError("season must be 2026")
    return season


def check_allowlist(doc, allowed, where):
    extra = set(doc) - allowed
    if extra:
        raise InputError(f"{where} has a field this board does not keep")


def validate_lineup(rows, where):
    if not isinstance(rows, list) or len(rows) != len(SLOTS):
        raise InputError(f"{where} needs {len(SLOTS)} players in slot order")
    seen = set()
    out = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise InputError(f"{where} row {index + 1} is not a player")
        check_allowlist(row, PLAYER_KEYS, f"{where} row {index + 1}")
        reject_keys(row, where)
        slot = row.get("slot")
        if slot != SLOTS[index]:
            raise InputError(
                f"{where} row {index + 1} must be {SLOTS[index]} in canonical order"
            )
        player = " ".join(str(row.get("player") or "").split())
        if len(player) < 2:
            raise InputError(f"{where} row {index + 1} needs a player")
        pos = str(row.get("pos") or "").upper()
        if pos not in ELIGIBLE[slot]:
            raise InputError(f"{where} {player} cannot fill {slot}")
        team = str(row.get("team") or "").upper()
        if not TEAM_RE.match(team):
            raise InputError(f"{where} {player} needs an NFL team abbreviation")
        key = norm_name(player)
        if key in seen:
            raise InputError(f"{where} lists {player} twice")
        seen.add(key)
        out.append({"slot": slot, "player": player, "pos": pos, "team": team, "points": None})
    return out


def is_locked(doc):
    if not doc:
        return False
    if doc.get("robotLockedAt"):
        return True
    return bool(doc.get("robot"))


def lineup_identity(rows):
    return [
        (row["slot"], norm_name(row["player"]), row["pos"], row["team"])
        for row in rows or []
    ]


def empty_week(week):
    return {
        "schemaVersion": SCHEMA_VERSION,
        "season": SEASON_YEAR,
        "week": week,
        "window": week_window(week),
        "status": "pending",
        "robotLockedAt": None,
        "firstKickoff": None,
        "robot": [],
        "actual": [],
        "totals": {"robot": None, "eddies": None},
        "margin": None,
        "result": None,
        "winner": None,
        "decisions": [],
    }


def read_week(data_dir, week):
    path = Path(data_dir) / week_file(week)
    if not path.exists():
        return None
    return load_json(path)


def decisions_for(robot, actual, scored):
    """One decision per slot index whose starters are different players."""
    out = []
    for index, row in enumerate(robot):
        other = actual[index]
        if norm_name(row["player"]) == norm_name(other["player"]):
            continue
        swing = None
        if scored and row["points"] is not None and other["points"] is not None:
            swing = as_float(r1(Decimal(str(row["points"])) - Decimal(str(other["points"]))))
        out.append({
            "slot": row["slot"],
            "index": index,
            "robotPlayer": row["player"],
            "robotPos": row["pos"],
            "robotTeam": row["team"],
            "robotPoints": row["points"],
            "eddiesPlayer": other["player"],
            "eddiesPos": other["pos"],
            "eddiesTeam": other["team"],
            "eddiesPoints": other["points"],
            "swing": swing,
        })
    return out


def result_for(margin):
    if margin > 0:
        return "W", "Robot"
    if margin < 0:
        return "L", "Eddies"
    return "T", "tie"


def apply_points(rows, table, scored):
    out = []
    for row in rows:
        copy = dict(row)
        copy["points"] = as_float(table[norm_name(row["player"])]) if scored else None
        out.append(copy)
    return out


def point_table(robot, actual, raw_points, bye, inactive):
    if not isinstance(raw_points, dict):
        raise InputError("points must be an object of player names")
    if not isinstance(bye, list) or not isinstance(inactive, list):
        raise InputError("bye and inactive must be lists of names")
    reject_keys(raw_points, "points")
    table = {}
    for name, value in raw_points.items():
        table[norm_name(name)] = num(value)
    forced = {norm_name(name) for name in list(bye) + list(inactive)}
    for name in forced:
        if not name:
            raise InputError("bye and inactive entries need a player")
    needed = [row["player"] for row in robot + actual]
    out = {}
    for player in needed:
        key = norm_name(player)
        if key in forced:
            out[key] = Decimal("0.0")
        elif key not in table:
            raise InputError(f"missing points for {player}")
        else:
            out[key] = table[key]
    return out


def sum_points(rows):
    total = sum((Decimal(str(row["points"])) for row in rows), Decimal("0"))
    return r1(total)


def rebuild_season(data_dir):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    weeks = []
    wins = losses = ties = 0
    robot_points = Decimal("0")
    eddies_points = Decimal("0")
    for path in sorted(data_dir.glob("w[0-9][0-9].json")):
        doc = load_json(path)
        reject_keys(doc, path.name)
        week = require_week(doc.get("week"))
        if path.name != week_file(week):
            raise InputError(f"{path.name} does not match week {week}")
        if doc.get("status") not in ("pending", "final"):
            raise InputError(f"week {week} status must be pending or final")
        totals = doc.get("totals") or {}
        summary = {
            "week": week,
            "file": path.name,
            "window": doc.get("window") or week_window(week),
            "status": doc["status"],
            "locked": is_locked(doc),
            "robotLockedAt": doc.get("robotLockedAt"),
            "result": doc.get("result"),
            "winner": doc.get("winner"),
            "robotPoints": totals.get("robot"),
            "eddiesPoints": totals.get("eddies"),
            "margin": doc.get("margin"),
            "decisions": doc.get("decisions") or [],
        }
        weeks.append(summary)
        if doc["status"] == "final" and doc.get("result") in ("W", "L", "T"):
            if doc["result"] == "W":
                wins += 1
            elif doc["result"] == "L":
                losses += 1
            else:
                ties += 1
            robot_points += Decimal(str(totals["robot"]))
            eddies_points += Decimal(str(totals["eddies"]))
    season = {
        "schemaVersion": SCHEMA_VERSION,
        "season": SEASON_YEAR,
        "club": "Eagleridge Eddie's",
        "sides": {"robot": "Robot", "eddies": "Eddies"},
        "firstWeek": FIRST_WEEK,
        "record": {
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "label": f"{wins}-{losses}-{ties}",
        },
        "points": {
            "robot": as_float(r1(robot_points)),
            "eddies": as_float(r1(eddies_points)),
            "margin": as_float(r1(robot_points - eddies_points)),
        },
        "weeks": weeks,
    }
    reject_keys(season, "season")
    dump(data_dir / "season.json", season)
    return season


def write_seed(data_dir, week=FIRST_WEEK):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / week_file(week)
    if not path.exists():
        dump(path, empty_week(week))
    return rebuild_season(data_dir)


def lock_lineup(data_dir, doc, now=None):
    if not isinstance(doc, dict):
        raise InputError("lock input must be an object")
    check_allowlist(doc, LOCK_KEYS, "lock input")
    reject_keys(doc, "lock input")
    week = require_week(doc.get("week"))
    require_season(doc.get("season"))
    if "firstKickoff" not in doc:
        raise InputError("firstKickoff is required")
    kickoff = parse_clock(doc["firstKickoff"])
    now_dt = parse_clock(now) if now else datetime.now(PT)
    lineup = validate_lineup(doc.get("lineup"), "robot lineup")
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / week_file(week)
    existing = load_json(path) if path.exists() else None

    if is_locked(existing):
        if lineup_identity(existing.get("robot")) != lineup_identity(lineup):
            raise Refusal("locked picks are immutable; refusing to edit the Robot lineup")
        stored = existing.get("firstKickoff")
        if not stored:
            raise Refusal("refusing to overwrite a lock after first kickoff")
        stored_kick = parse_clock(stored)
        if stored_kick.replace(microsecond=0) != kickoff.replace(microsecond=0):
            raise Refusal("locked picks are immutable; refusing to edit first kickoff")
        if now_dt >= stored_kick:
            raise Refusal("refusing to overwrite a lock after first kickoff")
        return path

    if now_dt >= kickoff:
        raise Refusal("refusing to lock at or after first kickoff")

    # Preserve an actual lineup already recorded on an unlocked shell.
    actual = existing.get("actual") if existing else []
    if actual:
        actual = validate_lineup(actual, "actual lineup")
    week_doc = empty_week(week)
    week_doc["robotLockedAt"] = iso_pt(now_dt)
    week_doc["firstKickoff"] = iso_pt(kickoff)
    week_doc["robot"] = lineup
    week_doc["actual"] = actual or []
    week_doc["status"] = "pending"
    reject_keys(week_doc, week_file(week))
    dump(path, week_doc)
    rebuild_season(data_dir)
    return path


def score_week(data_dir, doc):
    if not isinstance(doc, dict):
        raise InputError("score input must be an object")
    check_allowlist(doc, SCORE_KEYS, "score input")
    reject_keys(doc, "score input")
    week = require_week(doc.get("week"))
    require_season(doc.get("season"))
    status = doc.get("status")
    if status not in ("pending", "final"):
        raise InputError("status must be pending or final")
    data_dir = Path(data_dir)
    path = data_dir / week_file(week)
    existing = load_json(path) if path.exists() else None
    if not is_locked(existing):
        raise Refusal("Robot lineup is not locked for this week")
    actual = validate_lineup(doc.get("actual"), "actual lineup")
    scored = status == "final"
    if scored:
        table = point_table(
            existing["robot"],
            actual,
            doc.get("points") if doc.get("points") is not None else {},
            doc.get("bye") or [],
            doc.get("inactive") or [],
        )
    else:
        # Points stay null until the week is final, even if the input included numbers.
        table = {}
    robot = apply_points(existing["robot"], table, scored)
    actual_rows = apply_points(actual, table, scored)
    if scored:
        robot_total = sum_points(robot)
        eddies_total = sum_points(actual_rows)
        margin = r1(robot_total - eddies_total)
        result, winner = result_for(margin)
        robot_total_f = as_float(robot_total)
        eddies_total_f = as_float(eddies_total)
        margin_f = as_float(margin)
    else:
        robot_total_f = eddies_total_f = margin_f = None
        result = winner = None
    week_doc = {
        "schemaVersion": SCHEMA_VERSION,
        "season": SEASON_YEAR,
        "week": week,
        "window": existing.get("window") or week_window(week),
        "status": status,
        "robotLockedAt": existing.get("robotLockedAt"),
        "firstKickoff": existing.get("firstKickoff"),
        "robot": robot,
        "actual": actual_rows,
        "totals": {"robot": robot_total_f, "eddies": eddies_total_f},
        "margin": margin_f,
        "result": result,
        "winner": winner,
        "decisions": decisions_for(robot, actual_rows, scored),
    }
    reject_keys(week_doc, week_file(week))
    dump(path, week_doc)
    rebuild_season(data_dir)
    return path
