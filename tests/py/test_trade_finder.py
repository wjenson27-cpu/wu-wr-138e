"""ROS trade finder: ideas only, keeps stay, season-ending players stay out."""
import json
import re
import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_trade_finder as tf  # noqa: E402

KEEPS = {"jordyn brooks", "cedric gray"}
SEASON_ENDING = {"edgerrin cooper", "tremaine edmunds"}
FULL_TTAB = "Towner Top Aga Bottom"
PENDING_KEY = re.compile(r"pending|bids?$|claims?$", re.I)


def player(name, pos, ros, slot="active"):
    return tf.Player(name, pos, (pos,), "SEA", slot, ros, 1.0, "test", False)


class TradeFinder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = tf.build()

    def test_display_name_is_ttab(self):
        self.assertEqual(tf.display_name(FULL_TTAB), "TTAB")
        self.assertEqual(tf.display_name("  towner top aga bottom "), "TTAB")
        self.assertEqual(tf.display_name("Valley Old Goats"), "Valley Old Goats")

    def test_ideas_are_a_short_ranked_list(self):
        ideas = self.doc["ideas"]
        page = (ROOT / "trade-finder.html").read_text()
        self.assertLessEqual(len(ideas), 12)
        self.assertIn("No ideas on this roster", page)
        self.assertIn("!ideas.length", page)
        self.assertTrue(self.doc["recommendOnly"])
        if not ideas:
            return
        self.assertGreaterEqual(len(ideas), 1)
        self.assertEqual([i["rank"] for i in ideas], list(range(1, len(ideas) + 1)))

    def test_each_idea_has_the_board_fields(self):
        for idea in self.doc["ideas"]:
            for key in ("partner", "give", "get", "valueDelta", "partnerDelta", "whyItWorksForThem", "fitScore"):
                self.assertIn(key, idea)
            self.assertTrue(idea["give"] and idea["get"])
            self.assertIsInstance(idea["fitScore"], int)
            self.assertGreaterEqual(idea["fitScore"], 0)
            self.assertLessEqual(idea["fitScore"], 100)
            self.assertIsInstance(idea["valueDelta"], (int, float))
            self.assertGreater(idea["valueDelta"], 0)
            self.assertIsInstance(idea["partnerDelta"], (int, float))
            self.assertTrue(idea["whyItWorksForThem"])
            for player_row in idea["get"]:
                self.assertIn(player_row["pos"], ("RB", "DL", "LB", "DB"))

    def test_keeps_and_season_ending_never_appear(self):
        for idea in self.doc["ideas"]:
            for side in ("give", "get"):
                for player_row in idea[side]:
                    name = player_row["name"].lower()
                    self.assertNotIn(name, SEASON_ENDING)
                    if side == "give":
                        self.assertNotIn(name, KEEPS)

    def test_ttab_is_never_shown_under_the_long_name(self):
        for idea in self.doc["ideas"]:
            self.assertNotEqual(idea["partner"], FULL_TTAB)
        for row in self.doc["leagueDepth"]:
            self.assertNotEqual(row["team"], FULL_TTAB)
        labels = {row["team"] for row in self.doc["leagueDepth"]}
        self.assertIn("TTAB", labels)

    def test_script_does_not_send_or_call_out(self):
        src = (ROOT / "scripts" / "build_trade_finder.py").read_text()
        page = (ROOT / "trade-finder.html").read_text()
        self.assertNotIn("urllib", src)
        self.assertNotIn("fantrax.com", src.lower())
        self.assertNotIn("fantrax.com", page.lower())
        for idea in self.doc["ideas"]:
            self.assertNotIn("status", idea)

    def test_roster_stamp_comes_from_the_scrape(self):
        scrape = json.loads(tf.DEFAULT_SCRAPE.read_text())
        self.assertEqual(self.doc["asOfRoster"], scrape["scraped"])
        self.assertIn("2026-11-12", self.doc["asOfRoster"])
        self.assertEqual(
            self.doc["sources"]["rosters"],
            "data/sources/fantrax-raw-2026-11-12-pm-normalized.json",
        )
        self.assertEqual(self.doc["sources"]["scraped"], scrape["scraped"])
        self.assertTrue(self.doc["generatedAt"])
        self.assertNotEqual(self.doc["generatedAt"], "2026-10-30T08:59:00-07:00")

    def test_needs_line_is_derived_from_usable_counts(self):
        karlaftis = player("George Karlaftis", "DL", 171)
        hall = player("Breece Hall", "RB", 90)
        charb = player("Zach Charbonnet", "RB", 105)
        usable = {"QB": 0, "RB": 2, "WR": 0, "TE": 0, "DL": 1, "LB": 0, "DB": 0}
        playable = {"QB": 0, "RB": 2, "WR": 0, "TE": 0, "DL": 1, "LB": 0, "DB": 0}
        text = tf.needs_line([karlaftis, hall, charb], usable, playable)
        self.assertIn("2 usable RB", text)
        self.assertIn("Breece Hall", text)
        self.assertIn("Zach Charbonnet", text)
        self.assertIn("1 usable DL", text)
        self.assertIn("George Karlaftis", text)
        self.assertIn("starting", text)
        self.assertNotIn("only healthy back", text)
        self.assertNotIn("ACL", text)

        ed = self.doc["eddied"]
        needs = ed["needs"]
        self.assertIn(f"{ed['usable']['RB']} usable RB", needs)
        self.assertIn(f"{ed['usable']['DL']} usable DL", needs)
        self.assertEqual(ed["usable"]["RB"], 2)
        self.assertEqual(ed["usable"]["DL"], 1)
        self.assertIn("Karlaftis", needs)
        self.assertIn("Charbonnet", needs)
        self.assertNotIn("Hall is the only healthy back", needs)
        self.assertNotIn("ACL", needs)
        self.assertIn("starting", needs)

    def test_missing_surplus_names_are_skipped(self):
        by_name = {"Jalen Coker": player("Jalen Coker", "WR", 98)}
        with self.assertWarns(RuntimeWarning) as caught:
            found = tf.resolve_surplus(("Jalen Coker", "Kendrick Bourne", "Tyrice Knight"), by_name)
        self.assertEqual([p.name for p in found], ["Jalen Coker"])
        message = str(caught.warning)
        self.assertIn("Kendrick Bourne", message)
        self.assertIn("Tyrice Knight", message)
        with warnings.catch_warnings(record=True) as caught_build:
            warnings.simplefilter("always")
            doc = tf.build(
                lb_out=tf.LB_OUT + ("Tyrice Knight",),
                wr_out=tf.WR_OUT + ("Kendrick Bourne",),
            )
        text = " ".join(str(item.message) for item in caught_build)
        self.assertIn("Tyrice Knight", text)
        self.assertIn("Kendrick Bourne", text)
        self.assertNotIn("Tyrice Knight", doc["eddied"]["surplus"]["LB"])
        self.assertNotIn("Kendrick Bourne", doc["eddied"]["surplus"]["WR"])
        self.assertIn("Jalen Coker", doc["eddied"]["surplus"]["WR"])
        self.assertNotIn("Tyrice Knight", doc["eddied"]["surplus"]["LB"])

    def test_josh_downs_is_never_outgoing(self):
        for idea in self.doc["ideas"]:
            for player_row in idea["give"]:
                self.assertNotEqual(player_row["name"], "Josh Downs")
        for names in self.doc["eddied"]["surplus"].values():
            self.assertNotIn("Josh Downs", names)
        self.assertIn("Josh Downs", self.doc["holds"])
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            doc = tf.build(wr_out=("Josh Downs", "Jalen Coker"))
        self.assertNotIn("Josh Downs", doc["eddied"]["surplus"]["WR"])
        self.assertIn("Jalen Coker", doc["eddied"]["surplus"]["WR"])
        for idea in doc["ideas"]:
            self.assertNotIn("Josh Downs", [p["name"] for p in idea["give"]])

    def test_lb_and_db_incoming_ideas_appear(self):
        positions = {p["pos"] for idea in self.doc["ideas"] for p in idea["get"]}
        self.assertIn("LB", positions)
        self.assertTrue(positions & {"LB", "DB"})
        room = [player(f"DB {i}", "DB", 200 - (i * 10)) for i in range(4)]
        spare = tf.spare_candidates(room, "DB")
        self.assertTrue(spare)
        self.assertNotEqual(spare[0].name, "DB 0")
        incoming = tf.incoming_players(room + [player(f"LB {i}", "LB", 180 - i) for i in range(4)])
        self.assertTrue(any(p.pos == "DB" for p in incoming))
        self.assertTrue(any(p.pos == "LB" for p in incoming))
        score = tf.fit_score(
            [player("Trenton Simpson", "LB", 130, "reserve")],
            [spare[0]],
            eddies_delta=12,
            partner_delta=-6,
            healthy_delta=8,
            playable={"DB": 4, "LB": 4, "WR": 4, "RB": 4, "DL": 4},
            usable={"DB": 4, "LB": 4, "WR": 4, "RB": 4, "DL": 4},
            block_get=False,
            block_give=False,
            surplus_piece=True,
            starts_for_them=True,
            gives_starter=False,
            our_usable={"RB": 2, "WR": 1, "DL": 1, "LB": 4, "DB": 2},
            our_playable={"RB": 2, "WR": 3, "DL": 1, "LB": 4, "DB": 3},
        )
        self.assertIsInstance(score, int)
        offense_for_offense = tf.fit_score(
            [player("Jalen Coker", "WR", 98, "reserve")],
            [player("Spare Back", "RB", 140)],
            eddies_delta=10,
            partner_delta=-4,
            healthy_delta=6,
            playable={"RB": 4, "WR": 2, "DL": 3, "LB": 3, "DB": 3},
            usable={"RB": 4, "WR": 2, "DL": 3, "LB": 3, "DB": 3},
            block_get=False,
            block_give=False,
            surplus_piece=True,
            starts_for_them=True,
            gives_starter=False,
            our_usable={"RB": 2, "WR": 1, "DL": 1, "LB": 4, "DB": 3},
            our_playable={"WR": 3},
        )
        self.assertIsInstance(offense_for_offense, int)
        offense_for_idp = tf.fit_score(
            [player("Trenton Simpson", "LB", 130, "reserve"), player("Jalen Coker", "WR", 98, "reserve")],
            [spare[0]],
            eddies_delta=9,
            partner_delta=-5,
            healthy_delta=4,
            playable={"DB": 4, "LB": 2, "WR": 4, "RB": 3, "DL": 3},
            usable={"DB": 4, "LB": 2, "WR": 3, "RB": 3, "DL": 3},
            block_get=False,
            block_give=False,
            surplus_piece=True,
            starts_for_them=True,
            gives_starter=False,
            our_usable={"RB": 2, "WR": 1, "DL": 1, "LB": 4, "DB": 2},
            our_playable={"WR": 3},
        )
        self.assertIsInstance(offense_for_idp, int)

    def test_finder_does_not_publish_pending_bids_or_trades(self):
        blob = json.dumps(self.doc).lower()
        page = (ROOT / "trade-finder.html").read_text().lower()
        for phrase in ("pending trade", "pending bid", "pending claim", "eddies_pending"):
            self.assertNotIn(phrase, blob)
            self.assertNotIn(phrase, page)
        keys = []

        def walk(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    keys.append(str(key))
                    walk(value)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value)

        walk(self.doc)
        for key in keys:
            self.assertIsNone(PENDING_KEY.search(key), key)

    def test_written_file_matches_the_builder(self):
        path = ROOT / "data" / "trade-finder.json"
        self.assertTrue(path.exists(), "run scripts/build_trade_finder.py")
        saved = json.loads(path.read_text())
        self.assertEqual(saved["asOfRoster"], self.doc["asOfRoster"])
        self.assertEqual(saved["week"], self.doc["week"])
        self.assertEqual(saved["eddied"]["needs"], self.doc["eddied"]["needs"])
        self.assertEqual(
            [(i["partner"], [p["name"] for p in i["give"]], [p["name"] for p in i["get"]]) for i in saved["ideas"]],
            [(i["partner"], [p["name"] for p in i["give"]], [p["name"] for p in i["get"]]) for i in self.doc["ideas"]],
        )


if __name__ == "__main__":
    unittest.main()
