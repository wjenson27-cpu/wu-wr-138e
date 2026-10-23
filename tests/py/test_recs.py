import json, sys, tempfile, unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import score_recs as sr

TODAY = "2026-10-23"   # Week 7
NOW = datetime(2026, 10, 23, 7, 40)


def rec(**kw):
    r = {"id": "x", "date": "2026-10-11", "week": 5, "type": "start_sit", "player": "Trenton Simpson",
         "call": "Start Simpson", "alternative": "Cedric Gray", "reason": "r", "decision": "past"}
    r.update(kw)
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        box = {"week": 5, "scrapedAt": "2026-10-13T09:40:00-07:00", "matchups": [{"players": [
            {"team": "Eagle Ridge Eddies", "player": "Trenton Simpson", "pts": 25.0},
            {"team": "Eagle Ridge Eddies", "player": "Cedric Gray", "pts": 14.0}]}]}
        (self.tmp / "fantrax-week5-box-details-2026-10-13.json").write_text(json.dumps(box))
        (self.tmp / "fantrax-scrape-2026-10-12-pm.json").write_text(json.dumps({"scrapedAt": "2026-10-12T15:00:00-07:00",
            "roster": [{"player": "Jacory Croskey-Merritt", "note": "3 pts if started"}]}))
        for n, s in (("a", "2026-10-09T15:00:00-07:00"), ("b", "2026-10-12T15:00:00-07:00")):
            (self.tmp / f"fantrax-scrape-d{n}.json").write_text(json.dumps({"scrapedAt": s,
                "freeAgents": [{"player": "Elijah Ponder", "fpts": 100.0 if n == "a" else 113.0}]}))
        self.src = sr.Sources(self.tmp)
        self.raw()

    def raw(self, **kw):
        d = {"scraped": "2026-10-23T06:30:00-07:00", "rosters": [{"team": "x", "players": []}]}
        d.update(kw)
        (self.tmp / "fantrax-raw-2026-10-23-am.json").write_text(json.dumps(d))

    def run_cli(self, recs, learning=None, names=None):
        led = self.tmp / "recs.json"; out = self.tmp / "summary.json"
        if out.exists():
            out.unlink()
        led.write_text(json.dumps({"recs": recs, "learning": learning or []}))
        before = led.read_text()
        nf = self.tmp / "names.json"
        if names is not None:
            nf.write_text(json.dumps(names))
        rc = sr.main(["--ledger", str(led), "--out", str(out), "--sources", str(self.tmp), "--today", TODAY,
                      "--raw-glob", str(self.tmp / "fantrax-raw-*.json"), "--pending-names", str(nf)])
        return rc, led, out, before


