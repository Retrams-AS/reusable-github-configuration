# reusable-workflows

Reusable GitHub Actions workflows and composite actions for use across Retrams-AS repositories.

## Reusable Workflows

### Lint Python (`lint-python.yml`)

Runs `ruff check` and `ruff format --check` using [uv](https://github.com/astral-sh/uv).

**Usage in another repository:**

```yaml
jobs:
  lint-and-format:
<<<<<<< HEAD
    uses: Retrams-AS/reusable-workflows/.github/workflows/lint-and-format-python.yml@main
=======
    uses: Retrams-AS/reusable-workflows/.github/workflows/lint-python.yml@main
>>>>>>> b88f915dcf935a5a0f122a0df497f67c5fe06341
    with:
      python-version: "3.12" # optional, defaults to 3.10
```

## Composite Actions

### `setup-uv`

Installs uv, sets up Python, and runs `uv sync`.

**Usage in another repository:**

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: Retrams-AS/reusable-workflows/.github/actions/setup-uv@main
    with:
      python-version: "3.12" # optional, defaults to 3.10
```
