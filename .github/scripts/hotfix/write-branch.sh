#!/usr/bin/env bash
set -euo pipefail

# One commit on the hotfix branch pinning every target to VERSION, parented on
# HEAD_SHA. No force: if the branch moved, fail closed.
entries='[]'
names=()
for t in $TARGETS; do
  file="${t}/kustomization.yaml"
  if ! resp=$(gh api "repos/${REPO}/contents/${file}?ref=${HEAD_SHA}"); then
    echo "::error::${file} not found at ${HEAD_SHA:0:7}; cannot pin ${VERSION} on ${BRANCH}."
    exit 1
  fi
  jq -r .content <<< "$resp" | base64 -d > cur.yaml
  sed -E "s|(newTag: \")[^\"]*(\")|\1${VERSION}\2|" cur.yaml > new.yaml
  grep -q "newTag: \"${VERSION}\"" new.yaml \
    || { echo "::error::${file} has no quoted newTag line; cannot pin ${VERSION} on ${BRANCH}."; exit 1; }
  cmp -s cur.yaml new.yaml && continue
  blob=$(gh api --method POST "repos/${REPO}/git/blobs" \
    -f content="$(base64 -w0 new.yaml)" -f encoding=base64 --jq .sha)
  entries=$(jq --arg p "$file" --arg s "$blob" \
    '. + [{path: $p, mode: "100644", type: "blob", sha: $s}]' <<< "$entries")
  names+=("$(basename "$t")")
done

if [ "${#names[@]}" -eq 0 ]; then
  echo "::notice::Every target already pins ${VERSION} at ${HEAD_SHA:0:7}; no commit for ${BRANCH}."
  echo "commit=${HEAD_SHA}" >> "$GITHUB_OUTPUT"
  exit 0
fi
what=$(printf ", %s" "${names[@]}"); what=${what:2}

base_tree=$(gh api "repos/${REPO}/commits/${HEAD_SHA}" --jq .commit.tree.sha)
tree=$(jq -n --arg b "$base_tree" --argjson t "$entries" '{base_tree: $b, tree: $t}' \
  | gh api --method POST "repos/${REPO}/git/trees" --input - --jq .sha)
commit=$(jq -n --arg m "release: bump ${what} to ${VERSION} [skip ci]" \
               --arg t "$tree" --arg p "$HEAD_SHA" \
               '{message: $m, tree: $t, parents: [$p]}' \
  | gh api --method POST "repos/${REPO}/git/commits" --input - --jq .sha)

if ! gh api --method PATCH "repos/${REPO}/git/refs/heads/${BRANCH}" -f sha="$commit" -F force=false >/dev/null; then
  echo "::error::refs/heads/${BRANCH} is no longer at ${HEAD_SHA:0:7}, or the App is not a bypass actor on the hotfix/** ruleset; could not write ${VERSION}."
  exit 1
fi
echo "commit=${commit}" >> "$GITHUB_OUTPUT"
echo "Wrote \`${commit:0:7}\` to \`${BRANCH}\`: bump ${what} to ${VERSION}." >> "$GITHUB_STEP_SUMMARY"
