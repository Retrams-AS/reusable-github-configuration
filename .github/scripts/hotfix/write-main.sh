#!/usr/bin/env bash
set -euo pipefail

# Move main's pins to VERSION in one commit. Each attempt re-reads main's head
# and re-checks every pin it will change still sits on BASE or a BASE.<n>.
# No force: a 422 means main moved; retry from the read.
base_re="^${BASE//./\\.}(\\.[0-9]+)?\$"

for attempt in 1 2 3; do
  head=$(gh api "repos/${REPO}/git/ref/heads/${DEFAULT_BRANCH}" --jq .object.sha)
  entries='[]'
  names=()

  if [ -n "$CHANNEL" ]; then
    if ! resp=$(gh api "repos/${REPO}/contents/${CHANNEL_FILE}?ref=${head}"); then
      echo "::error::${CHANNEL_FILE} not found on ${DEFAULT_BRANCH} at ${head:0:7}; cannot set ${CHANNEL} to ${VERSION}."
      exit 1
    fi
    jq -r .content <<< "$resp" | base64 -d > cur.yaml
    pin=$(CH="$CHANNEL" yq '.[strenv(CH)] // ""' cur.yaml)
    if [ "$pin" != "$VERSION" ]; then
      if ! [[ $pin =~ $base_re ]]; then
        echo "::error::${CHANNEL} in ${CHANNEL_FILE} on ${DEFAULT_BRANCH} is '${pin}', not ${BASE}; refusing to write ${VERSION}."
        exit 1
      fi
      cp cur.yaml new.yaml
      VERSION="$VERSION" yq -i ".\"${CHANNEL}\" = strenv(VERSION)" new.yaml
      blob=$(gh api --method POST "repos/${REPO}/git/blobs" \
        -f content="$(base64 -w0 new.yaml)" -f encoding=base64 --jq .sha)
      entries=$(jq --arg p "$CHANNEL_FILE" --arg s "$blob" \
        '. + [{path: $p, mode: "100644", type: "blob", sha: $s}]' <<< "$entries")
      names+=("$CHANNEL")
    fi
  else
    for t in $TARGETS; do
      file="${t}/kustomization.yaml"
      if ! resp=$(gh api "repos/${REPO}/contents/${file}?ref=${head}"); then
        echo "::error::${file} not found on ${DEFAULT_BRANCH} at ${head:0:7}; cannot bump to ${VERSION}."
        exit 1
      fi
      jq -r .content <<< "$resp" | base64 -d > cur.yaml
      pin=$(sed -nE 's/^[[:space:]]*newTag: "([^"]*)".*/\1/p' cur.yaml | head -1)
      [ "$pin" = "$VERSION" ] && continue
      if ! [[ $pin =~ $base_re ]]; then
        echo "::error::${file} on ${DEFAULT_BRANCH} pins '${pin}', not ${BASE}; refusing to write ${VERSION}."
        exit 1
      fi
      sed -E "s|(newTag: \")[^\"]*(\")|\1${VERSION}\2|" cur.yaml > new.yaml
      blob=$(gh api --method POST "repos/${REPO}/git/blobs" \
        -f content="$(base64 -w0 new.yaml)" -f encoding=base64 --jq .sha)
      entries=$(jq --arg p "$file" --arg s "$blob" \
        '. + [{path: $p, mode: "100644", type: "blob", sha: $s}]' <<< "$entries")
      names+=("$(basename "$t")")
    done
  fi

  if [ "${#names[@]}" -eq 0 ]; then
    echo "::notice::Everything requested on ${DEFAULT_BRANCH} already pins ${VERSION}; nothing to write."
    exit 0
  fi
  what=$(printf ", %s" "${names[@]}"); what=${what:2}
  [ -n "$CHANNEL" ] && what="set ${what}" || what="bump ${what}"

  base_tree=$(gh api "repos/${REPO}/commits/${head}" --jq .commit.tree.sha)
  tree=$(jq -n --arg b "$base_tree" --argjson t "$entries" '{base_tree: $b, tree: $t}' \
    | gh api --method POST "repos/${REPO}/git/trees" --input - --jq .sha)
  commit=$(jq -n --arg m "release: ${what} to ${VERSION} [skip ci]" \
                 --arg t "$tree" --arg p "$head" \
                 '{message: $m, tree: $t, parents: [$p]}' \
    | gh api --method POST "repos/${REPO}/git/commits" --input - --jq .sha)

  if err=$(gh api --method PATCH "repos/${REPO}/git/refs/heads/${DEFAULT_BRANCH}" \
      -f sha="$commit" -F force=false 2>&1 >/dev/null); then
    echo "Wrote \`${commit:0:7}\` to \`${DEFAULT_BRANCH}\`: ${what} to ${VERSION}." >> "$GITHUB_STEP_SUMMARY"
    exit 0
  fi
  echo "Attempt ${attempt}: PATCH of ${DEFAULT_BRANCH} failed: ${err}"
  grep -q 422 <<< "$err" || { echo "::error::Could not write ${VERSION} to refs/heads/${DEFAULT_BRANCH}: ${err}"; exit 1; }
done
echo "::error::refs/heads/${DEFAULT_BRANCH} kept moving, or the App is not a bypass actor on its ruleset; ${VERSION} not written after 3 attempts."
exit 1