class PrivacyTest(Base):
    def assert_blocked(self, recs, learning=None, names=None):
        rc, led, out, before = self.run_cli(recs, learning, names)
        self.assertEqual(rc, 1)
        self.assertFalse(out.exists())
        self.assertEqual(led.read_text(), before)

    def test_clean_run_publishes(self):
        rc, led, out, _ = self.run_cli([rec()])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.read_text())["overall"]["hits"], 1)

    def test_own_pending_with_no_names_fails_closed(self):
        # today's real state: 1 of our pending moves, 0 names
        self.raw(eddiesPendingClaims=1)
        self.assert_blocked([rec()])
        self.raw(pendingClaimsCount=1)
        self.assert_blocked([rec()])

    def test_martin_emerson_learning_note_is_blocked(self):
        self.assert_blocked([rec()], [{"week": 6, "note": "Our pending claim on Martin Emerson processes Wed", "adjustment": "a"}])
        self.assert_blocked([rec()], [{"week": 6, "note": "n", "adjustment": "Bid $12 placed, processes Wed"}])
        self.assert_blocked([rec()], [{"week": 6, "note": "Our p\u0435nding Martin Emerson move", "adjustment": "a"}])

    def test_pending_name_drops_rec_and_note(self):
        self.raw(eddies_pending_names=["Martin Emerson"])
        rc, led, out, _ = self.run_cli(
            [rec(), rec(id="em", alternative="Martin Emerson"), rec(id="em2", reason="Lead-in to our Martin Emerson move")],
            [{"week": 5, "note": "Fine note", "adjustment": "a"}, {"week": 6, "note": "Emerson looked good", "adjustment": "b"}],
            names={"scraped": "2026-10-23T06:30:00-07:00", "names": ["Martin Emerson"], "own_names": ["Martin Emerson"]})
        self.assertEqual(rc, 0)
        text = out.read_text() + led.read_text()
        self.assertNotIn("Emerson", text)
        self.assertEqual(json.loads(out.read_text())["latestLearning"]["week"], 5)

    def test_pending_wording_variants_are_blocked(self):
        for kw in ({"call": "pend\u200bing claim"}, {"call": "p\u0435nding"}, {"call": "Bid $12 placed, processes Wed"},
                   {"call": "Claim in, runs Wednesday"}, {"call": "Offer out to Nathan, no reply yet", "type": "trade"},
                   {"call": "Offered Lloyd for Emerson", "type": "trade"}, {"alternative": "Pending: Emerson"},
                   {"note": "pending claim Wed"}, {"pendingClaim": True}, {"decision": "pending"}, {"decision": None},
                   {"status": "pending"}):
            with self.subTest(kw=kw):
                self.assert_blocked([rec(), rec(id="bad", **kw)])

    def test_week_and_date_checks(self):
        for kw in ({"week": 7, "date": "2026-10-22", "type": "faab", "decision": "completed"},   # current week
                   {"week": 8, "date": "2026-10-23"}, {"week": True}, {"week": "6"}, {"week": 6.0},
                   {"week": 6, "date": "2026-10-28"},   # future date
                   {"week": 6, "date": "2026-09-20"},   # date not in week 6 or week 5
                   {"date": "not a date"}):
            with self.subTest(kw=kw):
                self.assert_blocked([rec(**kw)])

    def test_current_week_rejected_before_scoring(self):
        with self.assertRaises(ValueError):
            sr.check_ledger({"recs": [rec(week=7, date="2026-10-22", decision="completed", type="faab")]}, 7, date(2026, 10, 23))

    @unittest.skipUnless(Path("/workspace/fantrax-raw-2026-10-23-am.json").exists(), "real scrape not on this box")
    def test_real_state_today_exits_1_and_writes_nothing(self):
        out = self.tmp / "real-summary.json"; led = self.tmp / "real-recs.json"
        led.write_text((ROOT / "data" / "recs.json").read_text()); before = led.read_text()
        rc = sr.main(["--ledger", str(led), "--out", str(out), "--today", TODAY,
                      "--raw-glob", "/workspace/fantrax-raw-2026-10-23-am.json",
                      "--pending-names", "/workspace/eddie-private/pending-names.json"])   # path only, as build_warroom uses it
        self.assertEqual(rc, 1); self.assertFalse(out.exists()); self.assertEqual(led.read_text(), before)

    def test_no_raw_scrape_fails_closed(self):
        (self.tmp / "fantrax-raw-2026-10-23-am.json").unlink()
        self.assert_blocked([rec()])

    def test_repo_ledger_passes_text_and_week_checks(self):
        led = json.loads((ROOT / "data" / "recs.json").read_text())
        sr.check_ledger(led, 7, date(2026, 10, 23))
        self.assertFalse(any(r["week"] >= 7 for r in led["recs"]))
        self.assertNotIn("Edgerrin Cooper", json.dumps(led))
        self.assertNotIn("Austin Booker", json.dumps(led))


class BasisTest(Base):
    def test_box_score_is_verified(self):
        r = sr.score({"recs": [rec()]}, self.src, 7)["recs"][0]
        self.assertEqual((r["result"], r["basis"], r["verified"]), ("hit", "box_score", "VERIFIED"))

    def test_fantrax_note_is_verified_bench(self):
        r = sr.score({"recs": [rec(alternative="Jacory Croskey-Merritt")]}, self.src, 7)["recs"][0]
        self.assertEqual((r["basis_alt"], r["verified"]), ("fantrax_note", "VERIFIED"))

    def test_inferred_alt_is_unverified_and_out_of_headline(self):
        led = sr.score({"recs": [rec(), rec(id="i", player="Cedric Gray", alternative="Trenton Simpson", alt_inferred=True)]}, self.src, 7)
        r = led["recs"][1]
        self.assertEqual((r["basis"], r["verified"], r["status"]), ("inferred", "UNVERIFIED", "scored"))
        s = sr.summary(led, 7, NOW)
        self.assertEqual((s["overall"]["hits"], s["overall"]["misses"]), (1, 0))
        self.assertEqual((s["overallAll"]["hits"], s["overallAll"]["misses"]), (1, 1))

    def test_derived_delta_is_unverified(self):
        r = sr.score({"recs": [rec(player="Elijah Ponder", delta={"Elijah Ponder": ["fantrax-scrape-da.json", "fantrax-scrape-db.json"]})]},
                     self.src, 7)["recs"][0]
        self.assertEqual((r["pts_player"], r["basis"], r["verified"], r["result"]), (13.0, "derived", "UNVERIFIED", "miss"))

    def test_missing_points_stay_open(self):
        r = sr.score({"recs": [rec(alternative="Nobody Here")]}, self.src, 7)["recs"][0]
        self.assertEqual((r["status"], r["result"], r["verified"]), ("open", None, "UNVERIFIED"))

    def test_week_formula(self):
        self.assertEqual(sr.week_of(date(2026, 10, 23)), 7)
        self.assertEqual(sr.week_of(date(2026, 10, 21)), 6)


if __name__ == "__main__":
    unittest.main()
