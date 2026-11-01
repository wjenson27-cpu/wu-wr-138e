#!/usr/bin/env python3
"""Lock the Robot lineup for one week.

Refuses to edit a lineup once it is locked, and refuses to write a lock at or
after the first kickoff time in the input.

Usage:
  python3 scripts/lock_robot_lineup.py --input lock.json [--data data/robot-vs-bill] [--now ISO]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import robot_vs_bill as rvb  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lock the Robot lineup before first kickoff.")
    ap.add_argument("--input", required=True, help="JSON file with week, firstKickoff, and lineup")
    ap.add_argument("--data", default=str(rvb.DATA_DIR), help="Directory of week files")
    ap.add_argument("--now", default=None, help="Clock override. A value with no offset is read as PT.")
    args = ap.parse_args(argv)
    try:
        doc = json.loads(Path(args.input).read_text())
        path = rvb.lock_lineup(args.data, doc, now=args.now)
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
