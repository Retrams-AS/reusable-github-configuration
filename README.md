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
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/lint-and-format-python.yml@<commit-sha> # <calver>
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
  - uses: Retrams-AS/reusable-github-configuration/.github/actions/setup-uv@<commit-sha> # <calver>
    with:
      python-version: "3.12" # optional, defaults to 3.10
```

## Releasing

Consumers should pin to a released commit SHA, not `@main`. Cutting a release tags
the current `main` so there is a stable, immutable hash to pin against.

### Versioning

Releases use CalVer: **`YYYY-MM.PATCH`** (for example `2026-06.0`, `2026-06.1`,
`2026-07.0`). `PATCH` starts at `0` each month and increments for each additional
release within the same year-month.

### Cut a release

Releases are created manually — nothing is tagged automatically on merge.

1. Merge your changes to `main`.
2. Go to **Actions → Release (CalVer) → Run workflow**, with the branch set to `main`.
3. The workflow computes the next `YYYY-MM.PATCH`, creates the tag, and prints the
   new tag, commit SHA, and ready-to-paste pin lines in the run's **summary**.

The workflow refuses to run if:

- it is dispatched from a branch other than `main`, or
- the current `main` commit is already released (nothing changed since the last
  release). A previously *failed* release run can simply be re-run, since it left no
  tag behind.

### Find the hash for a release

Either copy it from the release run's job summary, or resolve any tag to its SHA:

```bash
git ls-remote https://github.com/Retrams-AS/reusable-github-configuration <calver>
```

Then pin consumers to that SHA with the CalVer tag as a trailing comment:

```yaml
uses: Retrams-AS/reusable-github-configuration/.github/actions/setup-uv@<commit-sha> # <calver>
```
