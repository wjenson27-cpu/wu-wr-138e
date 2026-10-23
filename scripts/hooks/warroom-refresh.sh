#!/usr/bin/env bash
# Hook for the daily HQ sync / newsletter routines. Call AFTER the Fantrax scrape files are written and the
# day's editorial build_warroom has run:
#   bash /workspace/wu-wr-138e/scripts/hooks/warroom-refresh.sh            # full refresh on the box
#   bash /workspace/wu-wr-138e/scripts/hooks/warroom-refresh.sh --dry-run  # check only
# Exit 0 = data/ refreshed (or unchanged). Nonzero = nothing in data/ was touched.
# This hook never commits or pushes. The routine reviews the diff and commits/pushes as it does today.
set -euo pipefail
cd "$(dirname "$0")/../.."
exec python3 scripts/refresh_warroom.py --mode full "$@"
