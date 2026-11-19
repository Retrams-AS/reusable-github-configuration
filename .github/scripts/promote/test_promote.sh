#!/usr/bin/env bash
# Runs write-pointers.sh + fast-forward.sh as promote.yml does, against a local
# bare repo behind fake_gh.py. Each case promotes overlays from one GITHUB_SHA.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
fails=0
G=(git -c commit.gpgsign=false -c user.name=t -c user.email=t@t)

setup() {
  W=$(mktemp -d); mkdir "$W/bin" "$W/run"
  printf '#!/bin/sh\nexec python3 %q "$@"\n' "$here/fake_gh.py" > "$W/bin/gh"; chmod +x "$W/bin/gh"
  git init -q --bare -b main "$W/origin"; git clone -q "$W/origin" "$W/w" 2>/dev/null
  for o in fot-dev clinics/forde clinics/haukeland; do
    mkdir -p "$W/w/k8s/overlays/$o"
    printf 'images:\n  - name: fot\n    newTag: "2026-09.1"\n' > "$W/w/k8s/overlays/$o/kustomization.yaml"
  done
  # As fot_server's fot-dev: fot, plus fot-surface (another repo's release)
  # by name and renamed onto it.
  mkdir -p "$W/w/k8s/overlays/multi"
  cat > "$W/w/k8s/overlays/multi/kustomization.yaml" <<'YAML'
images:
  - name: reg/fot
    newTag: "2026-09.1"
  - name: reg/fot-surface
    newTag: "2026-11.2"

  # the builder moves with fot-surface
  - name: fot-surface-builder
    newName: reg/fot-surface
    newTag: "2026-11.2"
YAML
  "${G[@]}" -C "$W/w" add -A; "${G[@]}" -C "$W/w" commit -qm base; git -C "$W/w" push -q origin main
  SHA=$(git -C "$W/w" rev-parse HEAD)
}

# promote <overlay>: one matrix leg, run from $SHA. Sets rc and LANDED.
promote() {
  : > "$W/out"
  ( cd "$W/run" && export PATH="$W/bin:$PATH" FAKE_REPO="$W/origin" FAKE_LOGIN="release-app[bot]" \
      APP_SLUG=release-app REPO=o/r IMAGE="${IMAGE-}" GITHUB_SHA=$SHA DEFAULT_BRANCH=main TARGET="k8s/overlays/$1" \
      CHANNEL= CHANNEL_FILE=k8s/channels.yaml VERSION=2026-11.3 TAG= \
      GITHUB_OUTPUT="$W/out" GITHUB_STEP_SUMMARY=/dev/null
    bash "$here/write-pointers.sh" || exit 1
    COMMIT=$(sed -n 's/^commit=//p' "$W/out") bash "$here/fast-forward.sh" ) > "$W/log" 2>&1
  rc=$?
  LANDED=$(sed -n 's/^commit=//p' "$W/out" | tail -1)
}

# human <file>: a non-promote commit lands on main.
human() {
  git -C "$W/w" pull -q origin main; echo x > "$W/w/$1"
  "${G[@]}" -C "$W/w" add -A; "${G[@]}" -C "$W/w" commit -qm "fix: $1"; git -C "$W/w" push -q origin main
}

tag_of() { git -C "$W/origin" show "main:k8s/overlays/$1/kustomization.yaml" | sed -n 's/.*newTag: //p'; }
# multi_diff: the lines promote changed in the multi overlay since $SHA.
multi_diff() { git -C "$W/origin" diff -U0 "$SHA" main -- k8s/overlays/multi | grep '^[-+] ' | tr '\n' '|'; }

check() {
  if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; cat "$W/log"; fails=$((fails+1)); fi
}

setup
promote fot-dev; check first_lands '[ $rc -eq 0 ]'
promote clinics/forde; check second_from_same_sha_lands '[ $rc -eq 0 ] && [ "$LANDED" = "$(git -C "$W/origin" rev-parse main)" ]'
promote clinics/haukeland; check third_lands '[ $rc -eq 0 ]'
check all_three_bumped '[ "$(tag_of fot-dev)$(tag_of clinics/forde)$(tag_of clinics/haukeland)" = "\"2026-11.3\"\"2026-11.3\"\"2026-11.3\"" ]'
promote clinics/forde; check rerun_is_noop_on_head '[ $rc -eq 0 ] && [ "$LANDED" = "$(git -C "$W/origin" rev-parse main)" ]'
rm -rf "$W"

setup
promote fot-dev; human src.py; before=$(git -C "$W/origin" rev-parse main)
promote clinics/forde
check non_release_commit_fails_closed '[ $rc -ne 0 ] && [ "$(git -C "$W/origin" rev-parse main)" = "$before" ] && grep -q "is not a promote pointer commit" "$W/log"'
rm -rf "$W"

setup
human k8s/overlays/fot-dev/kustomization.yaml; promote clinics/forde
check human_edit_of_overlay_fails_closed '[ $rc -ne 0 ] && grep -q "is not a promote pointer commit" "$W/log"'
rm -rf "$W"

setup
IMAGE=reg/fot promote multi
check image_moves_only_its_entry '[ $rc -eq 0 ] && [ "$(multi_diff)" = "-    newTag: \"2026-09.1\"|+    newTag: \"2026-11.3\"|" ] && git -C "$W/origin" show main:k8s/overlays/multi/kustomization.yaml | sed -n 3p | grep -q 2026-11.3'
IMAGE=reg/fot promote fot-dev; check image_unmatched_fails_closed '[ $rc -ne 0 ] && grep -q "exactly one images" "$W/log"'
rm -rf "$W"

setup
IMAGE=reg/fot-surface promote multi
check renamed_entry_does_not_move '[ $rc -eq 0 ] && [ "$(multi_diff)" = "-    newTag: \"2026-11.2\"|+    newTag: \"2026-11.3\"|" ] && git -C "$W/origin" show main:k8s/overlays/multi/kustomization.yaml | sed -n 5p | grep -q 2026-11.3'
rm -rf "$W"

setup
promote multi; check no_image_bumps_every_entry '[ $rc -eq 0 ] && [ "$(multi_diff | grep -o "+    newTag: \"2026-11.3\"" | wc -l)" = 3 ]'
rm -rf "$W"

exit $fails
