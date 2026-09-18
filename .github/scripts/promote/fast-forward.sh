#!/usr/bin/env bash
set -euo pipefail

# No `force`, deliberately: the commit's parent is $GITHUB_SHA, so this
# is a compare-and-swap. If the branch moved during the run, failing
# closed is correct — the caller already retagged an image built from
# $GITHUB_SHA, and re-parenting onto a newer head would tag a tree that
# image was never built from. Re-dispatching retags from the new head.
if ! gh api --method PATCH "repos/${REPO}/git/refs/heads/${DEFAULT_BRANCH}" -f sha="$COMMIT" >/dev/null; then
  echo "::error::${DEFAULT_BRANCH} moved during this run; re-dispatch to retag from the new head."
  exit 1
fi
echo "Landed \`${COMMIT:0:7}\` on \`${DEFAULT_BRANCH}\`." >> "$GITHUB_STEP_SUMMARY"
