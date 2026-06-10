# Planned reusable components

Specs for the next reusable workflows/actions, written so each is ready to
implement when its gate clears. Context: the org is converging on one delivery
shape (designed 2026-06, proven on `fot_server`): per-merge sha artifacts →
deliberate releases that retag to CalVer `YYYY-MM.PATCH` → promotion PRs
bumping `images.newTag` per channel → Argo CD syncs the merge. CI only writes
git, never the cluster.

House rules for all of these: every `uses:` SHA-pinned with a version comment
(zizmor `unpinned-uses`), untrusted input through `env:`, least-privilege
`permissions:`, `persist-credentials: false` unless the job pushes git.

---

## 1. `release-promote.yml` (reusable workflow)

**Purpose:** the release flow from `fot_server`'s `release.yml`, generalized —
ensure a CalVer tag for HEAD (reuse, else retag the sha artifact), open the
promotion PR for the target channel, create the GitHub Release on prod.

**Gate:** lift only after fot's `release.yml` has executed a full successful
run (3b-1 acceptance). Then convert fot to a caller in the same PR.

**Interface:**

```yaml
on:
  workflow_call:
    inputs:
      image:           # required, string — e.g. registry.digitalocean.com/the-retrams-registry/fot
      release-type:    # required, string — dev | prod | nightly (caller maps its dispatch input / schedule)
      channels-file:   # string, default k8s/channels.yaml
      default-branch:  # string, default master — guard + PR base
    secrets:
      DO_ACCESS_KEY:   # required — registry retag needs auth
```

Caller permissions: `contents: write`, `pull-requests: write`. Caller keeps
the `concurrency: release` group (serializes version computation) and the
`workflow_dispatch` choice input + (optional) nightly cron.

**Behavior (verbatim from fot, parameterized):** ref-guard on
`default-branch` → resolve overlays from `channels-file` (prod = all channels
deduped; skip-and-succeed when empty) → version = CalVer tag on HEAD if
present else next `YYYY-MM.N` → if minting: doctl login + `docker buildx
imagetools create` retag `<image>:<sha7>` → `<image>:<version>` (loud failure
if artifact missing) → push git tag only after the image exists → promotion
PR on branch `release/<version>-<type>`, sed-bump asserted, label
`promotion`, only-skip-if-open-PR-exists → prod: `gh release create
--verify-tag --generate-notes [--notes-start-tag <latest release>]`,
idempotent.

**Notes:** `gh` in a reusable workflow acts on the caller repo with the
caller's token — no extra auth. The repo consuming this must have
`.github/release.yml` (template below) and `k8s/channels.yaml`.

---

## 2. `kustomize-validate.yml` (reusable workflow)

**Purpose:** PR check that every overlay still renders and conforms — a broken
overlay is a broken deploy once Argo tracks the repo.

**Gate:** none — implementable now. First consumers: fot_server, then each
3b-3 onboarded repo.

**Interface:**

```yaml
on:
  workflow_call:
    inputs:
      path:                # string, default k8s/overlays — scanned for */kustomization.yaml
      kubernetes-version:  # string, default "1.33.0" — kubeconform target
      channels-file:       # string, default k8s/channels.yaml ("" disables the channel-contract check)
```

Caller trigger: `pull_request` with `paths: ["k8s/**"]`. Permissions:
`contents: read`.

**Behavior:**
- For each `<path>/*/kustomization.yaml`, skipping directories starting with
  `_` (templates carry `__PLACEHOLDER__` values): `kubectl kustomize <dir> |
  kubeconform -strict -ignore-missing-schemas -kubernetes-version <v>`.
- **Channel contract check:** every overlay listed in `channels-file` must
  contain a quoted `newTag: "..."` line (the release workflow's sed bump
  requires that exact form). This turns the silently-unpromotable-overlay
  failure mode into a PR failure.
- kubectl is preinstalled on runners; install kubeconform from a SHA/checksum
  pinned release binary.

---

## 3. `promotion-changelog.yml` (reusable workflow)

**Purpose:** comment promotion PRs with what they actually ship — the
reviewer-facing half of the release-notes design (the GitHub Release covers
the durable log).

**Gate:** after the first real promotion PR exists to test against (3b-1
acceptance produces one).

**Interface:**

```yaml
on:
  workflow_call: {}   # no inputs needed — everything is derived from the PR diff
```

Caller trigger: `pull_request` (opened/synchronize) with
`paths: ["k8s/overlays/**/kustomization.yaml"]`. Permissions:
`contents: read`, `pull-requests: write`.

**Behavior:** diff base..head for `newTag` changes; for each changed overlay
emit `<overlay>: <old> → <new>` plus `git log --oneline <old>..<new>` (works
for sha7 → CalVer too — both are commits in the repo) and a compare link.
Upsert a single sticky comment (HTML marker), so synchronize updates instead
of stacking comments. Tags not yet fetchable (e.g. release branch race) →
degrade to the compare link only, never fail the PR.

---

## 4. `build-frontend.yml` (reusable workflow)

**Purpose:** fast no-docker build check for the Node frontends (adminpanel,
ytir-frontend, power_precision_dashboard) — frozen-lockfile install + build.

**Gate:** none — implementable now; first consumers when the drafted fleet
PRs reshape in 3b-3.

**Interface:**

```yaml
on:
  workflow_call:
    inputs:
      node-version:       # string, default "22"
      working-directory:  # string, default .
      build-command:      # string, default "" → auto: yarn build / npm run build
```

Caller trigger: `pull_request` with paths (`src/**`, `package.json`,
lockfile, vite/webpack config). Permissions: `contents: read`.

**Behavior:** setup-node (SHA-pinned, cache keyed on the lockfile); detect
the package manager from the lockfile (`yarn.lock` → `yarn install
--frozen-lockfile`, `package-lock.json` → `npm ci`); run the build. Aligns
with the `retrams-conventions` dockerfile skill (frozen installs, pinned
toolchain). Repos whose Dockerfile does the build can instead call
`build-and-push-docr.yml` with `push: false`; this one exists for the faster
inner loop.

---

## 5. `test-python.yml` (reusable workflow)

**Purpose:** `uv run pytest` via the existing `setup-uv` action — the testing
counterpart to `lint-and-format-python.yml`.

**Gate:** none — implementable now (fot_server's per-repo `testing.yml` is
the model and first conversion).

**Interface:**

```yaml
on:
  workflow_call:
    inputs:
      python-version:  # string, default "3.10"
      pytest-args:     # string, default "" — e.g. "-m 'not integration'"
      working-directory: # string, default .
```

Permissions: `contents: read`. Behavior: checkout (no creds) → `setup-uv` →
`uv run pytest <args>` in the working directory.

---

## 6. `templates/` (not workflows)

Per-repo config files the workflows assume; copy on onboarding (they can't be
`workflow_call`'d):

- `templates/release-config.yml` → repo's `.github/release.yml` — generated
  release-notes categories + `exclude: labels: [promotion]`.
- `templates/channels.yaml` → repo's `k8s/channels.yaml` — dev/nightly/stable
  channel map with the fot comments.

The `retrams-conventions` `github-actions` skill points here, so agents copy
the canonical files instead of reconstructing them.

---

## Implementation order

1. **Now / anytime:** `kustomize-validate.yml`, `test-python.yml`,
   `build-frontend.yml`, `templates/`.
2. **After 3b-1 acceptance:** `release-promote.yml` (lift from fot verbatim +
   convert fot to caller), `promotion-changelog.yml`.
3. **Each addition:** update the README usage section and the
   `retrams-conventions` `github-actions` skill's inventory line.
