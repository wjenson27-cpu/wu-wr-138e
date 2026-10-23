import json, os, shutil, subprocess, sys, tempfile, unittest
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
        self.assertTrue(se.match("Edgerrin Cooper"))
        self.assertFalse(se.match("Austin Booker"))
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
        d = bw.build(w, DATA, datetime(2026, 10, 23, 9, 0, tzinfo=PT))
        self.assertEqual([(r["rank"], r["player"]) for r in d["waivers"]], [(1, "Martin Emerson")])
    def test_booker_pass_is_week_scoped(self):
        self.assertTrue(wc.do_not_pitch(DATA, 7, date(2026, 10, 23)).match("Austin Booker"))
        self.assertFalse(wc.do_not_pitch(DATA, 8, date(2026, 10, 30)).match("Austin Booker"))
    def test_committed_data_has_no_cooper_as_option(self):
        se = wc.season_ending(DATA)
        for f in ("warroom.json", "free-agents.json"):
            d = json.loads((DATA / f).read_text())
            for p in d.get("waivers", []) + d.get("players", []):
                self.assertFalse(se.match(p), (f, p))

class BotOpsBlocker1FailClosed(unittest.TestCase):
    """Bot Ops round 1, blocker 1: missing/invalid lists must fail, not fall back to empty."""
    def setUp(self): self.d = stage()
    def _w(self): return {"week": 7, "waivers": [{"rank": 1, "player": "Edgerrin Cooper"}]}
    def test_missing_season_ending_fails(self):
        (self.d / "season-ending.json").unlink()
        with self.assertRaises(wc.ListError): bw.build(self._w(), self.d, datetime(2026, 10, 23, tzinfo=PT))
        with self.assertRaises(wc.ListError): bfa.build({"freeAgents": []}, self.d, "x")
    def test_missing_do_not_pitch_fails(self):
        (self.d / "do-not-pitch.json").unlink()
        with self.assertRaises(wc.ListError): bw.build(self._w(), self.d, datetime(2026, 10, 23, tzinfo=PT))
    def test_invalid_lists_fail(self):
        for bad in ("{not json", '{"players": null}', '{"players": [{"pos": "LB"}]}', '{"players": [{"name": "  "}]}', "[]"):
            (self.d / "season-ending.json").write_text(bad)
            with self.assertRaises(wc.ListError, msg=bad): wc.season_ending(self.d)
    def test_cli_exits_nonzero_and_writes_nothing(self):
        (self.d / "season-ending.json").unlink()
        before = (self.d / "warroom.json").read_bytes()
        r = subprocess.run([sys.executable, str(ROOT / "scripts/build_warroom.py"), "--data-dir", str(self.d), "--no-fantrax"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertEqual((self.d / "warroom.json").read_bytes(), before)

class BotOpsBlocker2Variants(unittest.TestCase):
    """Blocker 2: name variants, id-only and null-name recs."""
    def build(self, recs):
        return bw.build({"week": 7, "waivers": recs}, DATA, datetime(2026, 10, 23, 9, 0, tzinfo=PT))["waivers"]
    def test_variants_blocked(self):
        recs = [{"player": n} for n in ("E. Cooper", "Cooper, Edgerrin", "edgerrin cooper", "Edgerrin Cooper ",
                                        "EDGERRIN COOPER", "Edgerrin\u00a0Cooper", "Édgerrin Cooper Jr.",
                                        "Booker, Austin", "A. Booker", "austin booker")]
        self.assertEqual(self.build(recs), [])
    def test_id_only_and_null_name_blocked(self):
        out = self.build([{"playerId": "abc123"}, {"player": None}, {"player": ""}, {"id": "x", "player": None}])
        self.assertEqual(out, [])
    def test_id_match_from_list(self):
        d = stage(); se = json.loads((d / "season-ending.json").read_text())
        se["players"].append({"id": "FX-99", "pos": "LB", "team": "ZZ", "reason": "test"})
        (d / "season-ending.json").write_text(json.dumps(se))
        out = bw.build({"week": 7, "waivers": [{"player": "Totally Different", "playerId": "fx-99"}]}, d,
                       datetime(2026, 10, 23, tzinfo=PT))["waivers"]
        self.assertEqual(out, [])
    def test_other_cooper_not_blocked(self):
        self.assertEqual([r["player"] for r in self.build([{"player": "Darius Cooper"}])], ["Darius Cooper"])
    def test_fa_pool_variants(self):
        rows = [{"player": n, "pos": "LB", "team": "GB", "fpg": 1} for n in ("E. Cooper", "Cooper, Edgerrin")] + [{"player": None, "pos": "LB", "fpg": 1}]
        self.assertEqual(bfa.build({"freeAgents": rows}, DATA, "x")["players"], [])

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

class BotOpsBlocker3Pending(unittest.TestCase):
    """Blocker 3: every leak Bot Ops found must stop the run."""
    NOW = datetime(2026, 10, 23, 9, 0, tzinfo=PT)
    CASES = [
        {"trades": [{"with": "A", "status": "proposed"}]},
        {"waivers": [{"player": "Martin Emerson", "bidStatus": "PENDING"}]},
        {"claimsQueue": [{"player": "X"}]},
        {"trades": [{"with": "A", "status": "Pending "}]},
        {"waivers": [{"player": "Martin Emerson", "state": "submitted", "faab": 4}]},
        {"news": [{"text": "Eddie bid $40 on X, pending"}]},
        {"waivers": [{"player": "Martin Emerson", "why": "claim pending Wed"}]},
        {"trades": [{"with": "A", "why": "offer is pending"}]},
        {"pendingClaims": [{"player": "X"}]},
        {"eddies": {"bids": [3]}},
    ]
    def test_each_case_raises(self):
        for c in self.CASES:
            w = {"week": 7, "waivers": [], **c}
            with self.assertRaises(wc.PendingError, msg=c): bw.build(w, DATA, self.NOW)
    def test_cli_nonzero_nothing_written(self):
        d = stage(); w = json.loads((d / "warroom.json").read_text()); w["trades"] = [{"with": "A", "status": "proposed"}]
        (d / "warroom.json").write_text(json.dumps(w)); before = (d / "warroom.json").read_bytes()
        r = subprocess.run([sys.executable, str(ROOT / "scripts/build_warroom.py"), "--data-dir", str(d), "--no-fantrax"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertEqual((d / "warroom.json").read_bytes(), before)
    def test_clean_plan_passes_and_keeps_bid_rec(self):
        w = {"week": 7, "waivers": [{"rank": 1, "player": "Martin Emerson", "bid": 0}],
             "trades": [{"with": "B", "why": "idea"}],
             "news": [{"text": "0 pending claims, 0 pending trades."}], "injuryWatch": [{"practice": "Thu pending"}]}
        d = bw.build(w, DATA, self.NOW, raw={"rosters": [], "trades": {"pending": [1]}, "scraped": "s"}, raw_name="r.json")
        self.assertEqual(d["waivers"][0]["bid"], 0)
        self.assertEqual(set(d["fantraxRaw"]), {"file", "scraped"})  # nothing else copied from raw
    def test_committed_warroom_has_no_pending(self):
        self.assertFalse(wc.has_pending(json.loads((DATA / "warroom.json").read_text())))

class BotOpsBlocker4Atomic(unittest.TestCase):
    """Blocker 4: a failed swap leaves data/ byte-identical with no .tmp / .data-* leftovers."""
    def test_swap_failure_rolls_back(self):
        import refresh_warroom as rw
        root = Path(tempfile.mkdtemp()); data = root / "data"; data.mkdir()
        (data / "warroom.json").write_text("old"); (data / "keep.json").write_text("{}")
        st = Path(tempfile.mkdtemp()) / "data"; st.mkdir()
        (st / "warroom.json").write_text("new"); (st / "green-dots-status.json").write_text("{}")
        calls = []
        def bad(a, b):
            calls.append(1)
            if len(calls) == 2: raise OSError("injected")
            os.rename(a, b)
        with self.assertRaises(OSError): rw.swap_in(st, data, bad)
        self.assertEqual((data / "warroom.json").read_text(), "old")
        self.assertFalse((data / "green-dots-status.json").exists())
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["data"])
        self.assertEqual([p for p in data.rglob("*.tmp")], [])
    def test_swap_success(self):
        import refresh_warroom as rw
        root = Path(tempfile.mkdtemp()); data = root / "data"; data.mkdir(); (data / "a.json").write_text("1")
        st = Path(tempfile.mkdtemp()) / "data"; st.mkdir(); (st / "a.json").write_text("2"); (st / "b.json").write_text("3")
        rw.swap_in(st, data)
        self.assertEqual((data / "a.json").read_text(), "2"); self.assertEqual(sorted(p.name for p in root.iterdir()), ["data"])

class BotOpsNodeWhitelist(unittest.TestCase):
    def setUp(self):
        import refresh_warroom as rw; self.v = rw.node_verdict
        self.allowed = {"known one"}
    def test_nested_failure_caught(self):
        out = "TAP version 13\n    not ok 1 - nested new failure\nnot ok 2 - known one\n# pass 3\n# fail 2\n"
        self.assertIn("nested new failure", self.v(1, out, self.allowed))
    def test_crash_is_fail(self):
        self.assertIsNotNone(self.v(1, "Error: boom\n", self.allowed))
        self.assertIsNotNone(self.v(0, "", self.allowed))
    def test_only_known_passes(self):
        self.assertIsNone(self.v(1, "not ok 2 - known one\n# pass 3\n# fail 1\n", self.allowed))

class BotOpsNewestByTimestamp(unittest.TestCase):
    def test_newest_by_scrape_time_not_name(self):
        d = Path(tempfile.mkdtemp())
        (d / "fantrax-scrape-2026-12-31-zzz-newsletter.json").write_text(json.dumps({"scrapedAt": "2026-10-20T10:00:00-07:00", "freeAgents": []}))
        (d / "fantrax-scrape-2026-10-22-pm-newsletter.json").write_text(json.dumps({"scrapedAt": "2026-10-22T14:58:00-07:00", "freeAgents": []}))
        (d / "fantrax-scrape-2026-10-23-future-newsletter.json").write_text(json.dumps({"scrapedAt": "2027-01-01T00:00:00-08:00", "freeAgents": []}))
        (d / "fantrax-scrape-2026-10-23-partial-newsletter.json").write_text(json.dumps({"scrapedAt": "2026-10-22T20:00:00-07:00", "partial": True, "freeAgents": []}))
        f, _, t = wc.latest(str(d / "fantrax-scrape-*-newsletter.json"), "freeAgents", datetime(2026, 10, 22, 22, 0, tzinfo=PT))
        self.assertEqual(f.name, "fantrax-scrape-2026-10-22-pm-newsletter.json")
    def test_scraped_text_formats(self):
        self.assertEqual(wc.iso_pt(wc.scrape_time({"scraped": "2026-10-22 ~06:17-06:30 PDT (AM sync)"})), "2026-10-22T06:17:00-07:00")
        self.assertEqual(wc.iso_pt(wc.scrape_time({"scrape_time_PT": "2026-10-22 ~9:50 PM"})), "2026-10-22T21:50:00-07:00")
    def test_now_without_offset_is_pt(self):
        self.assertEqual(wc.iso_pt(wc.parse_now("2026-10-22T23:30:00")), "2026-10-22T23:30:00-07:00")

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
    def test_unresolved_team_refuses_rebuild(self):
        post = json.loads((FIX / "green-dot-post-synthetic.json").read_text())
        self._fixture_roster(post)
        post = {"body_html": post["body_html"].replace("Week 7 Green Dot: Playerca Alpha", "No dot info.")}
        gd, st = rgd.run(self.d, self.now(), json.loads((FIX / "archive-w7-free.json").read_text()), lambda s: post)
        self.assertFalse(st["rebuilt"]); self.assertTrue(st["stale"]); self.assertIn("BAL", st["parse"]["unresolved"])
    def test_finished_with_the_dot_wins(self):
        h = "<h2>Atlanta Falcons</h2><p>Text.</p><p>Week 6 Green Dot: Divine Deablo (Josh Woods finished with the dot with both Deablo and Daniels hurt)</p>"
        t, u = rgd.parse(h, 6)
        self.assertEqual(t[0]["greenDot"], "Josh Woods")
    def test_bye_marked(self):
        t, u = rgd.parse("<h2>Detroit Lions</h2><p>Week 6 Green Dot: Bye</p>", 6, [{"team": "DET", "greenDot": "Jack Campbell", "fullTime": []}])
        self.assertTrue(t[0]["bye"]); self.assertEqual(t[0]["greenDot"], "Jack Campbell"); self.assertNotIn("DET", u)
    def _fixture_roster(self, post):
        import re
        names = sorted(set(re.findall(r"Player[a-z]{2} Alpha", post["body_html"]))) + ["Josh Woods", "Quay Walker", "Shemar James"]
        (self.d / "hq" / "rosters").mkdir(parents=True, exist_ok=True)
        (self.d / "hq" / "rosters" / "zz-test-fixture.json").write_text(json.dumps({"players": [{"player": n} for n in names]}))
    def test_rebuild_from_free_post(self):
        post = json.loads((FIX / "green-dot-post-synthetic.json").read_text())
        self._fixture_roster(post)
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

class BotOpsRound2(unittest.TestCase):
    NOW = datetime(2026, 10, 23, 9, 0, tzinfo=PT)
    # Blocker 1: decorated / squashed names
    def test_decorated_cooper_variants_blocked(self):
        recs = [{"player": n} for n in ("Edgerrin Cooper (GB)", "E.Cooper", "Edgerrin Cooper - LB GB", "Edgerrin Cooper (LB, GB)",
                                        "Edgerrin Cooper – GB", "Edgerrin Cooper, LB GB", "Edgerrin Cooper [IR]", "E.  Cooper",
                                        "Edgerrin_Cooper", "Booker, Austin (CHI)", "A.Booker")]
        out = bw.build({"week": 7, "waivers": recs}, DATA, self.NOW)["waivers"]
        self.assertEqual(out, [])
        rows = [{"player": n, "pos": "LB", "team": "GB", "fpg": 1} for n in ("Edgerrin Cooper (GB)", "E.Cooper", "Edgerrin Cooper - LB GB")]
        self.assertEqual(bfa.build({"freeAgents": rows}, DATA, "x")["players"], [])
    def test_real_names_survive_normalization(self):
        out = bw.build({"week": 7, "waivers": [{"player": n} for n in ("Darius Cooper (PHI)", "D.J. Reed", "Amari Cooper - WR PIT")]}, DATA, self.NOW)["waivers"]
        self.assertEqual(len(out), 3)
        self.assertEqual(wc.norm("D.J. Reed"), wc.norm("DJ Reed"))
    # Blocker 2: empty / wiped lists, seed floor
    def test_empty_season_ending_fails(self):
        d = stage(); (d / "season-ending.json").write_text('{"players": []}')
        with self.assertRaises(wc.ListError): wc.season_ending(d)
        with self.assertRaises(wc.ListError): bw.build({"week": 7, "waivers": []}, d, self.NOW)
    def test_seed_floor_cooper_required(self):
        d = stage(); (d / "season-ending.json").write_text(json.dumps({"players": [{"name": "Somebody Else", "pos": "LB", "team": "X"}]}))
        with self.assertRaises(wc.ListError) as c: wc.season_ending(d)
        self.assertIn("Edgerrin Cooper", str(c.exception))
    def test_do_not_pitch_empty_explicit_ok_but_not_null(self):
        d = stage(); (d / "do-not-pitch.json").write_text('{"players": []}')
        self.assertFalse(wc.do_not_pitch(d, 7).match("Austin Booker"))
        for bad in ("", "{}", '{"players": null}', "[]"):
            (d / "do-not-pitch.json").write_text(bad)
            with self.assertRaises(wc.ListError, msg=bad): wc.do_not_pitch(d, 7)
    # Pending tuning
    def test_pend_and_awaiting_approval_block(self):
        for w in ({"waivers": [{"player": "Martin Emerson", "why": "PEND"}]},
                  {"waivers": [{"player": "Martin Emerson", "why": "awaiting approval of claim"}]},
                  {"trades": [{"with": "A", "status": "PEND"}]},
                  {"trades": [{"with": "A", "status": "Awaiting  Approval"}]},
                  {"trades": [{"with": "A", "status": "Open"}]},
                  {"waivers": [{"player": "Martin Emerson", "claimStatus": "open"}]}):
            with self.assertRaises(wc.PendingError, msg=w): bw.build({"week": 7, **w}, DATA, self.NOW)
    def test_injury_pending_and_open_status_allowed(self):
        # Round 4 rule: inside waivers/trades/drops ANY 'pending' blocks (fail closed); outside, injury text is fine.
        w = {"week": 7, "waivers": [{"player": "Martin Emerson", "why": "Stream."}],
             "injuryWatch": [{"player": "X", "status": "Open", "note": "MRI results pending"}],
             "news": [{"text": "Hall test results pending"}]}
        self.assertEqual(len(bw.build(w, DATA, self.NOW)["waivers"]), 1)
        with self.assertRaises(wc.PendingError):
            bw.build({"week": 7, "waivers": [{"player": "Martin Emerson", "why": "MRI results pending"}]}, DATA, self.NOW)
    # Green dots tuning
    def test_green_dot_sentence_end_not_merged(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 6 Green Dot: Josh Woods. Divine Deablo finished with the dot.</p>", 6)
        self.assertIn(t[0]["greenDot"], ("Divine Deablo", "Josh Woods")); self.assertNotIn(".", t[0]["greenDot"])
    def test_took_over_the_dot(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 6 Green Dot: Divine Deablo (left hurt; Josh Woods took over the dot)</p>", 6)
        self.assertEqual(t[0]["greenDot"], "Josh Woods")
    def test_bye_week_question_not_bye(self):
        t, u = rgd.parse("<h2>Detroit Lions</h2><p>Week 6 Green Dot: Bye week? No. Jack Campbell kept it.</p>", 6)
        self.assertFalse(t[0].get("bye")); self.assertIn("DET", u)
    def test_unknown_name_refused(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 6 Green Dot: Fake Person</p>", 6, None, {"josh woods"})
        self.assertIsNone(t[0]["greenDot"]); self.assertIn("ATL", u)
    def test_known_players_includes_backups(self):
        self.assertIn("josh woods", rgd.known_players(DATA))
    # Swap double failure
    def test_swap_and_rollback_both_fail_restores_from_backup(self):
        import refresh_warroom as rw
        root = Path(tempfile.mkdtemp()); data = root / "data"; data.mkdir()
        (data / "warroom.json").write_text("old"); (data / "sub").mkdir(); (data / "sub" / "x.json").write_text("1")
        st = Path(tempfile.mkdtemp()) / "data"; st.mkdir(); (st / "warroom.json").write_text("new")
        n = []
        def bad(a, b):
            n.append(1)
            if len(n) >= 2: raise OSError("injected")
            os.rename(a, b)
        with self.assertRaises(rw.SwapError): rw.swap_in(st, data, bad)
        self.assertEqual((data / "warroom.json").read_text(), "old"); self.assertEqual((data / "sub" / "x.json").read_text(), "1")
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["data"])
    def test_runner_exits_nonzero_on_double_failure(self):
        import refresh_warroom as rw
        orig = rw.swap_in
        rw.swap_in = lambda a, b: (_ for _ in ()).throw(rw.SwapError("x"))
        try:
            rc = rw.main(["--mode", "ci", "--skip-tests", "--root", str(self._scratch())])
        finally:
            rw.swap_in = orig
        self.assertNotEqual(rc, 0)
    def _scratch(self):
        r = Path(tempfile.mkdtemp()) / "repo"
        shutil.copytree(ROOT, r, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        shutil.copytree(DATA, r / "data", dirs_exist_ok=True)
        (r / "data" / "green-dots-status.json").write_text('{"force": "change"}')
        return r
    # DST
    def test_ambiguous_dst_requires_offset(self):
        with self.assertRaises(wc.AmbiguousTime): wc.parse_now("2026-11-01T01:30:00")
        self.assertEqual(wc.iso_pt(wc.parse_now("2026-11-01T01:30:00-08:00")), "2026-11-01T01:30:00-08:00")
        self.assertEqual(wc.iso_pt(wc.parse_now("2026-11-01T01:30:00-07:00")), "2026-11-01T01:30:00-07:00")
        self.assertIsNone(wc.scrape_time({"scraped": "2026-11-01 ~1:30 AM"}))
        self.assertIsNotNone(wc.scrape_time({"scraped": "2026-11-01 ~1:30 AM PST"}))
    def test_nonexistent_spring_time_fails(self):
        with self.assertRaises(wc.AmbiguousTime): wc.parse_now("2027-03-14T02:30:00")

if __name__ == "__main__":
    unittest.main()
