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
| `.github/actions/setup-uv`                     | Composite action — installs uv, sets up Python, runs `uv sync`              |

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

**Usage in another repository:**

```yaml
jobs:
  release:
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/release_calver.yml@<commit-sha> # <version>
    with:
      image: registry.digitalocean.com/the-retrams-registry/<service>
      version: "2026-06.1"
    secrets:
      DO_ACCESS_KEY: ${{ secrets.DO_ACCESS_KEY }}
```

### Promote (`promote.yml`)

Bumps `images.newTag` in one overlay and opens a promotion PR — merging it is
the deploy (Argo CD syncs). Run once per target: `release_calver` mints a
version, `promote` deploys it to dev / prod / a clinic, each independently.

**Usage in another repository:**

```yaml
jobs:
  promote:
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/promote.yml@<commit-sha> # <version>
    with:
      target: k8s/overlays/prod
      version: "2026-06.1"
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
