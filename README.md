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
