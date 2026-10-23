import json, sys, tempfile, unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import score_recs as sr


def rec(**kw):
    r = {"id": "x", "date": "2026-10-11", "week": 5, "type": "start_sit", "player": "Trenton Simpson",
         "call": "Start Simpson", "alternative": "Cedric Gray", "reason": "r", "decision": "past"}
    r.update(kw)
    return r


def sources(tmp):
    box = {"week": 5, "scrapedAt": "2026-10-13T09:40:00-07:00", "matchups": [{"players": [
        {"team": "Eagle Ridge Eddies", "player": "Trenton Simpson", "pts": 25.0},
        {"team": "Eagle Ridge Eddies", "player": "Cedric Gray", "pts": 14.0}]}]}
    (tmp / "fantrax-week5-box-details-2026-10-13.json").write_text(json.dumps(box))
    return sr.Sources(tmp)


NOW = datetime(2026, 10, 23, 7, 40)


class RecsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = sources(self.tmp)

    def test_week_formula(self):
        from datetime import date
        self.assertEqual(sr.week_of(date(2026, 10, 23)), 7)
        self.assertEqual(sr.week_of(date(2026, 10, 21)), 6)
        self.assertEqual(sr.week_of(date(2026, 10, 22)), 7)

    def test_scores_hit_verified_from_real_file(self):
        led = sr.score({"recs": [rec()]}, self.src, 7)
        r = led["recs"][0]
        self.assertEqual((r["status"], r["result"], r["verified"]), ("scored", "hit", "VERIFIED"))
        self.assertEqual((r["pts_player"], r["pts_alt"]), (25.0, 14.0))

    def test_missing_points_stay_unverified_and_unscored(self):
        led = sr.score({"recs": [rec(alternative="Nobody Here")]}, self.src, 7)
        r = led["recs"][0]
        self.assertEqual((r["status"], r["result"], r["verified"], r["pts_alt"]), ("open", None, "UNVERIFIED", None))

    def test_current_week_is_never_scored(self):
        led = sr.score({"recs": [rec(week=7, type="faab", decision="completed")]}, self.src, 7)
        self.assertEqual(led["recs"][0]["status"], "open")

    def test_pending_and_future_recs_are_excluded(self):
        bad = [rec(id="p1", decision="pending"), rec(id="p2", decision=None),
               rec(id="p3", call="Bid $9 on Ponder (claim pending)"),
               rec(id="p4", call="Open offer: Bourne for Golden", type="trade"),
               rec(id="p5", week=8)]
        for b in bad:
            with self.assertRaises(ValueError, msg=b["id"]):
                sr.summary(sr.score({"recs": [rec(), b]}, self.src, 7), 7, NOW)

    def test_cli_fails_closed_and_writes_nothing(self):
        led = self.tmp / "recs.json"; out = self.tmp / "summary.json"
        led.write_text(json.dumps({"recs": [rec(), rec(id="p", week=7, type="faab", decision="pending",
                                                        player="Austin Booker", call="Add Booker")]}))
        before = led.read_text()
        rc = sr.main(["--ledger", str(led), "--out", str(out), "--sources", str(self.tmp), "--today", "2026-10-23"])
        self.assertEqual(rc, 1)
        self.assertFalse(out.exists())
        self.assertEqual(led.read_text(), before)

    def test_published_summary_has_no_pending_or_future(self):
        s = json.loads((ROOT / "data" / "recs-summary.json").read_text())
        led = json.loads((ROOT / "data" / "recs.json").read_text())
        wk = s["week"]
        for r in led["recs"]:
            self.assertIn(r["decision"], sr.DONE)
            self.assertLessEqual(r["week"], wk)
            self.assertIsNone(sr.PENDING_RE.search(json.dumps(r)), r["id"])
        for r in s["recs"]:
            if r["week"] >= wk:
                self.assertEqual(r["status"], "open")
        self.assertNotIn("Austin Booker", json.dumps(s))

    def test_repo_ledger_shape_and_honesty(self):
        led = json.loads((ROOT / "data" / "recs.json").read_text())
        for r in led["recs"]:
            self.assertIn(r["type"], sr.TYPES)
            if r["verified"] == "VERIFIED":
                self.assertEqual(r["status"], "scored")
                self.assertTrue(r["source"] and "fantrax" in r["source"])
                self.assertIsNotNone(r["pts_player"]); self.assertIsNotNone(r["pts_alt"])
            if r["status"] == "scored":
                self.assertIn(r["result"], ("hit", "miss", "push"))
        self.assertFalse(any("Edgerrin Cooper" in json.dumps(r) for r in led["recs"]))

    def test_summary_rates(self):
        recs = [rec(id="a"), rec(id="b", player="Cedric Gray", alternative="Trenton Simpson")]
        s = sr.summary(sr.score({"recs": recs, "learning": [{"week": 5, "note": "n", "adjustment": "a"},
                                                             {"week": 7, "note": "future", "adjustment": "x"}]}, self.src, 7), 7, NOW)
        self.assertEqual(s["overall"]["hitRate"], 0.5)
        self.assertEqual(s["best"][0]["id"], "a"); self.assertEqual(s["worst"][0]["id"], "b")
        self.assertEqual(s["latestLearning"]["week"], 5)


if __name__ == "__main__":
    unittest.main()
