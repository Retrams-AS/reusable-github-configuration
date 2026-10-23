#!/usr/bin/env bash
set -euo pipefail

# On a 404, gh prints the error JSON to stdout, so key on exit status, not output.
if ! tagged=$(gh api "repos/${REPO}/git/ref/tags/${VERSION}" --jq .object.sha 2>/dev/null); then
  tagged=""
fi
if [ -z "$tagged" ]; then
  gh api "repos/${REPO}/git/refs" -f ref="refs/tags/${VERSION}" -f sha="$TARGET_SHA" >/dev/null
  echo "Tagged \`${TARGET_SHA:0:7}\` as \`${VERSION}\`." >> "$GITHUB_STEP_SUMMARY"
elif [ "$tagged" != "$TARGET_SHA" ]; then
  echo "::error::refs/tags/${VERSION} exists at ${tagged:0:7}, not ${TARGET_SHA:0:7}."
  exit 1
fi

if gh release view "$VERSION" --repo "$REPO" >/dev/null 2>&1; then
  echo "Release ${VERSION} already exists; leaving it."
  exit 0
fi

base_re=${BASE//./\\.}
if ! commits=$(gh api "repos/${REPO}/compare/${BASE}...${TARGET_SHA}" --paginate \
    --jq '.commits[].commit.message | split("\n")[0]'); then
  echo "::error::Compare ${BASE}...${TARGET_SHA:0:7} failed; cannot write notes for ${VERSION}."
  exit 1
fi
{
  echo "Hotfix on \`${BASE}\`."
  echo
  echo "Changes since ${BASE}:"
  grep -Ev "^release: .* to ${base_re}\.[0-9]+ \[skip ci\]$" <<< "$commits" | sed 's/^/- /' || true
  echo
  echo "Targets: ${TARGETS}${CHANNEL:+; channel ${CHANNEL}}"
} > notes.md
gh release create "$VERSION" --repo "$REPO" --title "$VERSION" --latest --notes-file notes.md
echo "Released \`${VERSION}\`." >> "$GITHUB_STEP_SUMMARY"
