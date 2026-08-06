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
| `.github/workflows/actionlint.yml`             | Reusable workflow — lints Actions YAML for correctness (actionlint + shellcheck) |
| `.github/workflows/pr-title-check.yml`         | Reusable workflow — checks each PR title is a valid Conventional Commit     |
| `.github/workflows/lint-and-format-node.yml`   | Reusable workflow — runs `yarn lint` and `yarn format` (ESLint + Prettier)  |
| `.github/workflows/test-node.yml`              | Reusable workflow — runs `yarn test:unit` (Vitest)                          |
| `.github/workflows/e2e-cypress.yml`            | Reusable workflow — runs Cypress e2e (build → preview → wait → run)         |
| `.github/workflows/publish-python-package.yml` | Reusable workflow — bumps, builds and publishes a Python package to pypi.retrams.no |
| `.github/actions/setup-uv`                     | Composite action — installs uv, sets up Python, runs `uv sync`              |
| `.github/actions/setup-node-yarn`              | Composite action — Corepack + Node + `yarn install --immutable`             |
| `.github/actions/openbao-index-token`          | Composite action — exchanges GitHub OIDC for a short-lived pypi.retrams.no token, as an output, `UV_INDEX_*` env vars, or a netrc |

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
      private-index: true    # optional, defaults to false — authenticate to pypi.retrams.no
      bao-ca: ${{ vars.BAO_SCANNER_CA }} # required when private-index is true
    permissions:
      contents: read
      id-token: write
```

Both scopes are required, whether or not `private-index` is set.

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
      private-index: true    # optional, defaults to false
      bao-ca: ${{ vars.BAO_SCANNER_CA }} # required when private-index is true
    permissions:
      contents: read
      id-token: write
    secrets:
      DO_ACCESS_KEY: ${{ secrets.DO_ACCESS_KEY }}
```

With `private-index: true` the build gets a `netrc` BuildKit secret. Consume it on the
dependency-install layer. The secret mounts as uid 0, mode 0400, so that layer must run
before any switch to a non-root `USER`, or the mount needs `uid=`:

```dockerfile
RUN --mount=type=secret,id=netrc,target=/tmp/netrc \
    NETRC=/tmp/netrc uv sync --frozen --no-dev
```

The identical line builds locally with
`docker build --secret id=netrc,src=$HOME/.netrc .`.

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

### Publish Python package (`publish-python-package.yml`)

Bumps the version from a `major`/`minor`/`patch` choice, builds with `uv`,
publishes to `pypi.retrams.no`, commits the bump, tags it, and cuts a GitHub
Release with the wheel and sdist attached. **CI stores no credential** — the
job's GitHub OIDC token is exchanged with OpenBao for a JWT that expires in
minutes. The published version is exposed as the `version` output.

Publishing happens *before* the repo is written to. A failed publish leaves
nothing to unwind; a publish that succeeds while a later step fails heals on
re-run, because the same bump computes the same version and the upload is
skipped as already-present.

**Three things must line up, and all fail closed in ways that read as a
permissions problem:**

1. The job runs in a GitHub **Environment**, and its name forms half of the OIDC
   subject OpenBao binds (`repo:Retrams-AS/<repo>:environment:<name>`). Default
   `release`. Renaming it breaks publishing.
2. The OIDC **audience** must equal the OpenBao role's `bound_audiences`
   (`package-index`).
3. `bao-ca` must carry the CA that issued OpenBao's listener certificate
   (`vars.BAO_SCANNER_CA`). `bao.retrams.no` is privately issued, so a runner
   trusting only public roots fails the TLS handshake before any auth happens.

**Adding a new publishing repo is an OpenBao change, not just a workflow file.**
The role's `bound_claims.sub` lists each permitted subject; see the platform
runbook `openbao-package-index-auth.md` §6. Writing that role replaces it
wholesale, so read the existing list and extend it.

Uses the same **Release App** as `promote.yml` (see its one-time setup); the App
must be installed on the publishing repo.

**Usage in another repository:**

```yaml
on:
  workflow_dispatch:
    inputs:
      bump:
        description: Which part of the version to increment
        required: true
        type: choice
        options: [patch, minor, major]
        default: patch

permissions: {}

jobs:
  release:
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/publish-python-package.yml@<commit-sha> # <version>
    permissions:
      id-token: write
      contents: read
    with:
      bump: ${{ inputs.bump }}
      bao-ca: ${{ vars.BAO_SCANNER_CA }}
    secrets:
      app-id: ${{ secrets.RELEASE_APP_ID }}
      app-private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}
```

### Zizmor (`zizmor.yml`)

Statically analyses GitHub Actions workflows for security problems with Zizmor.

