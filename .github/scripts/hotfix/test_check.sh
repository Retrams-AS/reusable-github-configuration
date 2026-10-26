#!/usr/bin/env bash
# Fixture test for check.sh. Each case builds a fresh origin + clone.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
fails=0
G=(git -c commit.gpgsign=false -c tag.gpgsign=false -c user.name=t -c user.email=t@t)

# setup: root commit, then main with tag 2026-09.1; hotfix/2026-09.1 checked out.
setup() {
  W=$(mktemp -d); git init -q --bare -b main "$W/origin"
  git clone -q "$W/origin" "$W/w" 2>/dev/null; cd "$W/w" || exit 1
  git checkout -q -B main
  "${G[@]}" commit -q --allow-empty -m root
  mkdir -p k8s/overlays/prod
  echo '  newTag: "2026-09.1"' > k8s/overlays/prod/kustomization.yaml
  echo 'prod: 2026-09.1' > k8s/channels.yaml
  "${G[@]}" add -A; "${G[@]}" commit -qm base
  "${G[@]}" tag 2026-09.1
  git checkout -q -b hotfix/2026-09.1
}
# fix <file>: commit on the branch and cherry-pick the same patch onto main.
fix() {
  mkdir -p "$(dirname "$1")"; echo x > "$1"
  "${G[@]}" add -A; "${G[@]}" commit -qm "fix $1"
  local sha; sha=$(git rev-parse HEAD)
  git checkout -q main; "${G[@]}" cherry-pick "$sha" >/dev/null; git checkout -q hotfix/2026-09.1
}

# run <name> <ok|fail> <substring...>; inputs via BRANCH/TARGETS/CHANNEL/FORBIDDEN_PATHS.
run() {
  local name=$1 want=$2; shift 2
  git push -q origin main 2>/dev/null; git fetch -q origin
  out=$(BRANCH=${BRANCH:-$(git branch --show-current)} DEFAULT_BRANCH=main TARGETS=${TARGETS-k8s/overlays/prod} \
    CHANNEL=${CHANNEL-} CHANNEL_FILE=k8s/channels.yaml FORBIDDEN_PATHS=${FORBIDDEN_PATHS-} \
    GITHUB_OUTPUT="$W/out" bash "$here/check.sh" 2>&1); rc=$?
  out="$out $(cat "$W/out" 2>/dev/null)"
  local ok=1
  { [ "$want" = ok ] && [ $rc -eq 0 ]; } || { [ "$want" = fail ] && [ $rc -ne 0 ]; } || ok=0
  for s in "$@"; do [[ "$out" == *"$s"* ]] || ok=0; done
  if [ $ok -eq 1 ]; then echo "ok   $name"; else echo "FAIL $name (rc=$rc): $out"; fails=$((fails+1)); fi
  cd /; rm -rf "$W"; unset BRANCH TARGETS CHANNEL FORBIDDEN_PATHS
}

setup; fix a.txt; run mints_first ok "version=2026-09.1.1" "resume=false"
setup; fix a.txt; "${G[@]}" tag 2026-09.1.1; fix b.txt; "${G[@]}" tag 2026-09.1.2; fix c.txt
run mints_next ok "version=2026-09.1.3"
setup; fix a.txt; "${G[@]}" tag 2026-09.1.1; run resumes ok "version=2026-09.1.1" "resume=true"
setup; git reset -q --hard HEAD~1; run base_not_ancestor fail "not an ancestor"
setup; BRANCH=main run bad_branch_main fail "hotfix/<base>"
setup; BRANCH=hotfix/foo run bad_branch_foo fail "hotfix/<base>"
for c in "target_other fail 2026-06.2" "target_newer fail 2026-10.1" "target_prior_hotfix ok 2026-09.1.1"; do
  read -r name want pin <<< "$c"; setup; git checkout -q main
  echo "  newTag: \"$pin\"" > k8s/overlays/prod/kustomization.yaml; "${G[@]}" commit -qam pin
  git checkout -q hotfix/2026-09.1
  if [ "$want" = fail ]; then run "$name" fail k8s/overlays/prod "$pin"; else run "$name" ok; fi
