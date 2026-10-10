# Weekly rankings

The Rankings tab reads `data/rankings/latest.json`, then the week file that pointer names. Both files are produced by `node scripts/build_rankings.js`. A GitHub Action runs that command and commits the output.

Set `SEASON` and `WEEK` to build a specific board. With those unset, the script uses the Fantrax week in Pacific time (Thursday through Wednesday, week 1 starting September 10, 2026). January and February still count as the previous season.

## When it refreshes

The action is `.github/workflows/rankings.yml`. It can be run by hand. On a schedule it runs:

- Tuesday 11:00 PM PT
- Thursday 8:00 AM PT
- Saturday 11:00 PM PT
- Sunday 7:00 AM PT

Those clocks are set in UTC for daylight time. After the first Sunday in November they fire an hour earlier (10 PM, 7 AM, 10 PM, and 6 AM PT) until March. The Tuesday run is still the current Fantrax week. Thursday morning is the first scheduled run of the new week. To build a different week before Thursday, run the action by hand and pass `week`.

The action uses the built-in `GITHUB_TOKEN` with `contents: write`. It commits only `data/rankings/` and pushes as `github-actions[bot]`. It does not run on every push.

## Sources

Points are never taken from a source's own PPR or standard total. Where a stat line exists, `js/scoring.js` rescores it with `data/scoring.json` (TE premium, TE first downs, IDP). Consensus points are an equal-weight average of the projection lines (Sleeper and ESPN). Last 3 is not averaged into that number, and it is not used when those projections are missing. It widens the floor and the ceiling when a projection exists. A player with nothing but last-3 actuals, including anyone on a bye, has no consensus points.

| Source | What it contributes | If it fails |
| --- | --- | --- |
| Sleeper player list | Name, team, position, injury | The board can still be built from ESPN names |
| Sleeper weekly projections | Stat line, offense and IDP, rescored | That column is blank |
| Sleeper actuals, earlier weeks | "Last 3" points: the mean of up to the last three weeks the player actually played. A week he did not play is not a zero | Last 3 is blank, and matchup grades are missing if the stats never arrive |
| ESPN public fantasy projections | Offensive stat line, rescored. Their public board has no IDP, so IDP rows have no ESPN points. Receiving first downs are not in this feed, so the TE first-down bonus is applied only when Sleeper has it | ESPN points are blank |
| FantasyPros weekly ECR | Positional rank, plus the experts' low and high rank. The pages under `/nfl/rankings/` are fetched with a descriptive user agent and at least 5.5 seconds between pages. Their points column is ignored | Ranks from FantasyPros are blank. If the site blocks the agent, the source is dropped |
| ESPN scoreboard | Opponent, home or away, dome, neutral site, DraftKings spread and total | Opponent, Vegas, and weather are blank |
| Open-Meteo | Outdoor temperature, wind, and rain chance at the venue for kickoff. Domes say "Dome". SoFi and Allegiant are treated as domes because the scoreboard marks those roofs as outdoor. Two games at the same stadium share one forecast | Weather says "Outdoor" or the source is marked missing |

These were not used:

- FantasyPros `/api/`, `/ajax/`, and `/nfl/ranker/` are disallowed by their robots.txt.
- Anything that needs a login.
- Kickers and team defenses. This league does not start them.
- A source's own fantasy-point total.

Sleeper's weekly stats do not name the opponent. Matchup history joins those stats to the player's current Sleeper team, then to the ESPN schedule. A player who changed teams is scored against the new team's past games. That limit is in the matchup, not hidden.

Vegas comes from the ESPN scoreboard odds. The stored spread is the player's own spread (negative means his team is favored). Implied points are `(total − spread) / 2` for the home team and `(total + spread) / 2` for the away team, using the home spread before it is flipped. A finished game often has no odds line left; those players have no Vegas row.

## Matchup grade

Offense: average Wheels Up points the opponent has allowed to that position in earlier weeks. A higher number is an easier matchup.

IDP: the opponent's offense, per game, from earlier weeks. The grade uses plays and sacks allowed for defensive line (`sacks × 8 + plays × 0.15`), plays for linebackers, and pass attempts for defensive backs. A busier offense grades higher. The row still shows plays, pass attempts, and sacks allowed.

Grades need at least four clubs. Place is 1 plus the number of clubs with a higher value. The letter is A at the 80th percentile or better, then B, C, D, and F below the 20th.

## Consensus and splits

Inside one position, players with a points consensus are ranked by those points (ties broken by name). Players who only have a FantasyPros rank or only last-3 actuals are listed after them.

Each stat source also has its own positional rank, from that source's Wheels Up points. The FantasyPros rank is the rank they published.

A player is flagged as a split when Sleeper and ESPN disagree by 6 or more points, or when two of Sleeper, ESPN, and FantasyPros disagree by 12 or more ranks (8 or more at quarterback) and the best of those ranks is inside the startable group (top 24 at quarterback and tight end, top 36 elsewhere). Last 3 is left out of that test. A hot or cold stretch still shows up in the floor-to-ceiling range.

A player is kept when any point source is above 1, or FantasyPros ranks him, or he is on a saved league roster.

## Availability

The build stamps each player from the roster snapshots in `data/hq/rosters/`: `eddies`, `other` with the club name, or `fa`. The tab recomputes this from the live HQ rosters when those load. Someone who is not on any of the 14 rosters is a free agent. If the rosters did not load, the tab keeps the stamped value and does not call the whole league a free agent.

`data/free-agents.json` is a sample waiver list. It does not decide who is unrostered.

## The file

`data/rankings/latest.json`:

```json
{ "season": 2026, "week": 5, "file": "2026-wk5.json", "asOf": "2026-10-10T00:00:00.000Z" }
```

`asOf` is UTC. The tab prints it in Pacific time.

`data/rankings/<season>-wk<N>.json`:

- `season`, `week`, `asOf`, `scoring`, `weights`
- `sources`: `{ id, name, ok, kind, detail, partial }`. `ok: false` means that feed did not come back. `partial: true` means some of it did. The tab lists both.
- `players`: one object per player
  - `name`, `pos` (`QB`, `RB`, `WR`, `TE`, `DL`, `LB`, `DB`), `team`
  - `opp`, `home` (`true` at home, `false` on the road, `null` on a bye), `bye`, `site` when the game is at a neutral site
  - `injury` short code: `Q`, `D`, `O`, `IR`, `SUS`, `PUP`, or blank
  - `played` when that team's game is already final
  - `pts`, `floor`, `ceil`, `rank`, `split`
  - `sources.sleeper`, `sources.espn`, `sources.recent`: `{ pts, rank }` and, for last 3, `weeks`
  - `sources.fantasypros`: `{ rank, low, high }`
  - `matchup`: `{ grade, kind, fpa, place, of, plays, passAtt, sacksAllowed, note }`
  - `vegas`: `{ spread, total, implied }` or null
  - `weather`: `{ indoor, text }` or null
  - `avail`: `eddies`, `fa`, or `other`
  - `club`: league team name, or blank for a free agent

If every source fails and the file would have no players, the script exits with an error and the action does not commit an empty board. One failed source does not do that.
