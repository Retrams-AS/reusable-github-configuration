# reusable-github-configuration

Reusable GitHub Actions workflows and composite actions for use across Retrams-AS repositories.

## Reusable Workflows

### Lint Python (`lint-python.yml`)

Runs `ruff check` and `ruff format --check` using [uv](https://github.com/astral-sh/uv).

**Usage in another repository:**

```yaml
jobs:
  lint-and-format:
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/lint-and-format-python.yml@main
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
  - uses: Retrams-AS/reusable-github-configuration/.github/actions/setup-uv@main
    with:
      python-version: "3.12" # optional, defaults to 3.10
```
