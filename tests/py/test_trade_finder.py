"""ROS trade finder: ideas only, keeps stay, season-ending players stay out."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_trade_finder as tf  # noqa: E402

KEEPS = {"jordyn brooks", "cedric gray"}
SEASON_ENDING = {"edgerrin cooper", "tremaine edmunds"}
FULL_TTAB = "Towner Top Aga Bottom"


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
        self.assertGreaterEqual(len(ideas), 5)
        self.assertLessEqual(len(ideas), 12)
        self.assertEqual([i["rank"] for i in ideas], list(range(1, len(ideas) + 1)))
        self.assertTrue(self.doc["recommendOnly"])

    def test_each_idea_has_the_board_fields(self):
        for idea in self.doc["ideas"]:
            for key in ("partner", "give", "get", "valueDelta", "whyItWorksForThem", "fitScore"):
                self.assertIn(key, idea)
            self.assertTrue(idea["give"] and idea["get"])
            self.assertIsInstance(idea["fitScore"], int)
            self.assertGreaterEqual(idea["fitScore"], 0)
            self.assertLessEqual(idea["fitScore"], 100)
            self.assertIsInstance(idea["valueDelta"], (int, float))
            self.assertGreater(idea["valueDelta"], 0)
            self.assertTrue(idea["whyItWorksForThem"])

    def test_keeps_and_season_ending_never_appear(self):
        for idea in self.doc["ideas"]:
            for side in ("give", "get"):
                for player in idea[side]:
                    name = player["name"].lower()
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

    def test_written_file_matches_the_builder(self):
        path = ROOT / "data" / "trade-finder.json"
        self.assertTrue(path.exists(), "run scripts/build_trade_finder.py")
        saved = json.loads(path.read_text())
        self.assertEqual(
            [(i["partner"], [p["name"] for p in i["give"]], [p["name"] for p in i["get"]]) for i in saved["ideas"]],
            [(i["partner"], [p["name"] for p in i["give"]], [p["name"] for p in i["get"]]) for i in self.doc["ideas"]],
        )


if __name__ == "__main__":
    unittest.main()
