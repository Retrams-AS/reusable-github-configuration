# reusable-github-configuration

Reusable GitHub Actions workflows and composite actions for use across Retrams-AS repositories.

## Reusable Workflows

### Lint Python (`lint-python.yml`)

Runs `ruff check` and `ruff format --check` using [uv](https://github.com/astral-sh/uv).

**Usage in another repository:**

```yaml
jobs:
  lint-and-format:
    # Pin to a released commit SHA. See "Releasing" for how to find the latest.
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/lint-and-format-python.yml@<commit-sha> # <version>
    with:
      python-version: "3.12" # optional, defaults to 3.10
```

### Zizmor

Runs Zizmor for GitHub Actions security analysis. Get feedback on your workflow yaml's.

This is not something to use and maintain everywhere, this is just a workflow with a
Zizmor action.

This is for making an org Ruleset and check "Require workflows to pass before merging"
with link to this workflow. Maintain in one repo, and govern through Rulesets.

If GitHub Advanced Security, then update workflow to get results in Security overview.

## Composite Actions

### `setup-uv`

Installs uv, sets up Python, and runs `uv sync`.

**Usage in another repository:**

```yaml
steps:
  - uses: actions/checkout@v6
  # Pin to a released commit SHA. See "Releasing" for how to find the latest.
  - uses: Retrams-AS/reusable-github-configuration/.github/actions/setup-uv@<commit-sha> # <version>
    with:
      python-version: "3.12" # optional, defaults to 3.10
```

## Releasing

Consumers should pin to a released commit SHA, not `@main`. Cutting a release tags
the current `main` so there is a stable, immutable hash to pin against.

### Versioning

This repo is an internal **library** (reusable workflows + a composite action with a
compatibility contract), so it uses **SemVer**: `vMAJOR.MINOR.PATCH` (for example
`v0.1.0`, `v0.1.1`, `v1.0.0`). Deployable images elsewhere in the org use CalVer; see
the `digital_ocean_deployment` design notes for that distinction.

Pick the bump by asking *"if a consumer moved their pinned SHA to this release, would
they have to change their `with:` block?"*

- **patch** — bug/behaviour fix, no input changes.
- **minor** — backwards-compatible change (e.g. a new optional input).
- **major** — breaking change (a renamed/removed/required input).

The tag is a human-readable marker; what consumers actually receive is the commit SHA
they pin, so the version is an informational signal rather than an enforced range.

### Cut a release

Releases are created manually — nothing is tagged automatically on merge.

1. Merge your changes to `main`.
2. Go to **Actions → Release (SemVer) → Run workflow**, with the branch set to `main`.
   Choose the **bump** (`patch` / `minor` / `major`) and optionally write a **notes**
   summary.
3. The workflow computes the next version from the highest existing tag, creates the
   tag, and publishes a **GitHub Release** whose notes are an auto-generated changelog
   of merged PRs since the previous release (your summary, if any, is prepended — and
   you can refine the notes in the Release UI afterwards). The run **summary** lists
   the new tag, commit SHA, release URL, and ready-to-paste pin lines.

The workflow refuses to run if:

- it is dispatched from a branch other than `main`, or
- the current `main` commit is already released (nothing changed since the last
  release). A previously _failed_ release run can simply be re-run, since it left no
  tag behind.

### Find the hash for a release

Either copy it from the release run's job summary, or resolve any tag to its SHA:

```bash
git ls-remote https://github.com/Retrams-AS/reusable-github-configuration <version>
```

Then pin consumers to that SHA with the SemVer tag as a trailing comment:

```yaml
uses: Retrams-AS/reusable-github-configuration/.github/actions/setup-uv@<commit-sha> # <version>
```
