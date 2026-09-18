#!/usr/bin/env bash
set -euo pipefail

# One commit, both pointers. The Contents API writes one file per call, so
# writing target and channel separately would produce two commits — exactly
# the split-write skew a tagged release can't tolerate.
entries='[]'
message=""

if [ -n "$TARGET" ]; then
  name=$(basename "$TARGET")
  file="${TARGET}/kustomization.yaml"

  if ! resp=$(gh api "repos/${REPO}/contents/${file}?ref=${GITHUB_SHA}"); then
    echo "::error::${file} not found on ${DEFAULT_BRANCH} — is '${TARGET}' the right overlay path?"
    exit 1
  fi
  jq -r .content <<< "$resp" | base64 -d > target-current.yaml

  sed -E "s|(newTag: \")[^\"]*(\")|\1${VERSION}\2|" target-current.yaml > target-bumped.yaml
  grep -q "newTag: \"${VERSION}\"" target-bumped.yaml \
    || { echo "::error::${file} has no quoted newTag line to bump."; exit 1; }
  if cmp -s target-current.yaml target-bumped.yaml; then
    echo "${TARGET} is already at ${VERSION}; nothing to promote there."
  else
    blob=$(gh api --method POST "repos/${REPO}/git/blobs" \
      -f content="$(base64 -w0 target-bumped.yaml)" -f encoding=base64 --jq .sha)
    entries=$(jq --arg p "$file" --arg s "$blob" \
      '. + [{path: $p, mode: "100644", type: "blob", sha: $s}]' <<< "$entries")
    message="bump ${name} to ${VERSION}"
  fi
fi

if [ -n "$CHANNEL" ]; then
  if ! resp=$(gh api "repos/${REPO}/contents/${CHANNEL_FILE}?ref=${GITHUB_SHA}"); then
    echo "::error::${CHANNEL_FILE} not found on ${DEFAULT_BRANCH}."
    exit 1
  fi
  jq -r .content <<< "$resp" | base64 -d > channel-current.yaml

  # The key must already exist. Creating it on demand would let a typo
  # add `prd:` and report success while the real channel never moves.
  if [ "$(yq "has(\"${CHANNEL}\")" channel-current.yaml)" != "true" ]; then
    echo "::error::${CHANNEL_FILE} has no '${CHANNEL}' key. Add it before promoting."
    exit 1
  fi
  cp channel-current.yaml channel-bumped.yaml
  VERSION="$VERSION" yq -i ".\"${CHANNEL}\" = strenv(VERSION)" channel-bumped.yaml
  if cmp -s channel-current.yaml channel-bumped.yaml; then
    echo "${CHANNEL} is already at ${VERSION}; nothing to promote there."
  else
    blob=$(gh api --method POST "repos/${REPO}/git/blobs" \
      -f content="$(base64 -w0 channel-bumped.yaml)" -f encoding=base64 --jq .sha)
    entries=$(jq --arg p "$CHANNEL_FILE" --arg s "$blob" \
      '. + [{path: $p, mode: "100644", type: "blob", sha: $s}]' <<< "$entries")
    [ -z "$message" ] && message="set ${CHANNEL} to ${VERSION}" || message="${message}, set ${CHANNEL} to ${VERSION}"
  fi
fi

if [ -z "$message" ]; then
  echo "commit=" >> "$GITHUB_OUTPUT"
  [ -n "$TAG" ] || echo "Nothing moved; ${VERSION} was already current everywhere requested."
  exit 0
fi

base_tree=$(gh api "repos/${REPO}/commits/${GITHUB_SHA}" --jq .commit.tree.sha)
tree=$(jq -n --arg b "$base_tree" --argjson t "$entries" '{base_tree: $b, tree: $t}' \
  | gh api --method POST "repos/${REPO}/git/trees" --input - --jq .sha)
# [skip ci]: App-token commits, unlike GITHUB_TOKEN ones, do trigger
# workflows, and a pointer write has nothing to build.
commit=$(jq -n --arg m "release: ${message} [skip ci]" \
               --arg t "$tree" --arg p "$GITHUB_SHA" \
               '{message: $m, tree: $t, parents: [$p]}' \
  | gh api --method POST "repos/${REPO}/git/commits" --input - --jq .sha)
echo "commit=${commit}" >> "$GITHUB_OUTPUT"
echo "Wrote \`${commit:0:7}\`: ${message}." >> "$GITHUB_STEP_SUMMARY"
