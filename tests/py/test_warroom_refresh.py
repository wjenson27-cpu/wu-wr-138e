import json, os, shutil, sys, tempfile, unittest
from datetime import date, datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import warroom_common as wc, build_free_agents as bfa, build_warroom as bw, refresh_green_dots as rgd
FIX = ROOT / "tests" / "fixtures"
DATA = Path(os.environ.get("WU_DATA_DIR") or ROOT / "data")
PT = wc.PT

def stage():
    d = Path(tempfile.mkdtemp()) / "data"; shutil.copytree(DATA, d); return d

class Week(unittest.TestCase):
    def test_week_calc(self):
        self.assertEqual(wc.week_for(date(2026, 9, 10)), 1)
        self.assertEqual(wc.week_for(date(2026, 9, 16)), 1)
        self.assertEqual(wc.week_for(date(2026, 9, 17)), 2)
        self.assertEqual(wc.week_for(date(2026, 10, 21)), 6)
        self.assertEqual(wc.week_for(date(2026, 10, 22)), 7)
        self.assertEqual(wc.week_for(date(2026, 10, 28)), 7)
        self.assertEqual(wc.week_for(date(2026, 10, 29)), 8)
    def test_week_uses_pt_not_utc(self):
        # Thu Oct 22 03:00 UTC is still Wed Oct 21 in PT -> week 6
        self.assertEqual(wc.week_for(datetime.fromisoformat("2026-10-22T03:00:00+00:00")), 6)

class Excludes(unittest.TestCase):
    def test_cooper_on_season_ending_list_booker_not(self):
        se = wc.season_ending(DATA)
        self.assertIn(wc.norm("Edgerrin Cooper"), se)
        self.assertNotIn(wc.norm("Austin Booker"), se)
    def test_cooper_never_in_fa_pool(self):
        scrape = {"freeAgents": [
            {"player": "Edgerrin Cooper", "pos": "LB", "team": "GB", "fpg": 28.75, "rosteredPct": 67},
            {"player": "Austin Booker", "pos": "DL", "team": "CHI", "fpg": 9.0, "rosteredPct": 20},
            {"player": "Some IR Guy", "pos": "LB", "team": "X", "fpg": 9.0, "injury": "IR"}]}
        d = bfa.build(scrape, DATA, "2026-10-22T21:00:00-07:00")
        names = [p["player"] for p in d["players"]]
        self.assertNotIn("Edgerrin Cooper", names)
        self.assertNotIn("Some IR Guy", names)
        self.assertIn("Austin Booker", names)  # do-not-pitch stays in the FA pool
    def test_cooper_and_booker_never_in_waiver_recs(self):
        w = {"week": 7, "waivers": [{"rank": 1, "player": "Edgerrin Cooper"}, {"rank": 2, "player": "Austin Booker"},
                                    {"rank": 3, "player": "Martin Emerson"}]}
        now = datetime(2026, 10, 23, 9, 0, tzinfo=PT)
        d = bw.build(w, DATA, now)
        self.assertEqual([(r["rank"], r["player"]) for r in d["waivers"]], [(1, "Martin Emerson")])
    def test_booker_pass_is_week_scoped(self):
        self.assertIn(wc.norm("Austin Booker"), wc.do_not_pitch(DATA, 7, date(2026, 10, 23)))
        self.assertNotIn(wc.norm("Austin Booker"), wc.do_not_pitch(DATA, 8, date(2026, 10, 30)))
    def test_committed_data_has_no_cooper_as_option(self):
        for f in ("warroom.json", "free-agents.json", "green-dots.json"):
            d = json.loads((DATA / f).read_text())
            opts = d.get("waivers", []) + d.get("players", []) if isinstance(d, dict) else []
            self.assertFalse(any("Edgerrin Cooper" == (p.get("player") or p.get("name")) for p in opts), f)

