#!/usr/bin/env bash
# Build-once/promote-many: retag the existing sha artifact to the CalVer
# tag (manifest copy — byte-identical, no rebuild).
#
# Walks back over kustomization-only commits. A promote bump rewrites a
# newTag and nothing else, so it has no artifact of its own and never will
# -- it carries [skip ci] because there is nothing there to build. The
# merge commit beneath it is the content this release is of.
set -uo pipefail
sha="$GITHUB_SHA"
for _ in $(seq 1 10); do
  sha7=$(echo "$sha" | cut -c1-7)
  if docker buildx imagetools create --tag "${IMAGE}:${VERSION}" "${IMAGE}:${sha7}"; then
    if [ "$sha" != "$GITHUB_SHA" ]; then
      echo "::notice::${GITHUB_SHA:0:7} has no artifact; used ${sha7}, reached over kustomization-only commits."
    fi
    exit 0
  fi
  if ! parent=$(git rev-parse -q --verify "${sha}^"); then
    break
  fi
  if [ -n "$(git diff --name-only "$parent" "$sha" -- . ':(exclude)*kustomization.yaml')" ]; then
    break
  fi
  sha="$parent"
done
echo "::error::No artifact ${IMAGE}:${GITHUB_SHA:0:7} in DOCR, and no ancestor reachable over kustomization-only commits has one. The Build workflow has not pushed this commit. Dispatch Build, then re-run."
exit 1
