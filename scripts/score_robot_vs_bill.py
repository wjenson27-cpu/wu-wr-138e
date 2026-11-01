#!/usr/bin/env python3
"""Score the Robot lineup against the Eddies lineup and refresh the season tally.

Points stay null while status is pending. A final week stores per-player points.
A player in both lineups counts once on each side. Bye and inactive players score 0.
The Robot lineup itself is never edited here.

Usage:
  python3 scripts/score_robot_vs_bill.py --input score.json [--data data/robot-vs-bill]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import robot_vs_bill as rvb  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Score one week and update the season tally.")
    ap.add_argument("--input", required=True, help="JSON file with week, status, actual lineup, and points")
    ap.add_argument("--data", default=str(rvb.DATA_DIR), help="Directory of week files")
    args = ap.parse_args(argv)
    try:
        doc = json.loads(Path(args.input).read_text())
        path = rvb.score_week(args.data, doc)
    except rvb.Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (rvb.InputError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
