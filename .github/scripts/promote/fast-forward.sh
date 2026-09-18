#!/usr/bin/env bash
set -euo pipefail

# No `force`, deliberately: the commit's parent is $GITHUB_SHA, so this is a
# compare-and-swap. Failing closed is correct — the caller already retagged an
# image built from $GITHUB_SHA, and re-parenting onto a newer head would tag a
# tree that image was never built from.
if ! gh api --method PATCH "repos/${REPO}/git/refs/heads/${DEFAULT_BRANCH}" -f sha="$COMMIT" >/dev/null; then
  echo "::error::${DEFAULT_BRANCH} is no longer at the commit this run was based on, or the App is not a bypass actor on its ruleset. Re-running a finished run always hits the first — dispatch a fresh run instead."
  exit 1
fi
echo "Landed \`${COMMIT:0:7}\` on \`${DEFAULT_BRANCH}\`." >> "$GITHUB_STEP_SUMMARY"
