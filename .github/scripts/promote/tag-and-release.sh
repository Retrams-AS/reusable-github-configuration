#!/usr/bin/env bash
set -euo pipefail

if gh api "repos/${REPO}/git/ref/tags/${TAG}" >/dev/null 2>&1; then
  echo "refs/tags/${TAG} already exists; leaving it."
  exit 0
fi

gh api "repos/${REPO}/git/refs" -f ref="refs/tags/${TAG}" -f sha="$TARGET_SHA" >/dev/null
echo "Tagged \`${TARGET_SHA:0:7}\` as \`${TAG}\`." >> "$GITHUB_STEP_SUMMARY"

[ "$GITHUB_RELEASE" = "true" ] || exit 0

# gh release list reads releases, not tags, so the tag written above is invisible
# to it and prev is still the release before this one.
prev=$(gh release list --repo "$REPO" --exclude-pre-releases --exclude-drafts --limit 1 --json tagName --jq '.[0].tagName // ""')
notes=(--generate-notes)
if [ -n "$prev" ]; then
  notes+=(--notes-start-tag "$prev")
fi
gh release create "$TAG" --repo "$REPO" --title "$TAG" "${notes[@]}"
