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

Nothing here pushes to `main`, and nothing here pushes at all. Bill reviews and merges.

- `data/season-ending.json` lists players out for the year (seeded with Edgerrin Cooper, LB GB, Achilles, IR since Oct 13 2026). They are removed from waiver recs AND the FA pool. **Required**: if this file is missing, invalid or empty, the run fails. A seed floor in code (`REQUIRED_SEASON_ENDING` in `scripts/warroom_common.py`, currently Edgerrin Cooper) must be on the list, or the run fails, so a wiped or truncated list can't fail open.
- `data/do-not-pitch.json` lists Bill's passes (for example Austin Booker for Week 7). They are removed from waiver recs only and stay in the FA pool. `weeks` limits a pass to those weeks. **Required** and fail-closed. It MAY be empty, but only as the explicit object `{"players": []}`. A missing file, `{}`, `null`, or a bare array fails.
- Names are cleaned before matching: `(GB)`, `[IR]`, ` - LB GB`, a trailing `, LB GB`, `E.Cooper` → `E. Cooper`, and other punctuation and underscores collapse to spaces. Matching is by player id (`id`/`ids` on a list entry vs `id`/`playerId`/`fantraxId` on a rec) or by normalized name (case, spaces, accents, periods, Jr./III, and "Last, First" order don't matter). An initials-only rec ("E. Cooper") that matches an entry's initial and last name is blocked. A rec with no player name (id only, or null) is never published.
- Deny-pending: any key like pending/claims/bids/offers/claimsQueue, any `*status`/`*state` value like pending/proposed/submitted/claimsQueue (case and spaces ignored), any "pending" text inside waivers/drops/trades records, `PEND` or "awaiting approval" anywhere, and "pending" only in the same text as bid/claim/trade/FAAB/offer/$N (so "MRI results pending" is fine; "0 pending"/"no pending" is fine) stops the run with a nonzero exit, and nothing is written. Status `Open` blocks only inside waivers/trades/claims/bids/drops.
- `scripts/build_free_agents.py` and `scripts/build_warroom.py` pick the newest Fantrax file by its own scrape timestamp (`scrapedAt`/`scraped`), not its file name. Partial scrapes and timestamps in the future are skipped. Week = 1 + floor((today PT − Sep 10 2026) / 7). Stamps are in PT.
- `scripts/refresh_green_dots.py` rebuilds `data/green-dots.json` only from a newer FREE post, and only when all 32 teams are found and every non-bye team is resolved. The post's final wording wins ("X finished with / took over / wore the dot"). Every parsed name must be in the repo's player files (IDP rankings, HQ rosters, player-values, the current rankings board, or the previous green-dot list), or that team counts as unresolved. "Bye week? No" is not a bye. A "shared" dot is null with both names in notes. Bye teams get `bye: true`, with the previous dot carried over. It always writes `data/green-dots-status.json` (`stale: true` when the file's week is older than the current week).
- `scripts/refresh_warroom.py --mode full|ci [--dry-run]` copies the repo to a temp stage, runs the steps there, validates JSON, runs the pending gate, then runs the Python and node tests inside the stage. The node whitelist (`tests/KNOWN_FAILING.txt`) matches exact names, nested subtests included, and a node crash counts as a failure. Only then does it swap the staged `data/` in, all-or-nothing. It keeps a full backup copy, rolls back on error, and if the rollback rename also fails it restores `data/` from the backup and exits 2. For the instant between the two renames, a reader can find no `data/`. It never commits.
- Times: a `--now` or scrape time with no offset is read as PT. An ambiguous or nonexistent PT wall time (Nov 1 1:00–1:59 AM, Mar 14 2:00–2:59 AM) fails `--now`, and a scrape file with such a time is skipped. Give an explicit offset (`-07:00`/`-08:00`) instead.
- Routine hook: `bash scripts/hooks/warroom-refresh.sh` after the day's Fantrax scrape and editorial build. If it exits 0, review the diff and commit/push as today. If it exits nonzero, `data/` is untouched.
- `docs/workflows/warroom-saturday.yml` (Bill installs it in `.github/workflows/`) runs Saturday at 10:23 AM PT in `ci` mode. It pushes nothing and opens no PR, and uploads changed green-dot files as a review artifact.
