#!/usr/bin/env bash
set -euo pipefail

# Relies on the caller checkout's fetch-depth: 0 above (all tags are local).
calver='^[0-9]{4}-[0-9]{2}\.[0-9]+$'
if [ -n "$VERSION" ]; then
  if ! echo "$VERSION" | grep -qE "$calver"; then
    echo "::error::version must be CalVer YYYY-MM.N (e.g. 2026-06.1), got '$VERSION'."
    exit 1
  fi
else
  existing=$(git tag --points-at "$GITHUB_SHA" | { grep -E "$calver" || true; } | sort -V | tail -1)
  # A re-run reuses the original event's GITHUB_SHA, whose child is promote's
  # pointer commit — so --points-at cannot see the tag, and without this arm a
  # re-run mints a second version and retags the released image under it. A
  # fresh dispatch skips this: the branch is already at the tagged commit.
  if [ -z "$existing" ]; then
    existing=$(git tag -l | { grep -E "$calver" || true; } | while read -r t; do
      if [ "$(git rev-parse -q --verify "${t}^{commit}^" || true)" = "$GITHUB_SHA" ]; then
        echo "$t"
      fi
    done | sort -V | tail -1)
  fi
  if [ -n "$existing" ]; then
    VERSION="$existing"
    echo "Commit already tagged ${VERSION}; reusing it."
  else
    ym=$(date -u +%Y-%m)
    last=$(git tag -l "${ym}.*" | { grep -E "$calver" || true; } | sed "s/^${ym}\.//" | sort -n | tail -1)
    VERSION="${ym}.$(( ${last:-0} + 1 ))"
    echo "Auto-minting ${VERSION}."
  fi
fi
echo "version=$VERSION" >> "$GITHUB_OUTPUT"
if git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null; then
  echo "build=false" >> "$GITHUB_OUTPUT"
else
  echo "build=true" >> "$GITHUB_OUTPUT"
fi
echo "Release version: \`$VERSION\`" >> "$GITHUB_STEP_SUMMARY"
