# WU Sunday Command Center

`sunday.html` is the phone page for the fantasy Sunday. It reads three JSON files and does not scrape anything.

- `data/sunday/config.json` names the featured club and how often to refresh.
- `data/sunday/live.json` is the matchup. A separate job should overwrite it about every 30 minutes.
- `data/td-parlay.json` is the anytime-TD card for the week on the live file.

Leave `"sample": true` on a file until the numbers are real. The page then shows a sample banner.

Times are Pacific time, labeled **PT**. Write `updatedAt` as ISO 8601 with a numeric offset (`-07:00` while daylight time is in effect, `-08:00` after the fall change). The page does not say PDT or PST.

This page never shows a bid that has not cleared, and it never shows a trade that has not cleared. Do not put those in these files. Do not add an owner field, and do not tie a club to a person. The featured club is displayed as **Eagleridge Eddie's**.

## Config

| Field | What it is |
| --- | --- |
| `featuredTeam` | Club id inside `live.json`, such as `eddies`. The page reads this key. |
| `featuredName` | The name on the matchup card. For this club use `Eagleridge Eddie's`. |
| `live` | Path to the matchup file. Default `data/sunday/live.json`. |
| `parlay` | Path to the TD card. Default `data/td-parlay.json`. |
| `refreshMinutes` | How often the page refetches. Default 5. Values under 1 are treated as 1. |
| `staleMinutes` | Age at which the score file is marked STALE. Default 45. |

## Live matchup

```json
{
  "sample": true,
  "updatedAt": "2026-10-31T13:02:00-07:00",
  "season": 2026,
  "week": 8,
  "opponent": "ultron",
  "teams": [
    {
      "id": "eddies",
      "name": "Eagleridge Eddie's",
      "record": "5-2",
      "starters": [
        {
          "slot": "RB",
          "player": "Breece Hall",
          "pos": "RB",
          "nflTeam": "NYJ",
          "status": "live",
          "points": 8.6,
          "projection": 16.8,
          "remainingProj": 7.5,
          "injury": "Q"
        }
      ]
    }
  ]
}
```

| Field | What it is |
| --- | --- |
| `updatedAt` | When the job wrote the file. The matchup card prints this in PT. |
| `week` | Fantrax week. The parlay card uses this week. |
| `opponent` | The other club's id. |
| `teams[].id` | Stable id. Must match `featuredTeam` or `opponent`. |
| `teams[].name` | Club name. The featured card still prefers `featuredName` from config. |
| `teams[].record` | Optional, such as `5-2`. |
| `starters` | The active lineup, in order. Bench players are not listed. A suggested swap is a field on the starter, not a second table. |

Starter fields:

| Field | What it is |
| --- | --- |
| `player` | Name. |
| `pos` | QB, RB, WR, TE, DL, LB, or DB. |
| `nflTeam` | NFL abbreviation. |
| `slot` | Lineup slot when it differs from `pos` (`FLEX`, `IDP`). |
| `status` | `not_started`, `live`, or `final`. The page also accepts "Not started". Players in the same NFL game should share a status. |
| `points` | Fantasy points already scored. |
| `projection` | Full-game projection. |
| `remainingProj` | Points still expected. Use `0` when the game is `final`. Use `0` when the player will not play. If this is omitted, a final game counts as 0 and any other game counts as `max(0, projection − points)`. |
| `injury` | `Q`, `D`, `OUT`, or blank. `Doubtful` and `O` are accepted. |
| `swap` | Optional. Only when you have a bench player to suggest. `{ "player", "pos", "nflTeam", "note" }`. The page does not move that player into the lineup, and the win probability does not assume the swap. |

The live score on the card is the sum of starter `points`. The projected score is points already scored plus remaining projected points.

## Win probability

Let the featured club have scored \(S_f\) with \(R_f\) still to come, and the opponent \(S_o\) and \(R_o\). Remaining values below 0 are treated as 0.

\[
F_f = S_f + R_f, \quad F_o = S_o + R_o
\]

\[
\mu = F_f - F_o, \quad \sigma = \sqrt{R_f + R_o}
\]

\[
P = \Phi(\mu / \sigma)
\]

\(\Phi\) is the standard normal CDF (Abramowitz and Stegun 7.1.26, through the error function). Each side's remaining points are treated as independent with variance equal to the remaining projection, so one unit of variance per remaining projected point.

When both lineups are finished (\(\sigma = 0\)): \(P = 1\) if the featured club is ahead, \(P = 0\) if it is behind, and \(P = 0.5\) on a tie. The percentage is \(P(\text{margin} > 0)\). It is not a betting price, and it ignores teammates in the same game moving together.

## Pace delta

The starters table shows points, the full projection, and a colored delta once the game has started.

\[
\text{delta} = \text{points} + \text{remainingProj} - \text{projection}
\]

Green is ahead of that pace, red is behind, and a wash is neutral. Before kickoff the delta is hidden, and points show as a dash so a zero does not look like a bad score. When a game is final, remaining is 0, so the delta is points minus the projection.

## Lock alerts

A starter is a lock alert when the game has not started and the injury tag is OUT, Doubtful (`D`), or IR. Questionable is only a tag on the row. If `swap.player` is set, the banner names that bench player. If it is missing, the banner names the problem and stops there.

## TD parlay

There is no `data/td-parlay.json` history in this repo. The league HQ file nests the same facts by person: each entry has `weeks["8"].player` and `weeks["8"].td`. `td` is `Yes`, `No`, `N/A`, or `""` while the game is open. A week hits when every active pick is `Yes`. `N/A` does not count. That HQ file groups people under `owners`. Do not commit that key or anyone's name here.

This repo publishes a flat list:

| Field | What it is |
| --- | --- |
| `week` | Fantrax week. |
| `participant` | Club name, or another label that is not a person tied to a club. |
| `pick` | The player who needs a touchdown. |
| `result` | `Yes`, `No`, or `pending`. |

The page also accepts a `participants` array whose `weeks` map uses `player` and `td`, and it will read an `owners` array in that same shape if you open an HQ file locally. `""` becomes `pending`. The Sunday card shows only the week on `live.json`.

The week is **still alive** when at least one active pick is pending and none are `No`. It **hit** when every active pick is `Yes`. It is **dead** when any active pick is `No`.

## Refresh and STALE

The browser refetches config, the live file, and the parlay every five minutes (or `refreshMinutes`). Each request adds `?t=` with the current time and uses `cache: "no-store"`.

The score file is **STALE** when `now − updatedAt` is greater than 45 minutes (`staleMinutes`). A file that is exactly 45 minutes old is still fresh. A missing or unparseable `updatedAt` is STALE. The parlay does not flip that badge. The badge is the word STALE, in Pacific context with the updated time still labeled PT.
