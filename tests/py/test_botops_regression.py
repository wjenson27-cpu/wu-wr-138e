"""Bot Ops regression suite: every case Bot Ops failed us on in review rounds 1-4 (Oct 22 2026).
Sources: /workspace/bot-ops/bad-data-test/results-2026-10-22-eddie-warroom-review{,-round2,-round3,-round4}.md
One test method per case. Classes: Round1, Round2, Round3, Round4 (round-4 findings, fixed in round 5) and History
(the 18 past versions of data/warroom.json on origin/main, saved under tests/fixtures/warroom-history/; every one
must pass the pending gate), plus the 'no false exclusion' controls those rounds listed. scripts/eddie cases run that repo's build_free_agents.py from WU_EDDIE_DIR (default
/workspace/scripts-eddie-wt, else /workspace/scripts/eddie); they are skipped ONLY on GitHub Actions, where the
box repo does not exist. Run: python3 -m unittest tests/py/test_botops_regression.py -v"""
import json, os, re, shutil, subprocess, sys, tempfile, unittest
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
def _dummy_pending_names():
    """A dummy names file stamped with the latest real raw scrape (so the stale check passes); never the private file."""
    import tempfile as _t
    fx = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "pending-names-test.json").read_text())
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import warroom_common as _wc
    f, d, _ = _wc.latest("/workspace/fantrax-raw-*.json", "rosters")
    fx["scraped"] = d.get("scraped") if isinstance(d, dict) else None
    out = Path(_t.mkdtemp()) / "pending-names-test.json"
    out.write_text(json.dumps(fx))
    return str(out)
os.environ.setdefault("WARROOM_PENDING_NAMES", _dummy_pending_names())  # real scrape may have pending>=1; never the private file
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
        """Not published: the build either stops (PendingError) or (round 8) drops the free text."""
        try:
            out = bw.build({"week": 7, **w}, DATA, NOW)
        except wc.PendingError:
            return
        texts = []
        def walk(o, k=None):
            if isinstance(o, dict):
                for kk, v in o.items(): walk(v, kk)
            elif isinstance(o, list):
                for v in o: walk(v, k)
            elif isinstance(o, str) and k in ("text", "why", "reason", "note", "notes", "stats"):
                texts.append(o)
        walk(w)
        self.assertTrue(texts, f"not blocked and no free text to drop: {w}")
        dumped = json.dumps(out, ensure_ascii=False)
        for t in texts:
            self.assertNotIn(json.dumps(t, ensure_ascii=False)[1:-1], dumped, f"published: {t!r}")
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

# ============================== ROUND 4 (fixed in round 5) ==============================
def w_why(t): return {"waivers": [{"player": "Martin Emerson", "why": t}]}
def t_why(t): return {"trades": [{"with": "A", "why": t}]}
def d_reason(t): return {"drops": [{"player": "Brian Robinson", "reason": t}]}
def news(t): return {"news": [{"text": t}]}
R4_PASS_WORDS = ["suspended", "dependent", "must-spend", "not an offer", "0 pending claims", "preview", "reviewed",
                 "queued", "encounter", "countering", "reviewed tape", "queued up", "in progress", "submits",
                 "proposition", "sack/TFL-dependent", "Greenlaw suspended 1 game (appeal Tue)", "no pending",
                 "0 pending trades", "Not a must-spend Saturday.", "Smack only, not an offer: Chase is on bye",
                 "not a formal offer.", "role depends on Delpit.", "FAAB $60. Pending 0/0.", "pending 0/0",
                 "0 pending claims, 0 pending trades", "offers flex upside", "awaits a soft matchup",
                 "outstanding tape vs CHI", "Counter run scheme fits him"]
R4_PASS_GENERAL = R4_PASS_WORDS + ["Greenlaw appeal pending; Dugger every-down MNF if upheld (pass on FAAB).",
                                   "MRI results pending"]
R4_BLOCK_TEXT = ["pending", "Waiver pending for Eddie", "Pending acceptance", "drop pending", "$ 12 pending",
                 "pending-review", "in_review", "in review", "under review", "Countered", "counter offer sent",
                 "counteroffer", "awaiting response", "awaiting approval", "PEND", "PENDING", "submitted to league",
                 "proposed", "trade proposal", "claim in queue", "trade offer sent", "offer sent to Nathan",
                 "not an offer; trade offer sent", "outstanding bid", "claim still outstanding", "outstanding",
                 "\uff50\uff45\uff4e\uff44\uff49\uff4e\uff47",          # fullwidth
                 "pen\u200bding", "pen\u200cding", "pen\u200dding", "pen\u2060ding", "pen\ufeffding", "pen\u00adding",
                 "p\u0435nding bid",                                         # Cyrillic e
                 "\u0440ending"]                                             # Cyrillic p
R4_BLOCK_STATUS = ["pending", "Pending ", "PEND", "pending-review", "in_review", "Countered", "awaiting response",
                   "queued", "open", "proposed", "accepted", "p\u0435nding", "c\u043empleted", "", 0, 1, 1.5, None,
                   "\uff50\uff45\uff4e\uff44\uff49\uff4e\uff47"]
R4_BLOCK_GENERAL = ["Eddie bid $40 on X ... pending", "PEND", "awaiting approval of claim", "\uff30\uff25\uff2e\uff24",
                    "p\u0435nding bid", "pen\u200bding claim", "\uff50\uff45\uff4e\uff44\uff49\uff4e\uff47 trade",
                    "outstanding claim on X"]
