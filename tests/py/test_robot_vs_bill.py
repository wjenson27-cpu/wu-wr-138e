"""Robot vs. The Eddies: lock immutability, scoring, season tally, privacy."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import robot_vs_bill as rvb  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "robot-vs-bill"
PY = sys.executable
LOCK = ROOT / "scripts" / "lock_robot_lineup.py"
SCORE = ROOT / "scripts" / "score_robot_vs_bill.py"
NAME = "B" + "ill"
LAST = "J" + "enson"
PUBLIC = [
    "robot-vs-bill.html",
    "js/robot-scoreboard.js",
    "docs/robot-vs-bill.md",
    "data/robot-vs-bill/schema.json",
    "data/robot-vs-bill/season.json",
    "data/robot-vs-bill/w09.json",
    "scripts/robot_vs_bill.py",
    "scripts/lock_robot_lineup.py",
    "scripts/score_robot_vs_bill.py",
]
BANNED_KEY = re.compile(
    r"faab|waiver|pendingclaim|pendingtrade|^bids?$|^claims?$|^trades?$|^owners?$",
    re.I,
)


def load(name):
    return json.loads((FIX / name).read_text())


def run(script, data, payload, now=None):
    folder = Path(data)
    src = folder / "input.json"
    src.write_text(json.dumps(payload))
    cmd = [PY, str(script), "--input", str(src), "--data", str(folder)]
    if now:
        cmd.extend(["--now", now])
    return subprocess.run(cmd, capture_output=True, text=True)


def week(data, n):
    return json.loads((Path(data) / f"w{n:02d}.json").read_text())


def season(data):
    return json.loads((Path(data) / "season.json").read_text())


def scrub(text):
    return text.replace("robot-vs-bill", "FEATURE").replace("score_robot_vs_bill", "SCORE")


class Lock(unittest.TestCase):
    def test_lock_before_kickoff_writes_a_pt_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = run(LOCK, tmp, load("lock-w09.json"), "2026-11-05T09:30:00-08:00")
            self.assertEqual(first.returncode, 0, first.stderr)
            doc = week(tmp, 9)
            self.assertEqual(doc["robotLockedAt"], "2026-11-05T09:30:00-08:00")
            self.assertEqual(doc["firstKickoff"], "2026-11-05T17:15:00-08:00")
            self.assertTrue(doc["robotLockedAt"].endswith("-08:00"))
            self.assertEqual(doc["status"], "pending")
            self.assertEqual(len(doc["robot"]), 14)
            self.assertIsNone(doc["robot"][0]["points"])
            self.assertEqual(doc["window"]["start"], "2026-11-05")
            self.assertEqual(doc["window"]["end"], "2026-11-09")
            self.assertEqual(season(tmp)["record"]["label"], "0-0-0")

    def test_edits_are_refused_and_the_file_stays_put(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = load("lock-w09.json")
            self.assertEqual(run(LOCK, tmp, payload, "2026-11-05T09:30:00-08:00").returncode, 0)
            original = (Path(tmp) / "w09.json").read_text()
            edited = json.loads(json.dumps(payload))
            edited["lineup"][0]["player"] = "Someone Else"
            before = run(LOCK, tmp, edited, "2026-11-05T12:00:00-08:00")
            self.assertEqual(before.returncode, 2, before.stderr)
            self.assertIn("immutable", before.stderr)
            self.assertEqual((Path(tmp) / "w09.json").read_text(), original)
            moved = json.loads(json.dumps(payload))
            moved["firstKickoff"] = "2026-11-06T17:15:00-08:00"
            shift = run(LOCK, tmp, moved, "2026-11-05T12:00:00-08:00")
            self.assertEqual(shift.returncode, 2, shift.stderr)
            self.assertEqual((Path(tmp) / "w09.json").read_text(), original)

    def test_identical_relock_before_kickoff_keeps_the_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = load("lock-w09.json")
            self.assertEqual(run(LOCK, tmp, payload, "2026-11-05T09:30:00-08:00").returncode, 0)
            original = (Path(tmp) / "w09.json").read_text()
            again = run(LOCK, tmp, payload, "2026-11-05T11:00:00-08:00")
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual((Path(tmp) / "w09.json").read_text(), original)
            self.assertEqual(week(tmp, 9)["robotLockedAt"], "2026-11-05T09:30:00-08:00")

    def test_overwrite_after_kickoff_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = load("lock-w09.json")
            self.assertEqual(run(LOCK, tmp, payload, "2026-11-05T09:30:00-08:00").returncode, 0)
            original = (Path(tmp) / "w09.json").read_text()
            at_kick = run(LOCK, tmp, payload, "2026-11-05T17:15:00-08:00")
            self.assertEqual(at_kick.returncode, 2, at_kick.stderr)
            self.assertIn("after first kickoff", at_kick.stderr)
            later = run(LOCK, tmp, payload, "2026-11-08T12:00:00-08:00")
            self.assertEqual(later.returncode, 2, later.stderr)
            self.assertEqual((Path(tmp) / "w09.json").read_text(), original)

    def test_first_lock_after_kickoff_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            late = run(LOCK, tmp, load("lock-w09.json"), "2026-11-05T17:15:00-08:00")
            self.assertEqual(late.returncode, 2, late.stderr)
            self.assertFalse((Path(tmp) / "w09.json").exists())
            early = load("lock-w09.json")
            early["week"] = 8
            refused = run(LOCK, tmp, early, "2026-10-29T09:00:00-07:00")
            self.assertEqual(refused.returncode, 1, refused.stderr)
            self.assertFalse((Path(tmp) / "w08.json").exists())

    def test_seed_week_can_still_be_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            rvb.dump(Path(tmp) / "w09.json", rvb.empty_week(9))
            rvb.rebuild_season(tmp)
            result = run(LOCK, tmp, load("lock-w09.json"), "2026-11-05T09:30:00-08:00")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(week(tmp, 9)["robot"]), 14)


class Score(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.assertEqual(run(LOCK, self.data, load("lock-w09.json"), "2026-11-05T09:30:00-08:00").returncode, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_shared_player_bye_and_totals(self):
        scored = run(SCORE, self.data, load("score-w09.json"))
        self.assertEqual(scored.returncode, 0, scored.stderr)
        doc = week(self.data, 9)
        robot = {row["player"]: row["points"] for row in doc["robot"]}
        actual = {row["player"]: row["points"] for row in doc["actual"]}
        self.assertEqual(robot["Joe Burrow"], 22.0)
        self.assertEqual(actual["Joe Burrow"], 22.0)
        self.assertEqual(robot["Drake London"], 8.0)
        self.assertNotIn("Drake London", actual)
        self.assertEqual(actual["Sauce Gardner"], 0.0)
        self.assertEqual(actual["Adam Thielen"], 2.0)
        self.assertEqual(doc["totals"], {"robot": 150.0, "eddies": 139.0})
        self.assertEqual(doc["margin"], 11.0)
        self.assertEqual(doc["result"], "W")
        self.assertEqual(doc["winner"], "Robot")
        swings = {row["slot"] + str(row["index"]): row["swing"] for row in doc["decisions"]}
        self.assertEqual(swings, {"FLEX6": 6.0, "DB10": 5.0})
        self.assertEqual(sum(row["swing"] for row in doc["decisions"]), doc["margin"])
        self.assertEqual([row["player"] for row in doc["robot"]], [row["player"] for row in load("lock-w09.json")["lineup"]])

    def test_pending_keeps_points_null(self):
        payload = load("score-w09.json")
        payload["status"] = "pending"
        self.assertEqual(run(SCORE, self.data, payload).returncode, 0)
        doc = week(self.data, 9)
        self.assertEqual(doc["status"], "pending")
        self.assertTrue(all(row["points"] is None for row in doc["robot"] + doc["actual"]))
        self.assertIsNone(doc["totals"]["robot"])
        self.assertIsNone(doc["result"])
        self.assertEqual(len(doc["decisions"]), 2)
        self.assertTrue(all(row["swing"] is None for row in doc["decisions"]))
        self.assertEqual(season(self.data)["record"]["label"], "0-0-0")
        self.assertEqual(season(self.data)["points"]["robot"], 0.0)

    def test_score_before_lock_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            refused = run(SCORE, tmp, load("score-w09.json"))
            self.assertEqual(refused.returncode, 2, refused.stderr)
            self.assertFalse((Path(tmp) / "w09.json").exists())

    def test_inactive_shared_player_is_zero_on_both_sides(self):
        self.assertEqual(run(LOCK, self.data, load("lock-w10.json"), "2026-11-12T09:30:00-08:00").returncode, 0)
        self.assertEqual(run(SCORE, self.data, load("score-w10.json")).returncode, 0)
        doc = week(self.data, 10)
        for side in ("robot", "actual"):
            bosa = next(row for row in doc[side] if row["player"] == "Nick Bosa")
            self.assertEqual(bosa["points"], 0.0)
        self.assertEqual(doc["totals"], {"robot": 130.0, "eddies": 144.0})
        self.assertEqual(doc["margin"], -14.0)
        self.assertEqual(doc["result"], "L")
        self.assertEqual(doc["winner"], "Eddies")
        self.assertEqual(sorted(row["swing"] for row in doc["decisions"]), [-8.0, -6.0])

    def test_identical_lineup_ties_with_no_decisions(self):
        payload = load("score-w09.json")
        payload["actual"] = load("lock-w09.json")["lineup"]
        payload["bye"] = []
        payload["inactive"] = []
        self.assertEqual(run(SCORE, self.data, payload).returncode, 0)
        doc = week(self.data, 9)
        self.assertEqual(doc["result"], "T")
        self.assertEqual(doc["winner"], "tie")
        self.assertEqual(doc["margin"], 0.0)
        self.assertEqual(doc["decisions"], [])
        self.assertEqual(doc["totals"]["robot"], doc["totals"]["eddies"])


class Tally(unittest.TestCase):
    def test_two_weeks_aggregate_and_rescore_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run(LOCK, tmp, load("lock-w09.json"), "2026-11-05T09:30:00-08:00").returncode, 0)
            self.assertEqual(run(SCORE, tmp, load("score-w09.json")).returncode, 0)
            self.assertEqual(run(LOCK, tmp, load("lock-w10.json"), "2026-11-12T09:30:00-08:00").returncode, 0)
            self.assertEqual(run(SCORE, tmp, load("score-w10.json")).returncode, 0)
            tally = season(tmp)
            self.assertEqual(tally["record"], {"wins": 1, "losses": 1, "ties": 0, "label": "1-1-0"})
            self.assertEqual(tally["points"], {"robot": 280.0, "eddies": 283.0, "margin": -3.0})
            self.assertEqual([row["week"] for row in tally["weeks"]], [9, 10])
            self.assertEqual(tally["weeks"][0]["result"], "W")
            self.assertEqual(tally["weeks"][1]["result"], "L")
            self.assertEqual(tally["firstWeek"], 9)
            again = load("score-w09.json")
            again["points"] = dict(again["points"])
            again["points"]["Adam Thielen"] = 13
            self.assertEqual(run(SCORE, tmp, again).returncode, 0)
            replaced = season(tmp)
            self.assertEqual(week(tmp, 9)["totals"]["eddies"], 150.0)
            self.assertEqual(week(tmp, 9)["result"], "T")
            self.assertEqual(replaced["record"]["label"], "0-1-1")
            self.assertEqual(replaced["points"]["robot"], 280.0)
            self.assertEqual(replaced["points"]["eddies"], 294.0)
            self.assertNotEqual(replaced["points"]["robot"], 430.0)

    def test_personal_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = load("lock-w09.json")
            payload["own" + "er"] = "nope"
            refused = run(LOCK, tmp, payload, "2026-11-05T09:30:00-08:00")
            self.assertEqual(refused.returncode, 1, refused.stderr)
            self.assertFalse((Path(tmp) / "w09.json").exists())


class Privacy(unittest.TestCase):
    def test_public_files_do_not_name_a_person_or_carry_league_money(self):
        for rel in PUBLIC:
            text = (ROOT / rel).read_text()
            cleaned = scrub(text)
            self.assertIsNone(
                re.search(r"\b" + NAME + r"\b", cleaned, re.I),
                rel,
            )
            self.assertNotIn(LAST.lower(), cleaned.lower(), rel)
            if rel.endswith(".json"):
                keys = []

                def walk(obj):
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            keys.append(str(key))
                            walk(value)
                    elif isinstance(obj, list):
                        for value in obj:
                            walk(value)

                walk(json.loads(text))
                for key in keys:
                    self.assertIsNone(BANNED_KEY.search(key), rel + " key " + key)
        page = (ROOT / "robot-vs-bill.html").read_text()
        script = (ROOT / "js" / "robot-scoreboard.js").read_text()
        for blob in (page, script):
            low = blob.lower()
            self.assertNotIn("faab", low)
            self.assertNotIn("pending claim", low)
            self.assertNotIn("pending trade", low)
            self.assertNotIn("proposed trade", low)
            self.assertNotIn("<table", low)
        self.assertIn("Robot vs. The Eddies", page)
        self.assertIn(">Robot<", script)
        self.assertIn(">Eddies<", script)
        home = (ROOT / "index.html").read_text()
        self.assertNotIn("robot-vs-bill.html", home)
        live = json.loads((ROOT / "data" / "robot-vs-bill" / "w09.json").read_text())
        self.assertEqual(live["week"], 9)
        self.assertEqual(live["status"], "pending")
        self.assertIsNotNone(live["robotLockedAt"])
        self.assertEqual(len(live["robot"]), 14)
        self.assertEqual(live["actual"], [])
        self.assertTrue(all(row["points"] is None for row in live["robot"]))
        self.assertIsNone(live["totals"]["robot"])
        self.assertIsNone(live["result"])
        tally = json.loads((ROOT / "data" / "robot-vs-bill" / "season.json").read_text())
        self.assertEqual(tally["record"]["label"], "0-0-0")
        self.assertEqual(tally["firstWeek"], 9)
        self.assertEqual(tally["sides"], {"robot": "Robot", "eddies": "Eddies"})
        self.assertNotIn("sample", live)
        self.assertNotIn("sample", tally)


if __name__ == "__main__":
    unittest.main()
