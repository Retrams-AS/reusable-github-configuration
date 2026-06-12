# reusable-github-configuration

Shared GitHub Actions workflows and composite actions for Retrams-AS repositories —
maintained here once and reused everywhere else.

**Always pin to a released commit SHA, never `@main`.**

```yaml
uses: Retrams-AS/reusable-github-configuration/.github/actions/setup-uv@<commit-sha> # <version>
```

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
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/lint-and-format-python.yml@<commit-sha> # <version>
    with:
      python-version: "3.12" # optional, defaults to "3.10"
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