R4_NAMES_KEEP = ["KC Concepcion", "KC Concepcion Jr.", "Jordan van den Berg", "Darius Cooper", "Keith Cooper",
                 "Jonathon Cooper", "Omar Cooper", "Omar Cooper Jr.", "Cooper DeJean", "Cooper Kupp", "Cooper McDonald",
                 "Cooper Rush", "Thomas Booker", "Thomas Booker IV", "Kendall Booker", "Alex Booker", "Ed Cooper",
                 "Eric Cooper", "Elijah Cooper", "Cooper Austin"]
# Season-ending Cooper in any disguise: out of waiver recs AND the FA pool.
R4_NAMES_BLOCK = ["Edgerrin Coo\u200bper", "Edgerrin Coo\u00adper", "\ufeffEdgerrin Cooper", "Edgerrin\u2060 Cooper",
                  "\uff25\uff44\uff47\uff45\uff52\uff52\uff49\uff4e \uff23\uff4f\uff4f\uff50\uff45\uff52",   # fullwidth
                  "Edgerrin Cooper|GB", "Cooper E.", "Cooper,Edgerrin", "Edgerrin Cooper 52", "Edgerrin Cooper"]
# Non-Latin letters (Cyrillic/Greek lookalikes): a waiver rec with one STOPS the run (fail closed); the FA pool drops it.
R4_NAMES_NONLATIN = ["Edgerrin C\u043eoper", "\u0415dgerrin Cooper", "Edg\u0435rrin Cooper (GB)", "Austin B\u043eoker",
                     "Edgerrin Co\u03bfper", "Darius C\u043eoper"]
def roster_names():
    names = set()
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("player", "name") and isinstance(v, str): names.add(v)
                else: walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    for f in DATA.rglob("*.json"):
        try: walk(json.loads(f.read_text()))
        except Exception: pass
    return names

