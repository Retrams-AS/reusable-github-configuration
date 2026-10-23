#!/usr/bin/env bash
set -euo pipefail

# Env: BRANCH DEFAULT_BRANCH TARGETS (space-separated overlay dirs) CHANNEL
# CHANNEL_FILE FORBIDDEN_PATHS GITHUB_OUTPUT. Needs full history, tags, and
# origin/$DEFAULT_BRANCH fetched.
main="origin/${DEFAULT_BRANCH}"
err() { echo "::error::$*"; exit 1; }

[[ "$BRANCH" =~ ^hotfix/([0-9]{4}-[0-9]{2}\.[0-9]+)$ ]] \
  || err "branch '${BRANCH}' must be hotfix/<base>, e.g. hotfix/2026-09.1."
base="${BASH_REMATCH[1]}"
re_base="${base//./\\.}"

git rev-parse -q --verify "refs/tags/${base}^{commit}" >/dev/null \
  || err "base tag ${base} does not exist."
git merge-base --is-ancestor "refs/tags/${base}" HEAD \
  || err "${base} is not an ancestor of ${BRANCH}; cut the branch from the tag."

for t in ${TARGETS:-}; do
  f="${t}/kustomization.yaml"
  git cat-file -e "${main}:${f}" 2>/dev/null || err "${f} not found on ${DEFAULT_BRANCH}."
  pin=$(git show "${main}:${f}" | sed -nE 's/^[[:space:]]*newTag: "([^"]*)".*/\1/p' | head -1)
  [[ "$pin" =~ ^${re_base}(\.[0-9]+)?$ ]] \
    || err "${t} pins '${pin}' on ${DEFAULT_BRANCH}, not ${base} or a hotfix of it."
done

if [ -n "${CHANNEL:-}" ]; then
  git cat-file -e "${main}:${CHANNEL_FILE}" 2>/dev/null || err "${CHANNEL_FILE} not found on ${DEFAULT_BRANCH}."
  pin=$(git show "${main}:${CHANNEL_FILE}" | CH="$CHANNEL" yq '.[strenv(CH)]')
  [[ "$pin" =~ ^${re_base}(\.[0-9]+)?$ ]] \
    || err "channel '${CHANNEL}' is at '${pin}' on ${DEFAULT_BRANCH}, not ${base} or a hotfix of it."
fi

# True for the workflow's own pointer commit: release subject, and the diff
# touches only target kustomization.yaml files, only newTag lines.
is_pointer() {
  local sha=$1 f t ok
  [[ "$(git log -1 --format=%s "$sha")" =~ ^release:\ .*\ to\ ${re_base}\.[0-9]+\ \[skip\ ci\]$ ]] || return 1
  while read -r f; do
    [ -n "$f" ] || continue
    ok=0
    for t in ${TARGETS:-}; do [ "$f" = "${t}/kustomization.yaml" ] && ok=1; done
    [ $ok -eq 1 ] || return 1
  done < <(git show --format= --name-only "$sha")
  ! git show --format= -U0 "$sha" | grep -E '^[+-]' | grep -vE '^(\+\+\+|---) ' \
    | grep -qvE '^[+-][[:space:]]*newTag: "[^"]*"'
}

# Commits with no patch on main; verified pointer commits never have one.
while read -r _ sha; do
  [ -n "$sha" ] || continue
  subj=$(git log -1 --format=%s "$sha")
  is_pointer "$sha" && continue
  # A -x trailer naming a commit on main also counts (patch differs after a conflict).
  for src in $(git log -1 --format=%B "$sha" | sed -nE 's/^\(cherry picked from commit ([0-9a-f]{7,40})\)$/\1/p'); do
    full=$(git rev-parse -q --verify "${src}^{commit}" 2>/dev/null) || continue
    git merge-base --is-ancestor "$full" "$main" && continue 2
  done
  err "commit ${sha:0:7} '${subj}' is neither patch-identical to a ${DEFAULT_BRANCH} commit nor cherry-picked (-x) from one; land the fix there first."
done < <(git cherry "$main" HEAD "refs/tags/${base}" | grep '^+' || true)

if [ -n "${FORBIDDEN_PATHS:-}" ]; then
  specs=()
  set -f  # the pathspecs are git's to expand, not the shell's
  for p in $FORBIDDEN_PATHS; do
    if [[ "$p" == :* ]]; then specs+=("$p"); else specs+=(":(glob)$p"); fi
  done
  set +f
  # Per commit, so a migration added then reverted in the branch is still refused.
  hit=$(for c in $(git rev-list "refs/tags/${base}..HEAD"); do
    is_pointer "$c" || git diff-tree --no-commit-id --name-only -r "$c" -- "${specs[@]}"
  done | sort -u)
  [ -z "$hit" ] || err "hotfix touches forbidden paths: $(echo "$hit" | tr '\n' ' ')"
fi

hf="^${re_base}\.[0-9]+$"
existing=$(git tag --points-at HEAD | { grep -E "$hf" || true; } | sort -V | tail -1)
if [ -n "$existing" ]; then
  version="$existing"; resume=true
else
  last=$(git tag -l "${base}.*" | { grep -E "$hf" || true; } | sed "s/^${re_base}\.//" | sort -n | tail -1)
  version="${base}.$(( ${last:-0} + 1 ))"; resume=false
fi
{ echo "base=${base}"; echo "version=${version}"; echo "resume=${resume}"; } >> "$GITHUB_OUTPUT"
