# Robot vs. The Eddies

`robot-vs-bill.html` is the phone scoreboard for one club: **Eagleridge Eddie's**. Each week the Robot locks a start/sit lineup before the first kickoff. After the games, the week file is scored against the club's actual Fantrax lineup. The board starts at **Week 9 (Nov 5–9 2026)**. There is no history before that.

The page is not linked from the War Room home page. It reads `data/robot-vs-bill/season.json` and the week files that tally lists. It does not scrape. Times are Pacific and labeled **PT**. Write timestamps as ISO 8601 with a numeric offset (`-08:00` after the fall change, `-07:00` while daylight time is in effect).

Sides on the page are **Robot** and **Eddies**. Do not add a personal name, an owner field, a bid, a claim, or a trade to these files. Points stay `null` until the week status is `final`.

The JSON Schema is `data/robot-vs-bill/schema.json`.

## Season tally

`data/robot-vs-bill/season.json` is rebuilt from the week files. It is the running record.

| Field | What it is |
| --- | --- |
| `club` | `Eagleridge Eddie's`. |
| `sides` | Display names: Robot and Eddies. |
| `firstWeek` | `9`. Earlier weeks are refused. |
| `record` | Robot wins, losses, and ties against Eddies. `label` is `W-L-T`, such as `1-1-0`. Pending weeks are not counted. |
| `points.robot` / `points.eddies` | Cumulative fantasy points from final weeks only. |
| `points.margin` | Cumulative Robot points minus cumulative Eddies points. |
| `weeks` | One summary per week file, in week order. `decisions` is copied from that week. |

## Week file

`data/robot-vs-bill/wNN.json` (for example `w09.json`).

```json
{
  "schemaVersion": 1,
  "season": 2026,
  "week": 9,
  "window": { "start": "2026-11-05", "end": "2026-11-09", "label": "Nov 5–9" },
  "status": "pending",
  "robotLockedAt": null,
  "firstKickoff": null,
  "robot": [],
  "actual": [],
  "totals": { "robot": null, "eddies": null },
  "margin": null,
  "result": null,
  "winner": null,
  "decisions": []
}
```

| Field | What it is |
| --- | --- |
| `status` | `pending` or `final`. |
| `robotLockedAt` | When the Robot lineup was locked, in PT. `null` means not locked yet. |
| `firstKickoff` | First kickoff for that week, in PT. The lock is refused at or after this instant. |
| `robot` / `actual` | Fourteen starters in canonical slot order. Empty until that side exists. |
| `totals` | Sum of that side. `null` until `final`. |
| `margin` | Robot total minus Eddies total. `null` until `final`. |
| `result` | `W`, `L`, or `T` from the Robot side. `null` until `final`. |
| `winner` | `Robot`, `Eddies`, or `tie`. |
| `decisions` | Slots where the two sides started different players, plus the point swing. |

Lineup order is fixed:

`QB, RB, WR, TE, FLEX, FLEX, FLEX, DL, LB, DB, DB, IDP, IDP, IDP`

FLEX is RB, WR, or TE. IDP is DL, LB, or DB. A player can appear once per lineup.

Each starter:

| Field | What it is |
| --- | --- |
| `slot` | The lineup slot. |
| `player` | Name. |
| `pos` | QB, RB, WR, TE, DL, LB, or DB. |
| `team` | NFL abbreviation. |
| `points` | Fantasy points, or `null` until the week is final. |

## Decisions that differed

A decision is a slot index where the two lineups list different players. `swing` is the Robot player's points minus the Eddies player's points at that slot. Positive means the Robot's starter scored more. `swing` is `null` until the week is final. The same player in both lineups is not a decision, including when that player is on a bye.

## Scoring

- A player who is in both lineups is scored once, and that number is added to each side's total.
- A player listed under `bye` or `inactive` scores `0` on every side that started them, even if the points input has another number.
- Anyone else who started needs a number in `points` when status is `final`.
- Status `pending` records the Eddies lineup and leaves every point `null`.
- The season tally adds final weeks only. Scoring the same week again replaces that week; it does not add it twice.

## Lock

`scripts/lock_robot_lineup.py` reads a JSON file:

```json
{
  "week": 9,
  "firstKickoff": "2026-11-05T17:15:00-08:00",
  "lineup": [
    { "slot": "QB", "player": "Player A", "pos": "QB", "team": "CIN" }
  ]
}
```

The lineup must be all 14 slots. `--now` sets the lock clock (no offset means PT). The script writes `robotLockedAt` and will not invent a lineup for any week before 9.

Once `robotLockedAt` is set:

- A different lineup is refused, before or after kickoff.
- A different first kickoff is refused.
- Any overwrite at or after the stored kickoff is refused, including an identical lineup.
- An identical lineup submitted again before kickoff leaves the original timestamp in place.

A first lock at or after kickoff is also refused, and the week file is left untouched.

## Score

`scripts/score_robot_vs_bill.py` reads:

```json
{
  "week": 9,
  "status": "final",
  "actual": [
    { "slot": "QB", "player": "Player A", "pos": "QB", "team": "CIN" }
  ],
  "points": { "Player A": 22 },
  "bye": [],
  "inactive": []
}
```

The Robot lineup must already be locked. This script does not change those picks. It rewrites the week file's Eddies lineup, points, totals, result, and decisions, then rebuilds `season.json`.

## Commands

```bash
python3 scripts/lock_robot_lineup.py --input lock.json --now 2026-11-05T09:30:00-08:00
python3 scripts/score_robot_vs_bill.py --input score.json
```

Exit `2` means the lock was refused. Exit `1` means the input was not usable. The live week file ships unlocked and empty. Sample lineups belong in `tests/fixtures/robot-vs-bill/` only.
