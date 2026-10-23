"""Bot Ops regression suite: every case Bot Ops failed us on in review rounds 1-3 (Oct 22 2026).
Sources: /workspace/bot-ops/bad-data-test/results-2026-10-22-eddie-warroom-review{,-round2,-round3}.md
One test method per case. Classes: Round1, Round2, Round3 (plus the 'no false exclusion' controls those rounds
listed). scripts/eddie cases run that repo's build_free_agents.py from WU_EDDIE_DIR (default
/workspace/scripts-eddie-wt, else /workspace/scripts/eddie); they are skipped ONLY on GitHub Actions, where the
box repo does not exist. Run: python3 -m unittest tests/py/test_botops_regression.py -v"""
import json, os, re, shutil, subprocess, sys, tempfile, unittest
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import warroom_common as wc, build_warroom as bw, build_free_agents as bfa, refresh_green_dots as rgd, refresh_warroom as rw
DATA = Path(os.environ.get("WU_DATA_DIR") or ROOT / "data")
PT = wc.PT
NOW = datetime(2026, 10, 23, 9, 0, tzinfo=PT)
EDDIE = next((Path(p) for p in (os.environ.get("WU_EDDIE_DIR"), "/workspace/scripts-eddie-wt", "/workspace/scripts/eddie")
              if p and (Path(p) / "test_build_free_agents.py").exists()), None)
ON_GHA = bool(os.environ.get("GITHUB_ACTIONS"))

def stage():
    d = Path(tempfile.mkdtemp()) / "data"; shutil.copytree(DATA, d); return d
def recs(names): return [{"rank": i + 1, "player": n} for i, n in enumerate(names)]
def waiver_out(names, data=DATA): return bw.build({"week": 7, "waivers": recs(names)}, data, NOW)["waivers"]
def fa_out(names, data=DATA):
    return bfa.build({"freeAgents": [{"player": n, "pos": "LB", "team": "GB", "fpg": 1} for n in names]}, data, "x")["players"]
SE_GOOD = json.dumps({"players": [{"name": "Edgerrin Cooper", "pos": "LB", "team": "GB"}]})
def eddie(se_text, names):
    d = Path(tempfile.mkdtemp())
    if se_text is not None: (d / "se.json").write_text(se_text)
    (d / "s.json").write_text(json.dumps({"freeAgents": [{"player": n, "pos": "LB", "team": "GB", "fpg": 1} for n in names]}))
    r = subprocess.run([sys.executable, str(EDDIE / "build_free_agents.py"), str(d / "s.json"), str(d / "o.json"), "x"],
                       env=dict(os.environ, WU_SEASON_ENDING=str(d / "se.json")), capture_output=True, text=True)
    return r.returncode, (json.loads((d / "o.json").read_text())["players"] if (d / "o.json").exists() else None)
def cli_warroom(d):
    return subprocess.run([sys.executable, str(ROOT / "scripts/build_warroom.py"), "--data-dir", str(d), "--no-fantrax"],
                          capture_output=True, text=True)

def _mk(fn): return lambda self: fn(self)
def add_cases(cls, prefix, cases, fn):
    for i, c in enumerate(cases):
        slug = re.sub(r"[^a-z0-9]+", "_", str(c if not isinstance(c, dict) else json.dumps(c)).lower())[:40].strip("_")
        setattr(cls, f"test_{prefix}_{i:02d}_{slug}", (lambda c: lambda self: fn(self, c))(c))

class Base(unittest.TestCase):
    def blocked(self, w):
        with self.assertRaises(wc.PendingError, msg=w):
            bw.build({"week": 7, **w}, DATA, NOW)
    def excluded(self, n):
        self.assertEqual(waiver_out([n]), [], n); self.assertEqual(fa_out([n]), [], n)
    def kept(self, n):
        self.assertEqual(len(waiver_out([n])), 1, n)
    @unittest.skipIf(ON_GHA or EDDIE is None, "scripts/eddie not on this machine")
    def _eddie(self): pass

def eddie_case(fn):
    return unittest.skipIf(ON_GHA or EDDIE is None, "scripts/eddie repo not on this machine")(fn)