done
setup; git checkout -q main; echo 'prod: 2026-08.1' > k8s/channels.yaml; "${G[@]}" commit -qam ch
git checkout -q hotfix/2026-09.1; CHANNEL=prod run channel_other fail prod 2026-08.1
setup; git checkout -q main; git rm -q k8s/channels.yaml; "${G[@]}" commit -qm nochan; git checkout -q hotfix/2026-09.1
CHANNEL=prod run channel_file_missing fail "k8s/channels.yaml not found"
setup; echo z > z.txt; "${G[@]}" add -A; "${G[@]}" commit -qm "only on branch"
run patch_missing fail "neither patch-identical" "only on branch"
RS='release: bump prod to 2026-09.1.1 [skip ci]'
ptr() { sed -i "s/newTag: .*/newTag: \"2026-09.1.1\"/" k8s/overlays/prod/kustomization.yaml; "${G[@]}" commit -qam "$RS"; }
setup; fix a.txt; ptr
run skips_release_commits ok "version=2026-09.1.1"
setup; fix alembic/versions/x.py; FORBIDDEN_PATHS='alembic/versions/**' run forbidden fail "alembic/versions/x.py"
setup; fix a.txt; FORBIDDEN_PATHS='alembic/versions/**' run forbidden_clean ok
# base carries two migrations; the hotfix deletes one (patch also on main).
setup; git checkout -q main; mkdir -p alembic/versions; echo a > alembic/versions/a.py; echo b > alembic/versions/b.py
"${G[@]}" add -A; "${G[@]}" commit -qm migs; "${G[@]}" tag -f 2026-09.1 >/dev/null; git checkout -q -B hotfix/2026-09.1
git rm -q alembic/versions/b.py; "${G[@]}" commit -qm "drop b"; sha=$(git rev-parse HEAD)
git checkout -q main; "${G[@]}" cherry-pick "$sha" >/dev/null; git checkout -q hotfix/2026-09.1
FORBIDDEN_PATHS='alembic/versions/**' run forbidden_delete fail "alembic/versions/b.py"
# added then reverted inside the branch (both also on main): net diff is empty.
setup; fix alembic/versions/x.py; "${G[@]}" revert --no-edit HEAD >/dev/null; rsha=$(git rev-parse HEAD)
git checkout -q main; "${G[@]}" cherry-pick "$rsha" >/dev/null; git checkout -q hotfix/2026-09.1
FORBIDDEN_PATHS='alembic/versions/**' run forbidden_reverted fail "alembic/versions/x.py"
# Hotfix patch differs from main's (conflict resolution) but carries a -x trailer.
trailer_case() { # <name> <ok|fail> <on-main|off-main>
  setup; git checkout -q main; echo m > m.txt; "${G[@]}" add -A; "${G[@]}" commit -qm "main fix"
  local msha; msha=$(git rev-parse HEAD)
  git checkout -q hotfix/2026-09.1; echo h > m.txt; "${G[@]}" add -A
  # off-main: an orphan commit, unreachable from main
  [ "$3" = on-main ] || msha=$("${G[@]}" commit-tree -m orphan "$(git hash-object -t tree /dev/null)")
  "${G[@]}" commit -qm "fix m" -m "(cherry picked from commit $msha)"
  run "$1" "$2"
}
trailer_case trailer_on_main ok on-main
trailer_case trailer_not_on_main fail off-main
setup; TARGETS=k8s/overlays/nope run target_missing fail "k8s/overlays/nope/kustomization.yaml not found"
setup; echo z > z.txt; "${G[@]}" add -A; "${G[@]}" commit -qm "release: something"
run release_prefix_not_skipped fail "neither patch-identical" "release: something"

setup; fix a.txt; echo e > evil.txt; "${G[@]}" add -A; "${G[@]}" commit -qm "$RS"
run release_subject_with_payload_refused fail "neither patch-identical"
setup; fix a.txt; echo 'x: y' >> k8s/overlays/prod/kustomization.yaml; ptr
run release_subject_extra_line_refused fail "neither patch-identical"
setup; fix a.txt; ptr; FORBIDDEN_PATHS='k8s/**' run pointer_commit_not_forbidden ok
setup; git checkout -q main; echo '  newTag: "2026-09.10"' > k8s/overlays/prod/kustomization.yaml; "${G[@]}" commit -qam pin
git checkout -q hotfix/2026-09.1; run pin_09_10_refused fail "2026-09.10"
setup; fix a.txt; git checkout -q main; for i in 1 2 3 4 5 6 7 8 9 10; do "${G[@]}" tag 2026-09.1.$i 2026-09.1; done; git checkout -q hotfix/2026-09.1
run mints_after_10 ok "version=2026-09.1.11"
setup; fix a.txt; git checkout -q main; "${G[@]}" tag 2026-09.1.3 2026-09.1; git checkout -q hotfix/2026-09.1
run mints_after_gap ok "version=2026-09.1.4"

[ $fails -eq 0 ] || { echo "$fails case(s) failed"; exit 1; }