class Round4(Base):
    def passes(self, w):
        bw.build({"week": 7, **w}, DATA, NOW)
    def test_status_key_casing_blocks(self): self.blocked({"waivers": [{"player": "Martin Emerson", "Status": "completed"}]})
    def test_completed_status_passes(self): self.passes({"trades": [{"with": "A", "status": "Completed"}]})
    def test_unknown_top_level_casing_blocks(self):
        for k in ("Waivers", "WAIVERS", "Trades"): self.blocked({k: []})
    def test_nested_give_list_pending_blocks(self): self.blocked({"trades": [{"with": "A", "give": [["pending"]]}]})
    def test_bid_as_string_blocks(self): self.blocked({"bids": ["Martin Emerson $3"]})
    def test_drops_not_list_blocks(self): self.blocked({"drops": {"player": "X"}})
    def test_pending_keys_in_idp_and_boxsafety_block(self):
        self.blocked({"idp": [{"player": "X", "pendingClaim": 1}]}); self.blocked({"boxSafety": {"outstanding": []}})
    def test_nested_eddie_outstanding_blocks(self): self.blocked({"lineup": [{"eddie": {"outstanding": [{"type": "claim"}]}}]})
    def test_general_numeric_status_blocks(self):
        for v in (0, 1, 2.5, True, [1], {"x": 1}): self.blocked({"lineup": [{"player": "X", "status": v}]})
    def test_general_string_and_null_status_ok(self):
        self.passes({"lineup": [{"player": "X", "status": "Suspended"}], "injuryWatch": [{"player": "Y", "status": None}]})
    def test_general_status_value_words_block(self):
        for v in ("pending-review", "in_review", "queued", "Awaiting approval", "Countered", "p\u0435nding"):
            self.blocked({"lineup": [{"player": "X", "status": v}]})
    def test_roster_sweep_only_booker_and_cooper_excluded(self):
        names = roster_names(); self.assertGreaterEqual(len(names), 2000)
        se, dnp = wc.season_ending(DATA), wc.do_not_pitch(DATA, 7, NOW.date())
        self.assertEqual(sorted(n for n in names if se.match(n) or dnp.match(n)), ["Austin Booker", "Edgerrin Cooper"])
        self.assertIn("KC Concepcion", names); self.assertTrue(wc.identifiable("KC Concepcion"))
    def test_van_den_berg_keeps_den(self): self.assertEqual(wc.name_tokens("Jordan van den Berg"), ["jordan", "van", "den", "berg"])
    def test_kc_concepcion_tokens(self): self.assertEqual(wc.name_tokens("KC Concepcion (WR, CLE)"), ["kc", "concepcion"])
    def test_team_code_still_stripped_elsewhere(self): self.assertEqual(wc.name_tokens("Cooper KC"), ["cooper"])
    def test_cyrillic_name_unidentifiable(self):
        self.assertFalse(wc.identifiable("Edgerrin C\u043eoper")); self.assertEqual(wc.name_tokens("Edgerrin C\u043eoper"), [])
    def test_fa_output_never_has_cyrillic_cooper(self):
        out = fa_out(["Edgerrin C\u043eoper", "Darius Cooper", "KC Concepcion"])
        self.assertEqual([p["player"] for p in out], ["Darius Cooper", "KC Concepcion"])
    def test_prep_strips_zero_width_and_nfkc(self):
        self.assertEqual(wc.prep("\uff50en\u200b\u200c\u200d\u2060\ufeff\u00adding"), "pending")
    def test_green_dot_current_week_in_week_n_counts(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 7 Green Dot: Divine Deablo. In Week 7, Josh Woods took over the dot.</p>", 7)
        self.assertEqual(t[0]["greenDot"], "Josh Woods")
    def test_green_dot_other_week_ignored(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 7 Green Dot: Divine Deablo. In Week 6, Josh Woods took over the dot.</p>", 7)
        self.assertEqual(t[0]["greenDot"], "Divine Deablo")
    def test_green_dot_hypothetical_ignored(self):
        t, u = rgd.parse("<h2>Atlanta Falcons</h2><p>Week 7 Green Dot: Divine Deablo. If he sits, Josh Woods took over the dot in practice.</p>", 7)
        self.assertEqual(t[0]["greenDot"], "Divine Deablo")
    def test_runner_history_fixture_full_dry_run_rc0(self):
        r = Path(tempfile.mkdtemp()) / "repo"; shutil.copytree(ROOT, r, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        shutil.copytree(DATA, r / "data", dirs_exist_ok=True)
        shutil.copy(HIST / "20261017-150633-dba8a40.json", r / "data/warroom.json")   # 'not an offer' + 'Pending 0/0'
        before = (r / "data/warroom.json").read_bytes()
        self.assertEqual(rw.main(["--mode", "full", "--skip-tests", "--dry-run", "--root", str(r)]), 0)
        self.assertEqual((r / "data/warroom.json").read_bytes(), before)
    @eddie_case
    def test_eddie_round4_names(self):
        rc, out = eddie(SE_GOOD, ["KC Concepcion", "Jordan van den Berg", "Edgerrin C\u043eoper", "Edgerrin Coo\u200bper",
                                  "\uff25\uff44\uff47\uff45\uff52\uff52\uff49\uff4e \uff23\uff4f\uff4f\uff50\uff45\uff52", "Omar Cooper Jr.", "Cooper Rush"])
        self.assertEqual(rc, 0); self.assertEqual([p["player"] for p in out], ["KC Concepcion", "Jordan van den Berg", "Omar Cooper Jr.", "Cooper Rush"])
add_cases(Round4, "pass_waiver_why", R4_PASS_WORDS, lambda self, t: self.passes(w_why(t)))
add_cases(Round4, "pass_trade_why", R4_PASS_WORDS, lambda self, t: self.passes(t_why(t)))
add_cases(Round4, "pass_drop_reason", R4_PASS_WORDS, lambda self, t: self.passes(d_reason(t)))
add_cases(Round4, "pass_news", R4_PASS_GENERAL, lambda self, t: self.passes(news(t)))
add_cases(Round4, "block_waiver_why", R4_BLOCK_TEXT, lambda self, t: self.blocked(w_why(t)))
add_cases(Round4, "block_trade_why", R4_BLOCK_TEXT, lambda self, t: self.blocked(t_why(t)))
add_cases(Round4, "block_status", [(sec, v) for sec in ("waivers", "trades", "drops", "bids", "claims") for v in R4_BLOCK_STATUS],
          lambda self, c: self.blocked({c[0]: [{"player": "Martin Emerson", "status": c[1]} if c[0] != "trades" else {"with": "A", "status": c[1]}]}))
add_cases(Round4, "block_general", R4_BLOCK_GENERAL, lambda self, t: self.blocked(news(t)))
add_cases(Round4, "name_kept", R4_NAMES_KEEP, lambda self, n: (self.kept(n), self.assertEqual(len(fa_out([n])), 1, n)))
add_cases(Round4, "name_blocked", R4_NAMES_BLOCK, lambda self, n: self.excluded(n))
add_cases(Round4, "name_nonlatin_rejected", R4_NAMES_NONLATIN,
          lambda self, n: (self.blocked({"waivers": recs([n])}), self.assertEqual(fa_out([n]), [], n), self.assertFalse(wc.identifiable(n))))
add_cases(Round4, "dnp_booker_out_of_recs", ["Austin Booker", "Booker, Austin (CHI)"], lambda self, n: self.assertEqual(waiver_out([n]), [], n))
add_cases(Round4, "not_matched_by_excluders", ["Edge Cooper", "Ed Cooper", "Cooper Austin", "Kendall Booker", "Jordan van den Berg"],
          lambda self, n: self.assertFalse(wc.season_ending(DATA).match(n) or wc.do_not_pitch(DATA, 7, NOW.date()).match(n), n))

# ============================== ROUND 5 (fixed in round 6) ==============================
R5_BLOCK_GENERAL = ["trade review pending", "waiver review pending", "FAAB bid decision pending",
                    "claim results pending for Eddie", "MRI results pending; trade pending", "Offer review pending",
                    "$40 decision pending"]
R5_PASS_GENERAL = ["MRI results pending", "Greenlaw appeal pending; Dugger every-down MNF if upheld (pass on FAAB).",
                   "Suspension review pending. Waivers clear Wed.", "X-ray results pending"]
R5_BLOCK_STRICT = ["queued claim", "claim queued", "Claim is queued", "pended", "waiting on approval",
                   "waiting for approval", "offer: Emerson for Lloyd", "Offer - Emerson for Lloyd", "p\u00e9nding",
                   "pe\u0301nding", "P\u00c9NDING", "\u00e1waiting approval"]
R5_PASS_STRICT = ["queued", "queued up", "queued up a big game", "Smack only, not an offer: Chase is on bye",
                  "suspended", "reviewed", "encounter", "not an offer", "0 pending claims", "preview", "dependent",
                  "must-spend", "caf\u00e9 hot take"]
def section(sec, t):
    return {"lineup": {"lineup": [{"player": "Martin Emerson", "note": t}]}, "news": news(t),
            "injuryWatch": {"injuryWatch": [{"player": "Martin Emerson", "note": t}]}}[sec]
class Round6(Base):
    passes = Round4.passes
add_cases(Round6, "block_general", [(s, t) for s in ("lineup", "news", "injuryWatch") for t in R5_BLOCK_GENERAL],
          lambda self, c: self.blocked(section(*c)))
add_cases(Round6, "pass_general", [(s, t) for s in ("lineup", "news", "injuryWatch") for t in R5_PASS_GENERAL],
          lambda self, c: self.passes(section(*c)))
add_cases(Round6, "block_strict", [(f.__name__, t) for f in (w_why, t_why, d_reason) for t in R5_BLOCK_STRICT],
          lambda self, c: self.blocked(globals()[c[0]](c[1])))
add_cases(Round6, "pass_strict", [(f.__name__, t) for f in (w_why, t_why, d_reason) for t in R5_PASS_STRICT],
          lambda self, c: self.passes(globals()[c[0]](c[1])))
add_cases(Round6, "block_empty_status", [(s, v) for s in ("lineup", "news") for v in (None, "", "  ", "\u200b")],
          lambda self, c: self.blocked({c[0]: [{"player": "Martin Emerson", "status": c[1]}]}))
add_cases(Round6, "pass_set_status", [(s, v) for s in ("lineup", "news") for v in ("Questionable", "Active", "Suspended")],
          lambda self, c: self.passes({c[0]: [{"player": "Martin Emerson", "status": c[1]}]}))

# ============================== HISTORY: 18 past data/warroom.json on origin/main ==============================
HIST = ROOT / "tests/fixtures/warroom-history"
HIST_FILES = sorted(HIST.glob("*.json"))

R7_PENDING = [  # Bot Ops round 6 + round 7 reports (own-team pending moves, any wording)
    "Eddie bid $12 on Emerson (processes Wed)", "Bid placed", "claim placed $12", "Eddie's claim is in, processes Wed",
    "Eddie put in a claim for Emerson", "claim processes Wed 9 PM", "Eddie's bid: $12", "Eddie sent Nathan a trade",
    "trade sent to Nathan, waiting", "Trade request sent", "Claim submitted", "Eddie's claim is in", "Eddie put in a claim",
    "W7 claim placed", "Top bid placed $12", "QB claim is in", "Eddie bids $12 on Emerson", "Eddie is bidding on Emerson",
    "offers out to Nathan", "Eddie claimed Emerson, not processed yet", "No bid yet. Eddie's claim is in",
    "FAAB $60 bid on Emerson", "Eddie sent Emerson to TTAB for $20 FAAB", "Trade processed, claim pending",
    "completed: trade sent to Nathan", "trade sent to Nathan (one other trade completed)",
    "Eddie claimed Emerson for $12, lost the Lake claim", "Eddie's waiver bid (processed? not yet)",
    "Eddie's trade: accepted? no, still waiting", "Completed trade sent to Nathan, awaiting reply",
    "trade accepted by Eddie, awaiting Nathan", "Trade: Eddie gets Emerson, Nathan gets Lloyd", "NYJ trade sent by Eddie",
    "traded to NYJ by Eddie, pending", "Eddie is going after Emerson with $12", "targeting Emerson with $12 Wed",
    "Eddie put $12 on Emerson", "$12 on Emerson, runs Wed", "$88 FAAB left; $12 on Emerson Wed",
    "Eddie's Emerson add processes Wed", "Emerson add is in for Wed", "pitched Nathan a Lloyd-for-Emerson deal",
    "Lloyd-for-Emerson deal sent to Nathan", "Eddie acquired Emerson? Not yet — Wed", "Emerson pickup pending",
    "Eddie added Emerson (pending Wed)", "deal pending with Nathan", "swap with Nathan pending",
    "proposed Lloyd-for-Emerson to Nathan", "Trade: Nathan gets Lloyd (awaiting)",
    "no bid on X; Eddie claimed Y for $12 Wed", "no bid on X, Eddie claimed Y for $12 Wed",
    "FAAB balance $88 after $12 bid on Emerson", "FAAB left is $88 after Eddie's $12 bid",
    "on waivers until Wed – Eddie has a claim (in)", "if claimed, we drop Z – claim placed", "Eddie filed a claim",
    "Eddie entered a bid", "Eddie lodged a claim", "we offered Lloyd", "Eddie made a claim", "Eddie put a bid",
    "EDDIE CLAIMED EMERSON", "Eddie will claim Emerson", "Eddie is claiming Emerson", "claim hasn't been processed",
    "Eddie cl\u0430imed Emerson", "Eddie cla\u200bimed Emerson", "Eddie \uff43\uff4c\uff41\uff49\uff4d\uff45\uff44 Emerson",
    "Eddie cl\u00e1imed Emerson", "top bid: $12 sent", "sample bid sheet sent", "Rams/Bills bids placed",
    "they claimed CGJ; Eddie claimed Emerson", "Kyle just scooped Pitts; Eddie bids $5",
    "fan claim: Eddie claimed Emerson", "waiver status: Eddie claim in", "claim is insurance; Eddie's claim is in",
    "before any bid, Eddie claimed Emerson", "pass on claims, Eddie filed one anyway",
    "Eagle Ridge Eddies claimed Emerson", "The Eddies traded for Lloyd", "our team put in a bid", "we picked up Emerson",
    "Eddie dropped Lloyd for Emerson", "\u00c9ddie claimed Emerson"]
OTHER_KEPT = ["Saltese sent Stefon Diggs to TTAB for $20 FAAB", "Morningside added McLaughlin $2 (dropped Lloyd)",
              "Nobody claimed Stutsman or CGJ in the Tuesday run", "Ponder to Doubtpfizer $1, Battle to Newman $7",
              "Greenlaw appeal pending", "MRI results pending"]

class Round8(Base):
    """Round 8 design: own moves publish only from structured completed records; own-move free text is dropped."""
    def out(self, w):
        try:
            return json.dumps(bw.build({"week": 7, **w}, DATA, NOW), ensure_ascii=False)
        except wc.PendingError:
            return None                                      # blocked: not published either
    def test_own_pending_never_published(self):
        for c in R7_PENDING:
            for sec, w in (("news", {"news": [{"text": c}]}),
                           ("lineup", {"lineup": [{"player": "Martin Emerson", "reason": c, "status": "ok"}]}),
                           ("waivers", {"waivers": [{"player": "Martin Emerson", "why": c}]}),
                           ("trades", {"trades": [{"with": "A", "why": c}]}),
                           ("injuryWatch", {"injuryWatch": [{"player": "Martin Emerson", "note": c}]}),
                           ("idp", {"idp": [{"player": "Martin Emerson", "notes": c}]})):
                with self.subTest(c=c, sec=sec):
                    o = self.out(w)
                    self.assertTrue(o is None or json.dumps(c, ensure_ascii=False)[1:-1] not in o, o)
    def test_other_teams_text_stays(self):
        for c in OTHER_KEPT:
            with self.subTest(c=c):
                o = self.out({"news": [{"text": c}]})
                self.assertIsNotNone(o); self.assertIn(c, o)
    def test_drop_keeps_rest_of_line(self):
        o = json.loads(self.out({"news": [{"text": "Lake is questionable. Eddie bid $12 on Emerson."}]}))
        self.assertEqual(o["news"], [{"text": "Lake is questionable."}])
    def test_fully_dropped_news_item_removed(self):
        o = json.loads(self.out({"news": [{"text": "Eddie bid $12 on Emerson."}, {"text": "Lake is out."}]}))
        self.assertEqual([n["text"] for n in o["news"]], ["Lake is out."])
    def test_structured_completed_record_still_publishes(self):
        self.assertIn("Completed", self.out({"trades": [{"with": "A", "status": "Completed", "date": "2026-10-20"}]}))
    def test_structured_pending_record_blocks(self):
        self.assertIsNone(self.out({"claims": [{"player": "Martin Emerson", "status": "pending"}]}))
    def test_live_data_builds(self):
        bw.build(json.loads((ROOT / "data/warroom.json").read_text()), DATA, NOW)

R8_CASES = [  # Bot Ops round 8 report
    "Emerson add is in for Wed", "$12 on Emerson, runs Wed", "Lloyd-for-Emerson deal sent to Nathan",
    "Eddie's claim is in, processes Wed", "Emerson claim placed", "completed: trade sent to Nathan for Emerson",
    "Trade: Eddie gets Emerson, Nathan gets Lloyd", "NYJ trade sent by Eddie for Emerson",
    "Eddie claimed Emerson for $12, lost the Lake claim", "Bid: Emerson $12 (Eddie)",
    "Eddie \uff42\uff49\uff44 $12 on Emerson", "Eddie bi\u200bd $12 on Emerson", "targeting Emerson Wed",
    "Eddie is going after Emerson", "Emerson is ours after Wed", "We grab Emerson Wed", "Grabbing Emerson Wed",
    "Emerson incoming Wednesday", "Lake leaves, Emerson arrives Wed", "Emerson at twelve bucks Wed",
    "Eddie b.i.d twelve on Emerson", "Emerson: $12. Wed.", "Emerson ($12, Wed)", "Emerson — $12, Wed",
    "Nathan's Lloyd-for-Emerson deal is in", "Substation sent Lloyd for Emerson",
    "Substation sent Lloyd for Emerson, awaiting reply", "EMERSON claim", "Em\u0435rson claim", "Émerson claim"]
PEND = ["Martin Emerson"]

class Round9(Base):
    """Round 9 input-side design: completed+past move records only; pending sources hard-fail; private pending-name
    safety net over every output string, record and key."""
    def build(self, w, raw=None, raw_name=None):
        try:
            return json.dumps(bw.build({"week": 7, **w}, DATA, NOW, raw=raw, raw_name=raw_name, pending=PEND),
                              ensure_ascii=False)
        except wc.PendingError:
            return None
    def gone(self, w, c):
        o = self.build(w)
        self.assertTrue(o is None or json.dumps(c, ensure_ascii=False)[1:-1] not in o, o)
    def test_round8_cases_every_field(self):
        live = json.loads((ROOT / "data/warroom.json").read_text())
        for c in R8_CASES + R7_PENDING:
            for w in ({"news": [{"text": c}]}, {"lineup": [{"player": "Martin Emerson", "reason": c, "status": "ok"}]},
                      {"waivers": [{"player": "X Y", "why": c}]}, {"waivers": [{"player": "X Y", "tag": c}]},
                      {"waivers": [{"player": "X Y", "drop": c}]}, {"trades": [{"with": c, "why": "x"}]},
                      {"trades": [{"with": "A", "give": [c]}]}, {"injuryWatch": [{"player": "Q R", "note": c}]},
                      {"idp": [{"player": "Q R", "notes": c}]}, {"news": [{c: "x"}]},
                      {**live, "news": live.get("news", []) + [{"text": c}]}):
                with self.subTest(c=c, w=list(w)[:2]):
                    self.gone(w, c)
    def test_fragment_dropped(self):
        o = json.loads(self.build({"news": [{"text": "Lake is out. Eddie bid $12 on Emerson. Processes Wed. Odell starts."}]}))
        self.assertEqual(o["news"][0]["text"], "Lake is out. Odell starts.")
    def test_completed_future_or_undated_excluded(self):
        for r in ({"with": "Nathan", "give": ["Lloyd"], "get": ["X Y"], "status": "completed", "date": "2026-10-28"},
                  {"with": "Nathan", "status": "completed"}, {"with": "Nathan", "status": "completed", "date": "2026-10-23"},
                  {"with": "Nathan", "status": "completed", "date": "soon"}):
            with self.subTest(r=r):
                self.assertEqual(json.loads(self.build({"trades": [r]}))["trades"], [])
    def test_completed_past_variants_publish(self):
        for st in ("completed", "Completed ", "COMPLETED", "Completed\u200b"):
            with self.subTest(st=st):
                self.assertEqual(len(json.loads(self.build({"trades": [{"with": "Nathan", "status": st, "date": "2026-10-21"}]}))["trades"]), 1)
    def test_other_statuses_stop_run(self):
        for st in ("done", "processed", "executed", "c\u043empleted", "completed-pending", "Completed (pending)", None, 1):
            with self.subTest(st=st):
                self.assertIsNone(self.build({"trades": [{"with": "Nathan", "status": st, "date": "2026-10-21"}]}))
    def test_pending_source_hard_fails(self):
        for raw, name in (({"url": "https://www.fantrax.com/fantasy/league/x/transactions/pending"}, "r.json"),
                          ({"url": "https://www.fantrax.com/fantasy/league/x/trade-offers"}, "r.json"),
                          ({"url": "https://www.fantrax.com/fantasy/league/x/home"}, "fantrax-claims-queue.json"),
                          ({"source": "Fantrax pending claims"}, "r.json")):
            with self.subTest(raw=raw):
                self.assertIsNone(self.build({}, raw=raw, raw_name=name))
    def test_pending_keys_in_plan_hard_fail(self):
        for w in ({"pendingClaims": []}, {"news": [{"pending": True}]}, {"claimsQueue": [1]}, {"offers": []}):
            with self.subTest(w=w):
                self.assertIsNone(self.build(w))
    def test_private_names_from_raw(self):
        raw = {"url": "https://www.fantrax.com/fantasy/league/x/home", "trades": {"eddies_pending_private": [{"player": "Odell Thurman"}]}}
        o = bw.build({"week": 7, "news": [{"text": "Thurman looks good."}, {"text": "Lake out."}]}, DATA, NOW, raw=raw)
        self.assertEqual([n["text"] for n in o["news"]], ["Lake out."])
    def test_private_list_never_published(self):
        o = self.build({"news": [{"text": "Lake out."}]})
        self.assertNotIn("Emerson", o)

class Round9b(Base):
    """Fail closed: a pending count >= 1 with an empty/missing private name list stops the refresh."""
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
    def names_file(self, names, counts=None):
        p = self.t / "pending-names.json"; p.write_text(json.dumps({"counts": counts or {}, "names": names})); return p
    RAW1 = {"url": "https://www.fantrax.com/fantasy/league/x/home", "trades": {"eddies_pending_claims_count": 1, "eddies_pending_private": []}}
    RAW0 = {"url": "https://www.fantrax.com/fantasy/league/x/home", "trades": {"eddies_pending_claims_count": 0, "pending_claims_count": None}}
    W = {"week": 7, "news": [{"text": "Martin Emerson looks like a fit."}, {"text": "Lake out."}]}
    def test_count_and_empty_names_fails(self):
        for p in (self.names_file([]), self.t / "missing.json"):
            with self.subTest(p=p), self.assertRaises(wc.PendingError):
                bw.build(dict(self.W), DATA, NOW, raw=self.RAW1, pending_path=str(p))
    def test_count_in_private_file_alone_fails(self):
        with self.assertRaises(wc.PendingError):
            bw.build(dict(self.W), DATA, NOW, raw=self.RAW0, pending_path=str(self.names_file([], {"trades.eddies_pending_claims_count": 2})))
    def test_count_zero_empty_ok(self):
        o = bw.build(dict(self.W), DATA, NOW, raw=self.RAW0, pending_path=str(self.names_file([])))
        self.assertEqual(len(o["news"]), 2)
    def test_count_and_names_drops(self):
        p = self.names_file(["Martin Emerson"], {"trades.eddies_pending_claims_count": 1})
        o = bw.build(dict(self.W), DATA, NOW, raw=self.RAW1, pending_path=str(p))
        self.assertEqual([n["text"] for n in o["news"]], ["Lake out."])
        dumped = json.dumps(o)
        self.assertNotIn(str(p), dumped); self.assertNotIn("pending-names", dumped); self.assertNotIn("Emerson", dumped)
    def test_cli_fails_rc_nonzero_nothing_written(self):
        d = stage(); before = (d / "warroom.json").read_bytes()
        rawf = self.t / "fantrax-raw-2026-10-23-test.json"
        rawf.write_text(json.dumps({**self.RAW1, "scraped": "2026-10-23 6:00 AM PDT", "rosters": {}}))
        env = {**os.environ, "WARROOM_PENDING_NAMES": str(self.t / "missing.json")}
        r = subprocess.run([sys.executable, str(ROOT / "scripts/build_warroom.py"), "--data-dir", str(d), "--raw-glob",
                            str(self.t / "fantrax-raw-*.json"), "--fa-glob", str(self.t / "none-*.json"),
                            "--now", "2026-10-23T07:00"], capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("pending-name list", r.stdout + r.stderr)
        self.assertEqual((d / "warroom.json").read_bytes(), before)
    def test_private_path_not_in_data_or_publish(self):
        for f in (ROOT / "data").rglob("*"):
            if f.is_file():
                self.assertNotIn(b"eddie-private", f.read_bytes(), str(f))
        for f in list((ROOT / ".github").rglob("*")) if (ROOT / ".github").exists() else []:
            if f.is_file():
                self.assertNotIn("eddie-private", f.read_text(errors="ignore"), str(f))
        self.assertFalse(str(Path(bw.PRIVATE_PENDING).resolve()).startswith(str(ROOT)) and "fixtures" not in bw.PRIVATE_PENDING)

class Round10(Base):
    """Bot Ops round 9: every pending item must resolve to a name or the run stops; names file list or dict; short last names."""
    URL = "https://www.fantrax.com/fantasy/league/x/home"
    W = {"week": 7, "waivers": [{"player": "Martin Emerson", "why": "Fits."}], "news": [{"text": "Lake out."}]}
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
    def f(self, content):
        p = self.t / "names.json"; p.write_text(content if isinstance(content, str) else json.dumps(content)); return str(p)
    def run_(self, raw, path=None):
        try:
            return json.dumps(bw.build(json.loads(json.dumps(self.W)), DATA, NOW, raw={"url": self.URL, **raw},
                                       pending_path=path if path is not None else self.f([])))
        except wc.PendingError:
            return None
    def not_published(self, raw, path=None):
        o = self.run_(raw, path)
        self.assertTrue(o is None or "Emerson" not in o, o)
    UNRESOLVED = [
        {"trades": {"eddies_pending_claims_count": 1, "eddies_pending_private": []}},
        {"trades": {"pending_claims_count": 1}}, {"pending_trades_count": 2}, {"x": {"y": {"eddies_pending_offer_count": 1}}},
        {"trades": {"eddies_pending_private": [{"playerId": "abc"}]}}, {"trades": {"eddies_pending_private": [{"bid": 12}]}},
        {"claimsQueue": [{"playerId": "abc"}]}, {"nested": {"claims_queue": [{"bid": 3}]}},
        {"transactions": [{"status": "pending"}]}, {"transactions_since_x": [{"faab_bid": 12}]},
        {"transactions": [{"status": "queued", "date": "2026-10-20"}]},
        {"transactions": [{"status": "completed", "date": "2026-10-28"}]},
        {"transactions": [{"status": "completed", "date": "2026-10-23"}]},
        {"transactions": [{"status": "completed"}]}]
    def test_unresolved_pending_fails_closed(self):
        for raw in self.UNRESOLVED:
            with self.subTest(raw=raw):
                self.assertIsNone(self.run_(raw))
    def test_botops_count1_emerson_waiver_rec_not_published(self):
        self.assertIsNone(self.run_({"trades": {"eddies_pending_claims_count": 1, "eddies_pending_private": []}}))
        self.not_published({"trades": {"eddies_pending_claims_count": 1}}, self.f(["Martin Emerson"]))
        self.not_published({"trades": {"eddies_pending_claims_count": 1}}, self.f({"names": ["Martin Emerson"]}))
        self.not_published({"trades": {"eddies_pending_claims_count": 1}},
                           self.f({"counts": {"trades.eddies_pending_claims_count": 1}, "names": ["Martin Emerson"]}))
    def test_named_queue_and_transactions_resolve_and_drop(self):
        for raw in ({"claimsQueue": [{"player": "Martin Emerson"}]},
                    {"trades": {"eddies_pending_private": [{"add": "Martin Emerson", "drop": "Isaiah Lake", "bid": 12}]}},
                    {"transactions": [{"status": "pending", "action": "add Martin Emerson DB CLE / drop Isaiah Lake DB DAL"}]},
                    {"transactions": [{"status": "processing", "player": "Martin Emerson"}]},
                    {"transactions": [{"status": "completed", "date": "2026-10-28", "add": "Martin Emerson"}]}):
            with self.subTest(raw=raw):
                o = self.run_(raw)
                self.assertIsNotNone(o); self.assertNotIn("Emerson", o)
    def test_own_count_not_covered_by_other_teams_transactions(self):
        self.assertIsNone(self.run_({"trades": {"eddies_pending_claims_count": 1, "eddies_pending_private": []},
                                     "transactions_since_x": [{"team": "Saltese Slamm", "action": "add Adonai Mitchell WR NYJ", "status": "processed"}]}))
    def test_count_more_than_named_items_fails(self):
        self.assertIsNone(self.run_({"trades": {"eddies_pending_claims_count": 2,
                                                "eddies_pending_private": [{"player": "Martin Emerson"}]}}))
    def test_file_missing_or_malformed_with_pending_fails(self):
        raw = {"claimsQueue": [{"player": "Martin Emerson"}]}
        for p in (str(self.t / "nope.json"), self.f("{not json"), self.f({"names": "Martin Emerson"}), self.f(42)):
            with self.subTest(p=p):
                self.assertIsNone(self.run_(raw, p))
    def test_no_pending_file_missing_ok(self):
        o = self.run_({"trades": {"eddies_pending_claims_count": 0, "pending_claims_count": None}}, str(self.t / "nope.json"))
        self.assertIn("Emerson", o)
    def test_completed_past_transaction_not_pending(self):
        o = self.run_({"transactions": [{"status": "Completed", "date": "2026-10-20", "player": "Martin Emerson"}]})
        self.assertIn("Emerson", o)
    def test_short_last_name_whole_word(self):
        o = bw.build({"week": 7, "news": [{"text": "Lee was great."}, {"text": "Leeds won."}, {"text": "Lake out."}]},
                     DATA, NOW, pending=["Ty Lee"])
        self.assertEqual([n["text"] for n in o["news"]], ["Leeds won.", "Lake out."])
    def test_suffix_not_used_as_last_name(self):
        o = bw.build({"week": 7, "news": [{"text": "Jr. day."}, {"text": "Robinson sits."}]}, DATA, NOW, pending=["Brian Robinson Jr."])
        self.assertEqual([n["text"] for n in o["news"]], ["Jr. day."])

class Round10b(Base):
    """Bot Ops round 9b: names must be fresh (same scrape stamp) and >= every pending count / entry."""
    URL = "https://www.fantrax.com/fantasy/league/x/home"
    W = {"week": 7, "waivers": [{"player": "Martin Emerson", "why": "Fits."}], "news": [{"text": "Lake out."}]}
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
    def f(self, names, scraped="2026-10-23 6:00 AM PDT", counts=None):
        p = self.t / "n.json"; p.write_text(json.dumps({"counts": counts or {}, "names": names, "scraped": scraped})); return str(p)
    def run_(self, raw, path):
        try:
            return json.dumps(bw.build(json.loads(json.dumps(self.W)), DATA, NOW,
                                       raw={"url": self.URL, "scraped": "2026-10-23 6:00 AM PDT", **raw}, pending_path=path))
        except wc.PendingError:
            return None
    def test_count2_one_name_fails(self):
        self.assertIsNone(self.run_({"trades": {"eddies_pending_claims_count": 2}}, self.f(["Martin Emerson"])))
    def test_stale_file_other_player_fails(self):
        self.assertIsNone(self.run_({"trades": {"eddies_pending_claims_count": 1}}, self.f(["Odell Thurman"], "2026-10-22 6:00 AM PDT")))
        self.assertIsNone(self.run_({"trades": {"eddies_pending_claims_count": 1}}, self.f(["Odell Thurman"], None)))
    def test_list_form_without_stamp_is_stale_when_raw_has_stamp(self):
        p = self.t / "l.json"; p.write_text(json.dumps(["Martin Emerson"]))
        self.assertIsNone(self.run_({"trades": {"eddies_pending_claims_count": 1}}, str(p)))
    def test_other_teams_names_in_file_do_not_cover_our_count(self):
        p = self.t / "o.json"
        p.write_text(json.dumps({"counts": {}, "names": ["Adonai Mitchell"], "own_names": [], "scraped": "2026-10-23 6:00 AM PDT"}))
        self.assertIsNone(self.run_({"trades": {"eddies_pending_claims_count": 1}}, str(p)))
    def test_fresh_matching_file_drops(self):
        o = self.run_({"trades": {"eddies_pending_claims_count": 1}}, self.f(["Martin Emerson"]))
        self.assertIsNotNone(o); self.assertNotIn("Emerson", o)
    def test_count_field_variants(self):
        for raw in ({"pendingClaims": 1}, {"claims_pending": "1"}, {"numPending": 2}, {"x": {"pending": True}},
                    {"queueSize": 1}, {"claims": 3}, {"trades": {"pending_trades_count": "2"}}):
            with self.subTest(raw=raw):
                self.assertIsNone(self.run_(raw, self.f([])))
    def test_direct_entries_without_count(self):
        for raw in ({"claimsQueue": [{"playerId": "a"}]}, {"x": {"pendingMoves": [{"bid": 3}]}}, {"myBids": [{"id": 1}]},
                    {"offers": [{"id": 2}]}, {"transactions": [{"status": "pending"}]},
                    {"claimsQueue": [{"player": "Cy Queue"}, {"player": "Dee Trans"}]}):
            with self.subTest(raw=raw):
                o = self.run_(raw, self.f([]))
                self.assertTrue(o is None or ("Queue" not in o and "Trans" not in o))
    def test_named_entries_resolve_themselves(self):
        o = self.run_({"claimsQueue": [{"player": "Martin Emerson"}]}, self.f([]))
        self.assertIsNotNone(o); self.assertNotIn("Emerson", o)
    def test_zero_and_none_counts_ok(self):
        o = self.run_({"pendingClaims": 0, "claims_pending": None, "numPending": "0", "x": {"pending": False}}, self.f([]))
        self.assertIn("Emerson", o)

class History(unittest.TestCase):
    def test_count_is_18(self): self.assertEqual(len(HIST_FILES), 18)
add_cases(History, "gate_passes", [f.name for f in HIST_FILES],
          lambda self, n: self.assertEqual(wc.find_pending(json.loads((HIST / n).read_text())), [], n))
add_cases(History, "build_passes", [f.name for f in HIST_FILES],
          lambda self, n: bw.build(json.loads((HIST / n).read_text()), DATA, NOW))

if __name__ == "__main__":
    unittest.main()