# ============================== ROUND 1 ==============================
class Round1(Base):
    def test_b1_missing_season_ending_warroom(self):
        d = stage(); (d / "season-ending.json").unlink()
        with self.assertRaises(wc.ListError): bw.build({"week": 7, "waivers": recs(["Edgerrin Cooper"])}, d, NOW)
    def test_b1_missing_season_ending_fa(self):
        d = stage(); (d / "season-ending.json").unlink()
        with self.assertRaises(wc.ListError): fa_out(["Edgerrin Cooper"], d)
    def test_b1_missing_do_not_pitch(self):
        d = stage(); (d / "do-not-pitch.json").unlink()
        with self.assertRaises(wc.ListError): waiver_out(["Austin Booker"], d)
    def test_b1_cli_missing_list_nonzero_nothing_written(self):
        d = stage(); (d / "season-ending.json").unlink(); before = (d / "warroom.json").read_bytes()
        self.assertNotEqual(cli_warroom(d).returncode, 0); self.assertEqual((d / "warroom.json").read_bytes(), before)
    @eddie_case
    def test_b1_eddie_missing_list_fails(self):
        rc, out = eddie(None, ["Edgerrin Cooper"]); self.assertNotEqual(rc, 0); self.assertIsNone(out)
    @eddie_case
    def test_b1_eddie_lowercase_and_trailing_space(self):
        rc, out = eddie(SE_GOOD, ["edgerrin cooper", "Edgerrin Cooper "]); self.assertEqual((rc, out), (0, []))
    def test_b2_initial_e_cooper(self): self.excluded("E. Cooper")
    def test_b2_booker_comma(self): self.assertEqual(waiver_out(["Booker, Austin"]), [])
    def test_b2_id_only_rec_blocked(self):
        self.assertEqual(bw.build({"week": 7, "waivers": [{"playerId": "abc"}]}, DATA, NOW)["waivers"], [])
    def test_b2_null_name_rec_blocked(self):
        self.assertEqual(bw.build({"week": 7, "waivers": [{"player": None}]}, DATA, NOW)["waivers"], [])
    def test_b3_trade_status_proposed(self): self.blocked({"trades": [{"with": "A", "status": "proposed"}]})
    def test_b3_bidstatus_pending(self): self.blocked({"waivers": [{"player": "Martin Emerson", "bidStatus": "PENDING"}]})
    def test_b3_claimsqueue(self): self.blocked({"claimsQueue": [{"player": "X Y"}]})
    def test_b3_status_pending_trailing_space(self): self.blocked({"trades": [{"with": "A", "status": "Pending "}]})
    def test_b3_state_submitted_faab(self): self.blocked({"waivers": [{"player": "Martin Emerson", "state": "submitted", "faab": 4}]})
    def test_b3_free_text_bid_pending(self): self.blocked({"news": [{"text": "Eddie bid $40 on X ... pending"}]})
    def test_b3_top_level_trades_filtered(self): self.blocked({"trades": [{"with": "A", "why": "trade pending league review"}]})
    def test_b3_gate_stops_cli(self):
        d = stage(); w = json.loads((d / "warroom.json").read_text()); w["trades"] = [{"with": "A", "status": "proposed"}]
        (d / "warroom.json").write_text(json.dumps(w)); before = (d / "warroom.json").read_bytes()
        self.assertNotEqual(cli_warroom(d).returncode, 0); self.assertEqual((d / "warroom.json").read_bytes(), before)
    def test_b4_second_rename_failure_rolls_back(self):
        root = Path(tempfile.mkdtemp()); data = root / "data"; data.mkdir(); (data / "warroom.json").write_text("old")
        st = Path(tempfile.mkdtemp()) / "d"; st.mkdir(); (st / "warroom.json").write_text("new"); (st / "green-dots-status.json").write_text("{}")
        n = []
        def bad(a, b):
            n.append(1)
            if len(n) == 2: raise OSError("injected")
            os.rename(a, b)
        with self.assertRaises(OSError): rw.swap_in(st, data, bad)
        self.assertEqual(sorted(p.name for p in data.iterdir()), ["warroom.json"]); self.assertEqual((data / "warroom.json").read_text(), "old")
        self.assertEqual([p.name for p in root.iterdir()], ["data"]); self.assertEqual(list(root.rglob("*.tmp")), [])
    def test_b5_atl_finished_with_dot_is_woods(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 6 Green Dot: Divine Deablo (Josh Woods finished with the dot with both Deablo and Daniels hurt)</p>", 6)
        self.assertEqual(t[0]["greenDot"], "Josh Woods")
    def test_b5_bye_marked_not_empty(self):
        t, u = rgd.parse("<h2>Cincinnati Bengals</h2><p>Week 6 Green Dot: Bye</p>", 6, [{"team": "CIN", "greenDot": "Barrett Carter", "fullTime": []}])
        self.assertTrue(t[0]["bye"]); self.assertEqual(t[0]["greenDot"], "Barrett Carter"); self.assertEqual(u, [x for x in u if x != "CIN"])
    def test_b5_misparse_not_written(self):
        d = stage(); before = (d / "green-dots.json").read_bytes()
        arch = [{"title": "2026 Week 7 Green Dot and Full-Time Linebackers", "audience": "everyone", "slug": "s", "canonical_url": "u", "post_date": "2026-10-27T12:00:00Z"}]
        gd, st = rgd.run(d, datetime(2026, 10, 27, 9, tzinfo=PT), arch, lambda s: {"body_html": "<h2>Atlanta Falcons</h2><p>Week 7 Green Dot: Josh Woods</p>"})
        self.assertFalse(st["rebuilt"]); self.assertTrue(st["stale"]); self.assertEqual((d / "green-dots.json").read_bytes(), before)
    def test_nb_nested_subtest_failure_caught(self):
        self.assertIsNotNone(rw.node_verdict(1, "    not ok 1 - new nested\n# pass 1\n", set()))
    def test_nb_node_crash_is_fail(self):
        self.assertIsNotNone(rw.node_verdict(7, "", set()))
    def test_nb_node_tests_run_on_stage(self):
        seen = []
        orig = rw.sh
        rw.sh = lambda cmd, **kw: (seen.append((cmd, kw.get("cwd"))), subprocess.CompletedProcess(cmd, 0, "# pass 1\n", ""))[1]
        try:
            st = Path(tempfile.mkdtemp()); (st / "tests" / "py").mkdir(parents=True); rw.run_tests(st)
        finally:
            rw.sh = orig
        self.assertTrue(all(Path(c) == st for _, c in seen)); self.assertTrue(any("node" in str(x[0][0]) for x in seen))
    def test_nb_known_failing_hash(self):
        self.assertIn("89e19da", (ROOT / "tests/KNOWN_FAILING.txt").read_text())
    def test_nb_workflow_detects_new_files_and_never_pushes(self):
        y = (ROOT / "docs/workflows/warroom-saturday.yml").read_text()
        self.assertIn("git status --porcelain", y); self.assertNotIn("git push", y); self.assertNotIn("git commit", y)
        self.assertIn("contents: read", y); self.assertIn("upload-artifact", y)
    def test_nb_newest_by_timestamp_not_name(self):
        d = Path(tempfile.mkdtemp())
        (d / "fantrax-scrape-2026-12-31-newsletter.json").write_text(json.dumps({"scrapedAt": "2026-10-20T10:00:00-07:00", "freeAgents": []}))
        (d / "fantrax-scrape-2026-10-22-newsletter.json").write_text(json.dumps({"scrapedAt": "2026-10-22T14:58:00-07:00", "freeAgents": []}))
        f, _, _ = wc.latest(str(d / "fantrax-scrape-*-newsletter.json"), "freeAgents", datetime(2026, 10, 22, 22, tzinfo=PT))
        self.assertEqual(f.name, "fantrax-scrape-2026-10-22-newsletter.json")

# ============================== ROUND 2 ==============================
class Round2(Base):
    def test_b1_team_suffix(self): self.excluded("Edgerrin Cooper (GB)")
    def test_b1_no_space_initial(self): self.excluded("E.Cooper")
    @eddie_case
    def test_b1_eddie_team_suffix_and_no_space(self):
        self.assertEqual(eddie(SE_GOOD, ["Edgerrin Cooper (GB)", "E.Cooper"]), (0, []))
    def test_b2_empty_season_ending_fails(self):
        d = stage(); (d / "season-ending.json").write_text('{"players": []}')
        with self.assertRaises(wc.ListError): waiver_out(["Edgerrin Cooper"], d)
    def test_b2_runner_empty_list_rc1(self):
        d = stage(); (d / "season-ending.json").write_text('{"players": []}')
        self.assertNotEqual(cli_warroom(d).returncode, 0)
    @eddie_case
    def test_b2_eddie_empty_list_fails(self):
        rc, out = eddie('{"players": []}', ["Edgerrin Cooper"]); self.assertNotEqual(rc, 0); self.assertIsNone(out)
    def test_nb_sentence_end_no_bogus_name(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 6 Green Dot: Josh Woods. Deablo finished with the dot.</p>", 6)
        self.assertNotIn("Woods. Deablo", str(t[0]["greenDot"]))
    def test_nb_took_over_the_dot(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 6 Green Dot: Divine Deablo (left hurt; Josh Woods took over the dot)</p>", 6)
        self.assertEqual(t[0]["greenDot"], "Josh Woods")
    def test_nb_bye_week_question_not_bye(self):
        t, u = rgd.parse("<h2>Detroit Lions</h2><p>Week 6 Green Dot: Bye week? No. Jack Campbell kept it.</p>", 6)
        self.assertFalse(t[0].get("bye"))
    def test_nb_roster_check_rejects_unknown(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 6 Green Dot: Fake Person</p>", 6, None, rgd.known_players(DATA))
        self.assertIn("ATL", u)
    def test_nb_mri_pending_outside_offer_sections_allowed(self):
        bw.build({"week": 7, "waivers": [], "lineup": [{"player": "X", "reason": "MRI results pending"}],
                  "injuryWatch": [{"player": "X", "status": "Open", "note": "MRI results pending"}]}, DATA, NOW)
    def test_nb_mri_pending_inside_waivers_blocked(self):  # ambiguous inside an offer section -> block
        self.blocked({"waivers": [{"player": "Martin Emerson", "why": "MRI results pending"}]})
    def test_nb_pend_blocked(self): self.blocked({"waivers": [{"player": "Martin Emerson", "why": "PEND"}]})
    def test_nb_awaiting_approval_blocked(self): self.blocked({"waivers": [{"player": "Martin Emerson", "why": "awaiting approval of claim"}]})
    def test_nb_open_in_trades_blocked(self): self.blocked({"trades": [{"with": "A", "status": "open"}]})
    def test_nb_double_failure_restores_exit2(self):
        root = Path(tempfile.mkdtemp()); data = root / "data"; data.mkdir(); (data / "warroom.json").write_text("old")
        st = Path(tempfile.mkdtemp()) / "d"; st.mkdir(); (st / "warroom.json").write_text("new")
        n = []
        def bad(a, b):
            n.append(1)
            if len(n) >= 2: raise OSError("injected")
            os.rename(a, b)
        with self.assertRaises(rw.SwapError): rw.swap_in(st, data, bad)
        self.assertEqual((data / "warroom.json").read_text(), "old"); self.assertEqual([p.name for p in root.iterdir()], ["data"])
    def test_nb_ambiguous_dst_fails(self):
        with self.assertRaises(wc.AmbiguousTime): wc.parse_now("2026-11-01T01:30:00")

# ============================== ROUND 3 ==============================
R3_PENDING = [
    {"waivers": [{"player": "Martin Emerson", "why": "pending"}]},
    {"waivers": [{"player": "Martin Emerson", "why": "Waiver pending for Eddie"}]},
    {"trades": [{"with": "A", "why": "Pending acceptance"}]},
    {"drops": [{"player": "Brian Robinson", "reason": "drop pending"}]},
    {"waivers": [{"player": "Martin Emerson", "why": "$ 12 pending"}]},
    {"trades": [{"with": "A", "status": "pending-review"}]},
    {"trades": [{"with": "A", "status": "in_review"}]},
    {"trades": [{"with": "A", "status": "Countered"}]},
    {"trades": [{"with": "A", "status": "awaiting response"}]},
    {"waivers": [{"player": "Martin Emerson", "submitted": True}]},
    {"outstanding": [{"type": "claim"}]},
    {"waivers": [{"player": "Martin Emerson", "note": "x"}]},               # unknown key in strict section
    {"claims": [{"player": "Martin Emerson", "bid": 3}]},                   # claim with no completed status
    {"bids": [{"player": "Martin Emerson", "bid": 3, "status": "accepted"}]},  # not a completed value
    {"trades": [{"with": "A", "why": "counter offer sent"}]},
    {"trades": [{"with": "A", "why": "submitted to league"}]},
    {"drops": [{"player": "Brian Robinson", "reason": "outstanding"}]},
]
R3_NAMES_BLOCK = ["Edgerrin Cooper|GB", "Cooper E.", "Cooper, Edgerrin (LB-GB)", "EDGERRIN  COOPER",
                  "Edgerrin Cooper [GB]", "Edgerrin Cooper (IR)", "Edgerrin Cooper - LB GB", "Edgerrin Cooper, LB GB",
                  "Edgerrin Cooper LB", "Edgerrin Cooper IR", "EDGERRIN COOPER GB", "Edgerrin Cooper \u2013 GB",
                  "*Edgerrin Cooper*", "Edgerrin Cooper Jr. (GB - LB)", "E.Cooper", "E.  Cooper", "Edgerrin_Cooper",
                  "A.Booker", "Booker, Austin (CHI)", "Austin Booker DL CHI", "Cooper,E", "COOPER EDGERRIN"]
R3_NAMES_KEEP = ["Darius Cooper", "Amari Cooper", "Ed Cooper", "Eric Cooper", "Jonathan Cooper", "Amari Cooper (PIT)",
                 "Thomas Booker", "Thomas Booker IV", "Kendall Booker", "Austin Brooks", "Edgerrin Cooperton",
                 "Cooper Kupp", "Cooper DeJean", "Bo Nix", "BO NIX", "DJ Moore", "D.J. Moore", "AJ Brown", "Ja'Marr Chase",
                 "Amon-Ra St. Brown", "C.J. Stroud", "T.J. Watt", "Kenneth Walker III", "Brian Robinson Jr.", "Edgerrin Coop"]
class Round3(Base):
    def test_seed_floor_cooper_only_by_id_fails(self):
        d = stage(); (d / "season-ending.json").write_text(json.dumps({"players": [{"id": "fx1"}]}))
        with self.assertRaises(wc.ListError): wc.season_ending(d)
    def test_season_list_comma_form_satisfies_seed(self):
        d = stage(); (d / "season-ending.json").write_text(json.dumps({"players": [{"name": "Cooper, Edgerrin"}]}))
        wc.season_ending(d)
    def test_dnp_empty_explicit_ok_with_extra_keys(self):
        d = stage(); (d / "do-not-pitch.json").write_text('{"about": "x", "players": []}'); wc.do_not_pitch(d, 7)
    def test_dst_spring_gap_2026_fails(self):
        with self.assertRaises(wc.AmbiguousTime): wc.parse_now("2026-03-08T02:30:00")
    def test_dst_explicit_offset_ok(self):
        self.assertEqual(wc.iso_pt(wc.parse_now("2026-11-01T01:30:00-08:00")), "2026-11-01T01:30:00-08:00")
    def test_nb_past_tense_override_skipped(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 6 Green Dot: Divine Deablo. Josh Woods wore the dot last year.</p>", 6)
        self.assertEqual(t[0]["greenDot"], "Divine Deablo")
    def test_nb_took_dot_from(self):
        t, u = rgd.parse("<h2>New Orleans Saints</h2><p>Week 6 Green Dot: Josh Woods (Kaden Elliss took the dot from Josh Woods)</p>", 6)
        self.assertEqual(t[0]["greenDot"], "Kaden Elliss")
    def test_nb_dot_changes_hands_again_last_wins(self):
        t, u = rgd.parse("<h2>New Orleans Saints</h2><p>Week 6 Green Dot: Pete Werner. Kaden Elliss took the dot. Then Pete Werner took the dot back.</p>", 6)
        self.assertEqual(t[0]["greenDot"], "Pete Werner")
    def test_nb_no_private_tempfile_api(self):
        self.assertNotIn("_get_candidate_names", (ROOT / "scripts/refresh_warroom.py").read_text())
    def test_nb_disk_use_documented(self):
        self.assertRegex((ROOT / "README.md").read_text(), r"(?i)disk")
    def test_nb_restore_from_backup_fails_exit2_loud(self):
        root = Path(tempfile.mkdtemp()); data = root / "data"; data.mkdir(); (data / "warroom.json").write_text("old")
        st = Path(tempfile.mkdtemp()) / "d"; st.mkdir(); (st / "warroom.json").write_text("new")
        n = []; c = []
        def bad_rename(a, b):
            n.append(1)
            if len(n) >= 2: raise OSError("rename injected")
            os.rename(a, b)
        def bad_copy(a, b):
            c.append(1)
            if len(c) >= 3: raise OSError("restore injected")
            shutil.copytree(a, b)
        with self.assertRaises(rw.SwapError) as e: rw.swap_in(st, data, bad_rename, bad_copy)
        self.assertIn("RESTORE FAILED", str(e.exception))
        kept = [p for p in root.iterdir() if p.name.startswith(".data-swap-")]
        self.assertEqual(len(kept), 1); self.assertEqual((kept[0] / "bak" / "warroom.json").read_text(), "old")
        orig = rw.swap_in; rw.swap_in = lambda a, b: (_ for _ in ()).throw(rw.SwapError("!!! DATA RESTORE FAILED test"))
        try:
            r = Path(tempfile.mkdtemp()) / "repo"; shutil.copytree(ROOT, r, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            shutil.copytree(DATA, r / "data", dirs_exist_ok=True); (r / "data" / "green-dots-status.json").write_text('{"x":1}')
            self.assertEqual(rw.main(["--mode", "ci", "--skip-tests", "--root", str(r)]), 2)
        finally:
            rw.swap_in = orig
    def test_runner_pend_input_rc1_data_unchanged(self):
        r = Path(tempfile.mkdtemp()) / "repo"; shutil.copytree(ROOT, r, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        shutil.copytree(DATA, r / "data", dirs_exist_ok=True)
        w = json.loads((r / "data/warroom.json").read_text()); w["waivers"][0]["why"] = "PEND"
        (r / "data/warroom.json").write_text(json.dumps(w)); before = (r / "data/warroom.json").read_bytes()
        self.assertEqual(rw.main(["--mode", "full", "--skip-tests", "--root", str(r)]), 1)
        self.assertEqual((r / "data/warroom.json").read_bytes(), before)
        self.assertEqual([p for p in r.iterdir() if p.name.startswith(".data-")], [])
    @eddie_case
    def test_b2_eddie_round3_formats(self):
        self.assertEqual(eddie(SE_GOOD, ["Edgerrin Cooper|GB", "Cooper E.", "Cooper, Edgerrin (LB-GB)", "EDGERRIN  COOPER"]), (0, []))
    @eddie_case
    def test_b2_eddie_keeps_other_coopers(self):
        rc, out = eddie(SE_GOOD, ["Darius Cooper", "Amari Cooper"]); self.assertEqual([p["player"] for p in out], ["Darius Cooper", "Amari Cooper"])
add_cases(Round3, "b1_pending_blocked", R3_PENDING, lambda self, c: self.blocked(c))
add_cases(Round3, "b2_name_blocked", R3_NAMES_BLOCK, lambda self, n: self.assertEqual(waiver_out([n]), [], n))
add_cases(Round3, "b2_name_kept", R3_NAMES_KEEP, lambda self, n: self.kept(n))

if __name__ == "__main__":
    unittest.main()
