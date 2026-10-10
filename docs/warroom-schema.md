# Eddie's weekly plan

`data/warroom.json` is the private plan for the in-season War Room. Eddie rewrites this file each day. The page reads it as-is. Live standings, the Eddies roster, FAAB, and scores still come from the league files. This file is the plan on top of those.

Leave `"sample": true` until the plan is real. The page then shows a sample banner. Set `"sample": false` when you replace the placeholder.

## When it was written

`asOf` is the time the plan was written, in Pacific time, like `2026-10-09T16:05:00-07:00`. The header treats the plan as stale when this time, or the roster file's time, is more than 24 hours old.

`freshness` is the same idea per source. Use `null` when that source has nothing new.

| Field | What it is |
| --- | --- |
| `freshness.plan` | When this file was written |
| `freshness.roster` | When the roster was last checked |
| `freshness.scores` | When a live score was last seen, or `null` |
| `freshness.waivers` | When the bid sheet was written |
| `freshness.news` | When the wire was written |

## The week

`season` is the year, `week` is the Fantrax week (Thursday through Wednesday, Pacific time). If `week` is missing, the page counts forward from Thursday, September 10, 2026.

`opponent` is who the Eddies play.

| Field | What it is |
| --- | --- |
| `opponent.teamId` | League id, such as `doubtpfizer` |
| `opponent.name` | Club name. The live standings fill the record. |

`lockTimes` is a list. Each item has `label` (Sunday, Monday) and `at` (a Pacific time).

## Lineup

`lineup` is one row per recommendation.

| Field | What it is |
| --- | --- |
| `slot` | QB, RB, WR, TE, FLEX, DL, LB, DB, IDP, or BN |
| `player` | Name, spelled the way the roster spells it |
| `pos` | QB, RB, WR, TE, DL, LB, or DB |
| `nflTeam` | NFL abbreviation |
| `verdict` | START, SIT, SWAP, or WATCH |
| `reason` | One line |
| `injury` | Short tag such as Q, O, or blank |
| `practice` | Short practice note, or blank |

## Injury watch and byes

`injuryWatch` rows have `player`, `tag`, `practice`, and `note`.

`byes` covers the next two weeks. Each item has `week` and `players`. A player has `player`, `pos`, and `nflTeam`. Use an empty `players` list when nobody is off.

## Bid sheet

`waivers` is the ordered bid list.

| Field | What it is |
| --- | --- |
| `rank` | 1 is the first claim |
| `player` | Name |
| `pos` | Position |
| `nflTeam` | NFL team |
| `why` | One or two sentences |
| `stats` | Recent league-scoring line, in words |
| `faabMin` | Low end of the range, dollars |
| `faabMax` | High end of the range, dollars |
| `bid` | The bid to send |
| `drop` | Who to drop |
| `tag` | MUST, LIKE, or DART |

`drops` is the cut list, worst first. Each row has `rank`, `player`, `pos`, and `reason`.

`trades` is a short list of ideas, not offers. Each one has `with` (the other club's name), `give` (names we send), `get` (names we ask for), and `why`.

## IDP and the wire

`idp` is the green-dot list. Each row has `nflTeam`, `greenDot` (the linebacker), and `notes`.

`boxSafety` rows have `player`, `nflTeam`, and `note`.

`news` is newest first. Each item has `source`, `time` (Pacific time), and `text`.
