# Free agents

`data/free-agents.json` is the waiver pool for the trade calculator. Eddie writes it from Fantrax once a day.

The calculator only needs this file to answer one question: what could Bill pick up for free? A rostered player is worth his points over that line. If the best available linebacker scores 12 a game, a linebacker who scores 13 is worth almost nothing in a trade.

If this file is missing, or `asOf` is more than 3 days old, the calculator ignores the wire and uses the last rostered starter instead. The Trade tab shows a badge when that happens.

Leave `"sample": true` on a placeholder. The tab then says the wire is a sample. Set `"sample": false` when the names are from Fantrax.

## The file

```json
{
  "sample": false,
  "asOf": "2026-10-09T17:00:00-07:00",
  "source": "Fantrax",
  "players": [
    {
      "player": "Jack Gibbens",
      "pos": "LB",
      "team": "MIA",
      "fpg": 7.8,
      "last3Fpg": 6.9,
      "rosteredPct": 11
    }
  ]
}
```

`asOf` is Pacific time, when the list was pulled.

## Each player

| Field | Fantrax column | What to put |
| --- | --- | --- |
| `player` | Player | Name |
| `pos` | Pos | QB, RB, WR, TE, DL, LB, or DB |
| `team` | Team | NFL abbreviation |
| `fpg` | FP/G | Fantasy points per game, this season, in this league's scoring |
| `last3Fpg` | Last-3 FP/G | Points per game over the last three weeks he played. Use `null` if he has no recent weeks. `0` is a real zero. |
| `rosteredPct` | % rostered | 0 to 100 |

A player with `rosteredPct` of 100 is not available. He is left out of the wire. Anyone under 100, or with no percent, counts.

The best free agent at each position is the wire baseline. The rostered baseline is the last starter the league already uses at that position. The calculator keeps whichever baseline is higher.

Points per game on the wire are blended when both numbers exist: 60% season (`fpg`) and 40% last three weeks (`last3Fpg`). The Trade tab prints those weights.
