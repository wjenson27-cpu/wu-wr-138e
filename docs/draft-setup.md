# Setting up the draft board

Open `draft.html` from the Archive tab, or go there directly. The 2026 board is already loaded. Your phone keeps any edits you make. The file in the repo does not change until you export and replace it.

## What you can do on draft day

The top bar shows the pick on the clock and how long until your pick. Your target names sit in the chips. When it is your turn the bar turns green and the eagle calls, unless Sound is set to Muted. Test plays the call once.

Board is the big list. Filter by position, hide players who are already drafted, and sort by rank, projection, or value over replacement. Likes is the short list. IDP is the green-dot sheet. LBs, RBs, WRs, DBs, QB, and TE are the position sheets. Live is the snake, with Undo and Reset. Reset asks before it clears the draft.

Tap Draft, then confirm, to give the player to the club on the clock. Undo takes back the last pick. A refresh keeps the draft. Reset starts the draft over and does not erase your rankings.

## Changing the board

Tap Edit. On any player you can set the tier, the verdict, the note, and the star. The star puts him on Likes. Remove drops him from the board.

Setup has Add a player. Type the name, the position (QB, RB, WR, TE, LB, DL, or DB), and the NFL team.

Draft order is the Round 1 list, top to bottom. Even rounds reverse. Up and Down move a club. Your slot is the box that moves your own club to that spot in Round 1. Rounds is how long the draft is. "Straight snake, no traded picks" ignores the 2026 pick swaps. Leave that off if you are replaying 2026. Bill's 2026 picks follow the traded-pick list from draft day.

The phone keeps the board and the live draft separately. Reload the file throws away phone edits and reads `data/draft/2026.json` again. Export season JSON downloads the board as it sits on the phone. Import a season file loads that download, including a new year. The season menu lists every year you have imported.

## Next year's board

1. In Setup, download the CSV template (`data/draft/rankings-template.csv`).
2. Fill one row per player. Delete the example row, or leave the words "Delete this example" in the note so that row is skipped.
3. In Setup, import the CSV. That replaces the big board and rebuilds each position list.
4. Fix tiers, notes, verdicts, and stars with Edit.
5. Set the clubs, the round count, and your slot.
6. Export the season JSON and save it as `data/draft/2027.json`. Add `2027` to the list in `data/draft/index.json`.

## CSV columns

Required to be useful: `name`, `pos`, `team`.

| Column | What to put |
| --- | --- |
| `name` | Player |
| `pos` | QB, RB, WR, TE, LB, DL, or DB |
| `team` | NFL abbreviation |
| `rank` | Your order. Blank rows are numbered in file order. |
| `tier` | T1 through T9 |
| `verdict` | SMASH, LIKE, CAUTION, WATCH, SLEEPER, or FADE |
| `like` | yes, y, true, 1, or star to star him |
| `note` | One line. A note that says "Delete this example" is skipped. |
| `pts` | Projected points. Ignored when you fill any stat column. |
| `y25` | Last year's points, optional |
| `role` | Short role, optional |
| `window` | When you want him, optional |

Stat columns, all optional: `passYds`, `passTd`, `interceptions`, `rushYds`, `rushTd`, `carries`, `receptions`, `recYds`, `recTd`, `teFirstDowns`, `solo`, `assisted`, `sacks`, `tfl`, `pd`, `defInt`.

If any stat cell is filled in, the board scores that line with this league's rules (tight end premium and IDP) and ignores `pts`. The scoring table is `data/scoring.json`. Value over replacement is points minus the last starter at that position, using the real lineup: one QB, one RB, one WR, one TE, three RB/WR/TE, one DL, one LB, two DB, and three IDP. Flex spots go to whoever scores more.

## 2026 file

`data/draft/2026.json` holds the clubs, the traded picks, the board, the likes, the position lists, and the green-dot sheet. `data/draft/index.json` lists the years the menu can open.
