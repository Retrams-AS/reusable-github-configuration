#!/usr/bin/env bash
set -euo pipefail

# Tag the commit only after the image exists, always via the refs API
# rather than `gh release create --target` (no `git push`, so the checkout
# stays credential-less). Skipped when create-tag is false: the caller is
# chaining promote, which lands its own commit and tag instead.

# Read before the tag exists: gh release list ignores tags, but keep the
# order obvious for the next reader.
prev=""
if [ "$MAKE_RELEASE" = "true" ]; then
  prev=$(gh release list --exclude-pre-releases --exclude-drafts --limit 1 --json tagName --jq '.[0].tagName // ""')
fi
gh api "repos/$GITHUB_REPOSITORY/git/refs" -f ref="refs/tags/$VERSION" -f sha="$TARGET_SHA" >/dev/null
if [ "$MAKE_RELEASE" = "true" ]; then
  if [ -n "$prev" ]; then
    gh release create "$VERSION" --title "$VERSION" --generate-notes --notes-start-tag "$prev"
  else
    gh release create "$VERSION" --title "$VERSION" --generate-notes
  fi
fi