class Stamps(unittest.TestCase):
    def test_warroom_stamps_pt_and_week(self):
        now = datetime(2026, 10, 24, 10, 23, tzinfo=PT)
        d = bw.build({"week": 7, "waivers": []}, DATA, now)
        self.assertEqual(d["week"], 7)
        self.assertEqual(d["lastUpdated"], "2026-10-24T10:23:00-07:00")
        self.assertEqual(d["asOf"], d["lastUpdated"])
        self.assertNotIn("refreshNotes", d)
    def test_week_rollover_flags_old_editorial(self):
        d = bw.build({"week": 7, "waivers": []}, DATA, datetime(2026, 10, 29, 8, 0, tzinfo=PT))
        self.assertEqual(d["week"], 8); self.assertTrue(d["refreshNotes"])

class NoPending(unittest.TestCase):
    def test_pending_stripped(self):
        w = {"week": 7, "waivers": [{"rank": 1, "player": "Martin Emerson", "bid": 0}],
             "pendingClaims": [{"player": "X", "bid": 5}], "trades": [{"with": "A", "status": "pending"}, {"with": "B", "why": "idea"}],
             "eddies": {"pendingTrades": [1], "bids": [3], "claims": [2]}}
        d = bw.build(w, DATA, datetime(2026, 10, 23, 9, 0, tzinfo=PT),
                     raw={"rosters": {}, "trades": {"pending": [{"x": 1}]}, "scraped": "s"}, raw_name="r.json")
        self.assertFalse(wc.has_pending(d))
        self.assertNotIn("pendingClaims", d)
        self.assertEqual(d["trades"], [{"with": "B", "why": "idea"}])
        self.assertEqual(d["waivers"][0]["bid"], 0)  # recommendation field is kept
        self.assertEqual(set(d["fantraxRaw"]), {"file", "scraped"})  # nothing else copied from raw
    def test_committed_warroom_has_no_pending(self):
        self.assertFalse(wc.has_pending(json.loads((DATA / "warroom.json").read_text())))

class GreenDots(unittest.TestCase):
    def setUp(self): self.d = stage()
    def now(self): return datetime(2026, 10, 24, 10, 23, tzinfo=PT)
    def test_stale_when_no_newer_post(self):
        before = (self.d / "green-dots.json").read_text()
        gd, st = rgd.run(self.d, self.now(), json.loads((FIX / "archive-no-w7.json").read_text()))
        self.assertTrue(st["stale"]); self.assertFalse(st["rebuilt"])
        self.assertEqual((self.d / "green-dots.json").read_text(), before)
    def test_paid_post_not_parsed(self):
        called = []
        gd, st = rgd.run(self.d, self.now(), json.loads((FIX / "archive-w7-paid.json").read_text()),
                         lambda s: called.append(s) or {})
        self.assertEqual(called, []); self.assertTrue(st["stale"]); self.assertIn("paid", st["reason"])
    def test_rebuild_from_free_post(self):
        post = json.loads((FIX / "green-dot-post-synthetic.json").read_text())
        gd, st = rgd.run(self.d, self.now(), json.loads((FIX / "archive-w7-free.json").read_text()), lambda s: post)
        self.assertTrue(st["rebuilt"]); self.assertFalse(st["stale"])
        self.assertEqual(gd["week"], 7); self.assertEqual(gd["sourceUrl"], "https://x/gd7")
        self.assertEqual(gd["asOf"], "2026-10-27T05:20:00-07:00")
        t = {x["team"]: x for x in gd["teams"]}
        self.assertIsNone(t["DAL"]["greenDot"])          # shared -> null
        self.assertIn("Bye", t["DET"]["notes"])           # bye -> carried
        self.assertEqual(t["GB"]["greenDot"], "Quay Walker")
        self.assertNotIn("Edgerrin Cooper", json.dumps([x["greenDot"] for x in gd["teams"]] + [x["fullTime"] for x in gd["teams"]]))
    def test_fetch_failure_is_stale_not_crash(self):
        orig = rgd.get; rgd.get = lambda u: (_ for _ in ()).throw(OSError("offline"))
        try:
            gd, st = rgd.run(self.d, self.now())
        finally:
            rgd.get = orig
        self.assertTrue(st["stale"]); self.assertIn("fetch failed", st["reason"])

if __name__ == "__main__":
    unittest.main()
