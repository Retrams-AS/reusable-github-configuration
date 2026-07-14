# reusable-github-configuration

Shared GitHub Actions workflows and composite actions for Retrams-AS repositories —
maintained here once and reused everywhere else.

> **Pinning:** the snippets below use `@main` for brevity. In repos checked by
> zizmor (`unpinned-uses` blanket policy), pin `uses:` references to a commit
> SHA with a comment, e.g. `...@<sha> # main 2026-06`, and bump deliberately.

## Reusable Workflows

### Lint Python (`lint-and-format-python.yml`)
See [Releasing](#releasing) for how to find a SHA.

## What's here

| File                                           | What it does                                                                |
| ---------------------------------------------- | --------------------------------------------------------------------------- |
| `.github/workflows/lint-and-format-python.yml` | Reusable workflow — runs `ruff check` and `ruff format --check` via uv      |
| `.github/workflows/zizmor.yml`                 | Reusable workflow — scans your Actions YAML for security issues with Zizmor |
| `.github/workflows/pr-title-check.yml`         | Reusable workflow — checks each PR title is a valid Conventional Commit     |
| `.github/workflows/lint-and-format-node.yml`   | Reusable workflow — runs `yarn lint` and `yarn format` (ESLint + Prettier)  |
| `.github/workflows/test-node.yml`              | Reusable workflow — runs `yarn test:unit` (Vitest)                          |
| `.github/workflows/e2e-cypress.yml`            | Reusable workflow — runs Cypress e2e (build → preview → wait → run)         |
| `.github/actions/setup-uv`                     | Composite action — installs uv, sets up Python, runs `uv sync`              |
| `.github/actions/setup-node-yarn`              | Composite action — Corepack + Node + `yarn install --immutable`             |

## Reusable workflows

### Lint and format (`lint-and-format-python.yml`)

Runs `ruff check` and `ruff format --check` using [uv](https://github.com/astral-sh/uv).

```yaml
jobs:
  lint-and-format:
    # Pin to a released commit SHA. See "Releasing" for how to find the latest.
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/lint-and-format-python.yml@<commit-sha> # <calver>
    with:
      python-version: "3.12" # optional, defaults to "3.10"
```

### Lint and format — Node (`lint-and-format-node.yml`)

Runs `yarn lint` (ESLint) and `yarn format` (Prettier) for Yarn/Corepack
frontends. **Script contract:** the caller's `package.json` must expose `lint`
and `format` scripts.

```yaml
jobs:
  lint-and-format:
    permissions:
      contents: read
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/lint-and-format-node.yml@<commit-sha> # <version>
    with:
      node-version: "20"      # optional, defaults to "20"
      enable-scripts: false   # optional, defaults to false (skips install build scripts)
```

### Test — Node (`test-node.yml`)

Runs `yarn test:unit` (Vitest). **Script contract:** the caller must expose a
`test:unit` script.

```yaml
jobs:
  unit:
    permissions:
      contents: read
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/test-node.yml@<commit-sha> # <version>
    with:
      node-version: "20"      # optional, defaults to "20"
      enable-scripts: false   # optional, defaults to false (skips install build scripts)
```

### E2E — Cypress (`e2e-cypress.yml`)

Builds the app, serves it, waits for it, and runs Cypress specs. **Script
contract:** the `build-command`/`start-command` (defaults `yarn build` /
`yarn preview`) must produce and serve the app at `wait-on`.

```yaml
jobs:
  e2e:
    permissions:
      contents: read
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/e2e-cypress.yml@<commit-sha> # <version>
    with:
      node-version: "20"                   # optional
      build-command: "yarn build"          # optional
      start-command: "yarn preview"        # optional
      wait-on: "http://localhost:4173"     # optional
      wait-on-timeout: 120                 # optional
```

### Build and push image to DOCR (`build-and-push-docr.yml`)

Builds the caller's Dockerfile and (optionally) pushes it to the DigitalOcean
Container Registry tagged with the 7-char commit sha. Callers own the triggers
and path filters; with `push: false` it is a build-only PR check. Pair with a
release flow that promotes sha artifacts to immutable version tags by retagging
(reference implementation: `fot_server`).

**Usage in another repository:**

```yaml
jobs:
  build:
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/build-and-push-docr.yml@main
    with:
      image: registry.digitalocean.com/the-retrams-registry/<service>
      push: ${{ github.event_name != 'pull_request' }}
    secrets:
      DO_ACCESS_KEY: ${{ secrets.DO_ACCESS_KEY }}
```

### Release (CalVer) (`release_calver.yml`)

Mints a CalVer `YYYY-MM.N` version by retagging the existing `<image>:<sha7>`
artifact (never rebuilds), tagging the commit, and (optionally) cutting a
GitHub Release. Build-once/promote-many; pair with `promote.yml`.

The `version` input is optional. When omitted, the workflow mints it: current
UTC `YYYY-MM`, patch = highest existing `N` for that month + 1 (first release
of a month is `.1`). Re-dispatching on a commit that already carries a CalVer
tag reuses that version instead of minting a new one, so re-runs are safe.
Either way the resolved version is exposed as the `version` **output** — chain
`promote` on it (see below). Pass `version` explicitly only for a deliberate
override.

**Usage in another repository** (with a chained promote to dev):

```yaml
jobs:
  release:
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/release_calver.yml@<commit-sha> # <version>
    with:
      image: registry.digitalocean.com/the-retrams-registry/<service>
    secrets:
      DO_ACCESS_KEY: ${{ secrets.DO_ACCESS_KEY }}

  promote-dev:
    needs: release
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/promote.yml@<commit-sha> # <version>
    with:
      target: k8s/overlays/dev
      version: ${{ needs.release.outputs.version }}
    secrets:
      app-id: ${{ secrets.RELEASE_APP_ID }}
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}
```

### Promote (`promote.yml`)

Bumps `images.newTag` in one overlay by committing straight to the default
branch — that commit is the deploy (Argo CD syncs). Run once per target:
`release_calver` mints a version, `promote` deploys it to dev / prod / a
clinic, each independently. Rollback = revert the bump commit.

The commit is made with the org's dedicated **Release App** (a GitHub App)
that must be installed on the repo and be a **bypass actor** on the default
branch's ruleset. The commit shows as Verified and carries `[skip ci]`, so
build/test/lint don't run on it.

**One-time App setup** (org level, once):

1. Org settings → Developer settings → GitHub Apps → New App (**Release App**).
   Repository permission: **Contents: Read and write**. Nothing else;
   webhook off.
2. Generate a private key; note the App ID.
3. Install the App on each service repo that promotes.
4. In each such repo's default-branch **ruleset**, add the App as a
   **bypass actor**.
5. Store the App ID and PEM as secrets (org-level with repo access, or
   per-repo): `RELEASE_APP_ID`, `RELEASE_APP_PRIVATE_KEY`.

**Usage in another repository:**

```yaml
jobs:
  promote:
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/promote.yml@<commit-sha> # <version>
    with:
      target: k8s/overlays/prod
      version: "2026-06.1"
    secrets:
      app-id: ${{ secrets.RELEASE_APP_ID }}
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}
```

### Zizmor (`zizmor.yml`)

Statically analyses GitHub Actions workflows for security problems with Zizmor.

Don't copy this workflow into every repo. It is enforced org-wide. One copy to maintain; Rulesets govern the rest.

**If we upgrade to GitHub Advanced Security, we need to update and extend the workflow to upload results to security overview.**

### PR title check (`pr-title-check.yml`)

Fails any PR whose title isn't a valid
[Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/) — this is what lets
releases read their version straight from PR titles (see [Releasing](#releasing)).

Like Zizmor, keep one copy and require it org-wide via a Ruleset.

## Composite actions

### `docr-login`

The org-standard way to authenticate CI to the DigitalOcean Container Registry:
installs doctl and runs `doctl registry login --expiry-seconds`, which issues
**short-lived** registry credentials. Do **not** use `docker/login-action` with
the raw API token — it stores the long-lived token in the runner's docker
config for the whole job. (`digitalocean/action-doctl` is actively maintained,
not deprecated, and this is the auth flow DigitalOcean's own docs use.)

**Usage in another repository:**

```yaml
steps:
  - uses: Retrams-AS/reusable-github-configuration/.github/actions/docr-login@main
    with:
      token: ${{ secrets.DO_ACCESS_KEY }}
      expiry-seconds: "1200" # optional, defaults to 1200
```

### `setup-uv`

Installs uv, sets up Python, and runs `uv sync`.

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: Retrams-AS/reusable-github-configuration/.github/actions/setup-uv@<commit-sha> # <version>
    with:
      python-version: "3.12" # optional, defaults to "3.10"
```

### `setup-node-yarn`

Enables Corepack, sets up Node with the Yarn cache, and runs
`yarn install --immutable`. The Node analog of `setup-uv`. Checkout the repo
first (this action does not).

```yaml
steps:
  - uses: actions/checkout@v6
  - uses: Retrams-AS/reusable-github-configuration/.github/actions/setup-node-yarn@<commit-sha> # <version>
    with:
      node-version: "20"      # optional, defaults to "20"
      enable-scripts: "false" # optional, defaults to "false"
```

## Releasing

### Versioning is derived from PR titles

You never pick the bump — it's read from the
[Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/) type of the PRs merged since the last release:

| PR title type                          | Bump      | Meaning                                                        |
| -------------------------------------- | --------- | -------------------------------------------------------------- |
| `feat!:` / `fix!:` (any type with `!`) | **major** | Breaking change — a renamed, removed, or newly required input. |
| `feat:`                                | **minor** | Backwards-compatible change, e.g. a new optional input.        |
| `fix:` / `perf:`                       | **patch** | Bug or behaviour fix, no input changes.                        |
| `docs:` / `chore:` / `ci:` / …         | none      | Not releasable on its own.                                     |

Highest type across the PRs wins; `pr-title-check` enforces the format.

### Cut a release

**Actions → Release (SemVer) → Run workflow** on `main` — nothing to fill in (or set
**version_override** for a deliberate version like `v1.0.0`). It tags the commit and
publishes a **GitHub Release** with an auto-generated changelog; the run summary has the
tag, SHA, and pin lines.

It refuses to run off other branches than `main`, or with no releasable PRs since the last tag (use
`version_override` to force one). Releases are immutable via GitHub's **Immutable
releases** setting.

### Find the hash for a release

From the run summary, or resolve any tag:

```bash
git ls-remote https://github.com/Retrams-AS/reusable-github-configuration <version>
```

Then pin to that SHA, with the tag as a trailing comment: `@<commit-sha> # <version>`.
