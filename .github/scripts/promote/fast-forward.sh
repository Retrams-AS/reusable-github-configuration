#!/usr/bin/env bash
set -euo pipefail

# No `force`: the image was built from $GITHUB_SHA's tree, so a moved branch is
# rebuilt on only when everything since $GITHUB_SHA is promote pointer commits.
here=$(dirname "$0")
bot="${APP_SLUG}[bot]"
base=$GITHUB_SHA

# Prints why head may not be built on; prints nothing when it may.
foreign_since() {
  gh api "repos/${REPO}/compare/${GITHUB_SHA}...$1" | jq -r --arg bot "$bot" --arg ch "$CHANNEL_FILE" '
    if .status != "ahead" then "it is \(.status) of the run commit, not ahead"
    elif .total_commits > (.commits | length) or (.files | length) >= 300 then "too many changes to check"
    else
      (.commits[] | select(.author.login != $bot
          or (.commit.message | test("^release:.*\\[skip ci\\]\\s*$"; "s") | not))
        | "\(.sha[:7]) is not a promote pointer commit"),
      (.files[] | .filename, (.previous_filename // empty)
        | select(. != $ch and (test("^k8s/overlays/.+/kustomization\\.yaml$") | not))
        | "\(.) changed")
    end'
}

for attempt in 1 2 3 4 5; do
  if gh api --method PATCH "repos/${REPO}/git/refs/heads/${DEFAULT_BRANCH}" -f sha="$COMMIT" >/dev/null; then
    echo "commit=${COMMIT}" >> "$GITHUB_OUTPUT"
    echo "Landed \`${COMMIT:0:7}\` on \`${DEFAULT_BRANCH}\`." >> "$GITHUB_STEP_SUMMARY"
    exit 0
  fi
  head=$(gh api "repos/${REPO}/git/ref/heads/${DEFAULT_BRANCH}" --jq .object.sha)
  if [ "$head" = "$base" ]; then
    echo "::error::${DEFAULT_BRANCH} has not moved, so the refusal is not a race: is the App a bypass actor on its ruleset?"
    exit 1
  fi
  why=$(foreign_since "$head")
  if [ -n "$why" ]; then
    echo "::error::${DEFAULT_BRANCH} moved past ${GITHUB_SHA:0:7} with more than promote pointer commits ($(tr '\n' ';' <<< "$why")). The image was built from ${GITHUB_SHA:0:7}; dispatch a fresh release instead."
    exit 1
  fi
  echo "${DEFAULT_BRANCH} moved to ${head:0:7} by another promote; rebuilding on it."
  base=$head
  BASE=$head GITHUB_OUTPUT=rebuild.out bash "$here/write-pointers.sh"
  COMMIT=$(sed -n 's/^commit=//p' rebuild.out | tail -1)
  if [ -z "$COMMIT" ]; then
    echo "commit=${head}" >> "$GITHUB_OUTPUT"
    echo "\`${head:0:7}\` already carries ${VERSION}; nothing to land." >> "$GITHUB_STEP_SUMMARY"
    exit 0
  fi
  sleep $((attempt * 2))
done
echo "::error::${DEFAULT_BRANCH} kept moving; gave up after 5 attempts."
exit 1
