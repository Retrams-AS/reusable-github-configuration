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
