# Eddies War Room

Private pages for the Eagle Ridge Eddies. Two screens:

- `index.html` is the in-season War Room: this week, weekly rankings, roster, waivers, IDP, news, the league, and the trade calculator.
- `draft.html` is the draft board. `draft-archive.html` is the 2026 draft-day copy and stays as it was.

Eddie fills `data/warroom.json`, `data/free-agents.json`, and `data/green-dots.json`. How those files are shaped:

- [docs/warroom-schema.md](docs/warroom-schema.md)
- [docs/free-agents-schema.md](docs/free-agents-schema.md)
- [docs/draft-setup.md](docs/draft-setup.md)
- [docs/rankings-schema.md](docs/rankings-schema.md)
- [docs/green-dots-schema.md](docs/green-dots-schema.md)

To rebuild trade prices from the season's stat lines, run `python3 scripts/build_player_values.py` from this folder. The Trade tab reads `data/player-values.json`.

To rebuild the weekly rankings board, run `node scripts/build_rankings.js` from this folder. A scheduled action does that through the week and commits `data/rankings/`.

## Auto-refresh (branch `eddie/warroom-auto-refresh`; merge is Bill's)

Nothing here pushes to `main`. Bill reviews and merges.

- `data/season-ending.json` lists players out for the year (seeded with Edgerrin Cooper, LB GB, Achilles, IR since Oct 13 2026). They are removed from waiver recs AND the FA pool.
- `data/do-not-pitch.json` lists Bill's passes (for example Austin Booker for Week 7). They are removed from waiver recs only and stay in the FA pool. `weeks` limits a pass to those weeks.
- `scripts/build_free_agents.py` builds `data/free-agents.json` from the newest `/workspace/fantrax-scrape-*-newsletter.json`.
- `scripts/build_warroom.py` refreshes `data/warroom.json` without needing a date: week = 1 + floor((today PT − Sep 10 2026) / 7), it stamps `asOf`/`lastUpdated` in PT, applies the exclude lists, re-ranks waivers, refreshes waiver stats from the newest FA scrape, and strips anything pending (bids, claims, trades). The editorial plan (lineup reasons, news) still comes from the day's newsletter routine.
- `scripts/refresh_green_dots.py` checks Woellert's Substack. It rebuilds `data/green-dots.json` only from a newer FREE post, and always writes `data/green-dots-status.json` (`stale: true` when the file's week is older than the current week). Paid posts are never parsed.
- `scripts/refresh_warroom.py --mode full|ci [--dry-run]` runs all of the above on a staged copy, validates every JSON file, runs `tests/py` and the node tests (`tests/KNOWN_FAILING.txt` lists the 3 failures that predate this branch), and copies changes into `data/` only if everything passes. It never commits.
- Routine hook: `bash scripts/hooks/warroom-refresh.sh` after the day's Fantrax scrape and editorial build. If it exits 0, the routine commits/pushes as it does today; if it exits nonzero, `data/` is untouched.
- `docs/workflows/warroom-saturday.yml` (Bill installs it by moving it to `.github/workflows/`; the bot token cannot push workflow files) runs Saturday at 10:23 AM PT in `ci` mode and pushes any change to an `auto/green-dots-YYYYMMDD` branch, never to `main`.
