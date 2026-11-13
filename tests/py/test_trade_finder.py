"""ROS trade finder: any Eddies player out, any position in, season-ending stays out."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_trade_finder as tf  # noqa: E402

SEASON_ENDING = {"edgerrin cooper", "tremaine edmunds"}
FULL_TTAB = "Towner Top Aga Bottom"
PENDING_KEY = re.compile(r"pending|bids?$|claims?$", re.I)


def player(name, pos, ros, slot="active"):
    return tf.Player(name, pos, (pos,), "SEA", slot, ros, 1.0, "test", False)


class TradeFinder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = tf.build()
        cls.eddies = list(tf.build.last_eddies)
        cls.rosters = list(tf.build.last_rosters)

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
                self.assertIn(player_row["pos"], tf.INCOMING)

    def test_any_rostered_player_may_be_outgoing(self):
        eligible = self.doc["eddied"]["eligible"]
        self.assertIn("Josh Downs", eligible)
        self.assertIn("Jordyn Brooks", eligible)
        self.assertIn("Cedric Gray", eligible)
        self.assertIn("Jalen Coker", eligible)
        self.assertNotIn("Travis Etienne", eligible)
        src = (ROOT / "scripts" / "build_trade_finder.py").read_text()
        self.assertNotIn("HOLDS", src)
        self.assertNotIn("LB_OUT", src)
        self.assertNotIn("WR_OUT", src)
        for idea in self.doc["ideas"]:
            for player_row in idea["give"]:
                self.assertIn(player_row["name"], eligible)
        downs = tf.fit_score(
            [player("Josh Downs", "WR", 64, "reserve")],
            [player("Spare Back", "RB", 140)],
            eddies_delta=6,
            partner_delta=-3,
            healthy_delta=2,
            playable={pos: 4 for pos in tf.INCOMING},
            usable={pos: 4 for pos in tf.INCOMING},
            block_get=False,
            block_give=False,
            surplus_piece=True,
            starts_for_them=True,
            gives_starter=False,
        )
        self.assertIsInstance(downs, int)

    def test_every_idea_gains_value_and_leaves_starters_filled(self):
        for idea in self.doc["ideas"]:
            self.assertGreater(idea["valueDelta"], 0)
            team = next(row for row in self.rosters if row["id"] == idea["partnerId"])
            get = next(person for person in team["players"] if person.name == idea["get"][0]["name"])
            give_names = {row["name"] for row in idea["give"]}
            after = [person for person in self.eddies if person.name not in give_names] + [get]
            self.assertEqual(tf.starter_holes(after), [], idea["partner"])

    def test_season_ending_never_appear(self):
        for idea in self.doc["ideas"]:
            for side in ("give", "get"):
                for player_row in idea[side]:
                    self.assertNotIn(player_row["name"].lower(), SEASON_ENDING)

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

    def test_starter_hole_uses_the_needs_count(self):
        room = [
            player("QB", "QB", 180),
            player("RB1", "RB", 110),
            player("RB2", "RB", 100),
            player("WR1", "WR", 130),
            player("WR2", "WR", 90),
            player("WR3", "WR", 80),
            player("TE", "TE", 120),
            player("DL", "DL", 170),
            player("LB", "LB", 160),
            player("DB1", "DB", 140),
            player("DB2", "DB", 130),
            player("DB3", "DB", 125),
        ]
        self.assertEqual(tf.starter_holes(room), [])
        traded_dl = [p for p in room if p.name != "DL"] + [player("New RB", "RB", 150)]
        self.assertIn("DL", tf.starter_holes(traded_dl))
        traded_one_rb = [p for p in room if p.name != "RB1"] + [player("New WR", "WR", 140)]
        self.assertEqual(tf.starter_holes(traded_one_rb), [])

    def test_every_position_and_trade_shape_can_score(self):
        self.assertEqual(tf.INCOMING, ("QB", "RB", "WR", "TE", "DL", "LB", "DB"))
        full = {pos: 4 for pos in tf.INCOMING}

        def score(give, get, delta=8):
            return tf.fit_score(
                give, [get],
                eddies_delta=delta,
                partner_delta=-4,
                healthy_delta=2,
                playable=full,
                usable=full,
                block_get=False,
                block_give=False,
                surplus_piece=True,
                starts_for_them=True,
                gives_starter=False,
            )

        offense = score([player("Wideout", "WR", 90)], player("Other WR", "WR", 140))
        idp = score([player("Backer", "LB", 130)], player("Other LB", "LB", 150))
        cross = score(
            [player("Wideout", "WR", 90), player("Backer", "LB", 130)],
            player("Lineman", "DL", 150),
        )
        quarterback = score([player("Signal", "QB", 170)], player("Other QB", "QB", 180))
        tight = score([player("End", "TE", 100)], player("Other TE", "TE", 120))
        for deal in (offense, idp, cross, quarterback, tight):
            self.assertIsInstance(deal, int)
        self.assertIsNone(score([player("Wideout", "WR", 90)], player("Other WR", "WR", 140), delta=0))

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
