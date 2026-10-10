# Eddies War Room

Private pages for the Eagle Ridge Eddies. Two screens:

- `index.html` is the in-season War Room: this week, roster, waivers, IDP, news, the league, and the trade calculator.
- `draft.html` is the draft board. `draft-archive.html` is the 2026 draft-day copy and stays as it was.

Eddie fills `data/warroom.json` and `data/free-agents.json`. How those files are shaped:

- [docs/warroom-schema.md](docs/warroom-schema.md)
- [docs/free-agents-schema.md](docs/free-agents-schema.md)
- [docs/draft-setup.md](docs/draft-setup.md)

To rebuild trade prices from the season's stat lines, run `python3 scripts/build_player_values.py` from this folder. The Trade tab reads `data/player-values.json`.