Don't copy this workflow into every repo. It is enforced org-wide. One copy to maintain; Rulesets govern the rest.

**If we upgrade to GitHub Advanced Security, we need to update and extend the workflow to upload results to security overview.**

### actionlint (`actionlint.yml`)

Correctness linting for Actions YAML — undefined contexts, malformed expressions,
bad `needs:` references, and shellcheck findings inside `run:` blocks. The security
counterpart is `zizmor.yml`. Runs on this repo's own pushes and PRs; callable from
another repo with `uses:`.

Locally:

```bash
uvx --from actionlint-py==1.7.12.24 --with shellcheck-py==0.11.0.1 actionlint -ignore 'property "workflow_(repository|sha)" is not defined'
```

The `-ignore` is required: actionlint does not model the `job` context, so the
`._shared` self-checkout pattern reports a false "property not defined".

CI runs this exact command, shellcheck pin included.

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

This action knows nothing about the private index. To install first-party wheels, run
`openbao-index-token` with `uv-index-name` **before** it — the credentials arrive
through the job environment.

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

### `openbao-index-token`

Exchanges the job's GitHub OIDC token for a short-lived JWT accepted by
`pypi.retrams.no`. Two calls, not one: `auth/jwt/login` returns an *opaque*
OpenBao service token the index cannot verify, and its only job is to authorise
`identity/oidc/token`, which mints the RS256 JWT that JWKS verification accepts.

`publish-python-package.yml` uses this for the publish path. For reads, set
`uv-index-name` and the action exports the credentials uv looks for, so `setup-uv`
and any later `uv` command pick them up with no further wiring:

```yaml
jobs:
  install:
    permissions:
      id-token: write
      contents: read # also required — see the note under the Lint example above
    steps:
      - uses: actions/checkout@v6
      - uses: Retrams-AS/reusable-github-configuration/.github/actions/openbao-index-token@<commit-sha> # <version>
        with:
          bao-ca: ${{ vars.BAO_SCANNER_CA }}
          uv-index-name: retrams
      - uses: Retrams-AS/reusable-github-configuration/.github/actions/setup-uv@<commit-sha> # <version>
```

Defaults mint a **read-only** token. Publishing overrides `jwt-role` and
`identity-role`, and its OpenBao role additionally requires the job to run in a GitHub
Environment named `release`. For a Docker build, set `netrc-file` instead of
`uv-index-name` and pass the resulting path to BuildKit as a `netrc` secret. Point
`netrc-file` at a file *under* `${{ runner.temp }}`, e.g. `${{ runner.temp }}/netrc` —
not a path inside the workspace: this is a composite action, so it cannot declare a
`post:` step to clean the file up, and it persists until the job ends — long enough
for a workspace path to be swept into an artifact upload.

Setting `private-index: true` on a caller with no matching `pyproject.toml` entry
fails silently: the credentials are exported but nothing tells uv to use them, so it
resolves against public PyPI instead. The caller sees a "package not found" — or,
worse, a same-named public package installs instead of the real one — with nothing
pointing at the real cause. The `pyproject.toml` needs both a `[[tool.uv.index]]`
entry named `retrams` with `explicit = true` (so a first-party name can never be
silently satisfied from public PyPI) and a `[tool.uv.sources]` entry that routes the
package to it. See the `retrams-package-index` repo's own README for the canonical
snippet.

## Releasing

### Pick the bump

The release takes a **patch / minor / major** dropdown, defaulting to `patch`, applied to the
highest existing `vX.Y.Z` tag.

| Bump      | When                                                                        |
| --------- | --------------------------------------------------------------------------- |
| **major** | A consumer must change something before bumping their pin — a renamed, removed or newly required input, a changed default, or a new permission the caller must grant. |
| **minor** | Backwards-compatible addition, e.g. a new optional input.                   |
| **patch** | Fix that needs nothing from consumers.                                      |

Conventional Commit titles are enforced by `pr-title-check` and generate the changelog. They do
not choose the version.

### Cut a release

**Actions → Release (SemVer) → Run workflow** on `main`, choose the bump, run. It tags the
commit and publishes a **GitHub Release** with an auto-generated changelog; the run summary has
the tag, SHA, and pin lines.

It refuses to run off any branch other than `main`, and fails if the computed tag already
exists. There is no way to force an arbitrary version — push the tag by hand if you need one.
Releases are immutable via GitHub's **Immutable releases** setting.

### Find the hash for a release

From the run summary, or resolve any tag:

```bash
git ls-remote https://github.com/Retrams-AS/reusable-github-configuration <version>
```

Then pin to that SHA, with the tag as a trailing comment: `@<commit-sha> # <version>`.
