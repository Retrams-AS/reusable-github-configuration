#!/usr/bin/env bash
set -euo pipefail

if gh api "repos/${REPO}/git/ref/tags/${TAG}" >/dev/null 2>&1; then
  echo "refs/tags/${TAG} already exists; leaving it."
  exit 0
fi

# Read before the tag exists: gh release list ignores tags, but keep the
# order obvious for the next reader.
prev=""
if [ "$GITHUB_RELEASE" = "true" ]; then
  prev=$(gh release list --repo "$REPO" --exclude-pre-releases --exclude-drafts --limit 1 --json tagName --jq '.[0].tagName // ""')
fi
gh api "repos/${REPO}/git/refs" -f ref="refs/tags/${TAG}" -f sha="$TARGET_SHA" >/dev/null
echo "Tagged \`${TARGET_SHA:0:7}\` as \`${TAG}\`." >> "$GITHUB_STEP_SUMMARY"
if [ "$GITHUB_RELEASE" = "true" ]; then
  if [ -n "$prev" ]; then
    gh release create "$TAG" --repo "$REPO" --title "$TAG" --generate-notes --notes-start-tag "$prev"
  else
    gh release create "$TAG" --repo "$REPO" --title "$TAG" --generate-notes
  fi
fi
