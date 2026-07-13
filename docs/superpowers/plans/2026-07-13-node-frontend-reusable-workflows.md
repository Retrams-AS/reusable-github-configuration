# Node/Yarn Frontend Reusable CI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract scanner-ui's Yarn-based CI (lint/format, unit tests, Cypress e2e) into this repo as one composite action + three reusable workflows, mirroring the existing Python setup.

**Architecture:** A `setup-node-yarn` composite action encapsulates the shared preamble (Corepack → Node → immutable install). Three reusable workflows (`lint-and-format-node.yml`, `test-node.yml`, `e2e-cypress.yml`) each check out the caller, then check themselves out into `._shared/` at `job.workflow_sha` (version-locking the action to the workflow), and run the relevant `yarn` scripts.

**Tech Stack:** GitHub Actions (reusable workflows + composite action), Yarn 4 via Corepack, Node 20, Vitest, Cypress. Verified with `uvx zizmor` and a PyYAML parse.

## Global Constraints

Copied verbatim from the spec — every task must honour these:

- Every `uses:` SHA-pinned with a version comment (zizmor `unpinned-uses`). Reuse these already-vetted pins, do not introduce new ones:
  - `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2`
  - `actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e # v6.4.0`
  - `cypress-io/github-action@fa4a118725a8f001170d49631ea89e5d66fee626 # v7.4.1`
- `persist-credentials: false` on every checkout (no job pushes git).
- Least-privilege `permissions: contents: read` on every reusable job.
- Yarn only: Corepack + `yarn install --immutable`. No package-manager detection.
- Hardcoded script contract — consumers must expose: `yarn lint`, `yarn format`, `yarn test:unit`, `yarn build`, `yarn preview`.
- `node-version` default `"20"` everywhere.

## Verification tooling (used by every task)

No `actionlint`/`zizmor` on PATH, but `uv` is. Two checks:

```bash
# 1. YAML parse validity
uvx --with pyyaml python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1])); print('YAML OK:', sys.argv[1])" <file>

# 2. Security gate — same thresholds as .github/workflows/zizmor.yml
uvx zizmor --min-severity medium --min-confidence medium <file>
```

If zizmor complains about online audits (no token), it degrades gracefully; the offline audits (`template-injection`, `unpinned-uses`, `excessive-permissions`) are the ones that matter here. Set `GH_TOKEN=$(gh auth token)` if you want the online audits too.

**Runtime ceiling (be honest):** this repo has no `package.json`, so the Node workflows cannot execute here. End-to-end proof happens only when scanner-ui adopts the callers (Task 6, a separate follow-up PR). Static checks are the ceiling for this repo.

## File Structure

- Create: `.github/actions/setup-node-yarn/action.yml` — the shared setup preamble.
- Create: `.github/workflows/lint-and-format-node.yml` — `yarn lint` + `yarn format`.
- Create: `.github/workflows/test-node.yml` — `yarn test:unit`.
- Create: `.github/workflows/e2e-cypress.yml` — Cypress build/preview/wait/run.
- Modify: `README.md` — table rows + usage sections.
- Deliver in chat (NOT committed): scanner-ui `lint-and-format.yml` + `run-tests.yml` caller snippets.

---

### Task 1: `setup-node-yarn` composite action

**Files:**
- Create: `.github/actions/setup-node-yarn/action.yml`

**Interfaces:**
- Consumes: nothing (the calling workflow checks out the repo first, exactly like `setup-uv`).
- Produces: composite action referenced as `./._shared/.github/actions/setup-node-yarn` with inputs `node-version` (string, default `"20"`) and `enable-scripts` (string, default `"false"`). After it runs, `node`, `yarn` (v4 via Corepack), and installed `node_modules`/`.yarn` are available to later steps.

- [ ] **Step 1: Write the action file**

```yaml
name: Setup Node + Yarn
description: Enable Corepack, set up Node with Yarn cache, and install dependencies from an immutable lockfile

inputs:
  node-version:
    description: Node.js version to use
    default: "20"
  enable-scripts:
    description: >-
      Value for YARN_ENABLE_SCRIPTS during install. "false" (default) skips
      package build scripts (e.g. an Electron native rebuild) that lint/test
      don't need; set "true" when a postinstall must run.
    default: "false"

runs:
  using: composite
  steps:
    - name: Enable Corepack
      # Activates the Yarn version pinned in package.json#packageManager.
      shell: bash
      run: corepack enable

    - name: Set up Node
      uses: actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e # v6.4.0
      with:
        node-version: ${{ inputs.node-version }}
        cache: yarn

    - name: Install dependencies
      shell: bash
      run: yarn install --immutable
      env:
        YARN_ENABLE_SCRIPTS: ${{ inputs.enable-scripts }}
```

- [ ] **Step 2: Verify YAML parses**

Run: `uvx --with pyyaml python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1])); print('YAML OK:', sys.argv[1])" .github/actions/setup-node-yarn/action.yml`
Expected: `YAML OK: .github/actions/setup-node-yarn/action.yml`

- [ ] **Step 3: Verify zizmor is clean**

Run: `uvx zizmor --min-severity medium --min-confidence medium .github/actions/setup-node-yarn/action.yml`
Expected: `No findings` (or exit 0 / only informational). Any `medium`+ finding must be fixed before committing.

- [ ] **Step 4: Commit**

```bash
git add .github/actions/setup-node-yarn/action.yml
git commit -m "feat: add setup-node-yarn composite action"
```

---

### Task 2: `lint-and-format-node.yml` reusable workflow

**Files:**
- Create: `.github/workflows/lint-and-format-node.yml`

**Interfaces:**
- Consumes: `setup-node-yarn` action from Task 1 (via the `._shared` self-checkout).
- Produces: reusable workflow callable as `.github/workflows/lint-and-format-node.yml` with inputs `node-version` (string, default `"20"`) and `enable-scripts` (boolean, default `false`). Runs `yarn lint` then `yarn format`.

- [ ] **Step 1: Write the workflow file**

```yaml
name: Lint and format (Node)

on:
  workflow_call:
    inputs:
      node-version:
        description: Node.js version to use
        type: string
        default: "20"
      enable-scripts:
        description: Run package install scripts (sets YARN_ENABLE_SCRIPTS)
        type: boolean
        default: false

jobs:
  lint-and-format:
    name: ESLint + Prettier
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout caller repository
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false

      - name: Checkout shared actions at the called ref
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          # job.workflow_repository/sha resolve this reusable workflow's repo and
          # the exact SHA the caller pinned, so the composite action matches the
          # workflow version. (Not available on GitHub Enterprise Server.)
          repository: ${{ job.workflow_repository }}
          ref: ${{ job.workflow_sha }}
          path: ._shared
          persist-credentials: false

      - name: Set up Node + Yarn
        uses: ./._shared/.github/actions/setup-node-yarn
        with:
          node-version: ${{ inputs.node-version }}
          enable-scripts: ${{ inputs.enable-scripts }}

      - name: Lint (ESLint)
        run: yarn lint

      - name: Format check (Prettier)
        run: yarn format
```

- [ ] **Step 2: Verify YAML parses**

Run: `uvx --with pyyaml python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1])); print('YAML OK:', sys.argv[1])" .github/workflows/lint-and-format-node.yml`
Expected: `YAML OK: .github/workflows/lint-and-format-node.yml`

- [ ] **Step 3: Verify zizmor is clean**

Run: `uvx zizmor --min-severity medium --min-confidence medium .github/workflows/lint-and-format-node.yml`
Expected: exit 0, no `medium`+ findings.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/lint-and-format-node.yml
git commit -m "feat: add lint-and-format-node reusable workflow"
```

---

### Task 3: `test-node.yml` reusable workflow (unit)

**Files:**
- Create: `.github/workflows/test-node.yml`

**Interfaces:**
- Consumes: `setup-node-yarn` action from Task 1.
- Produces: reusable workflow callable as `.github/workflows/test-node.yml` with inputs `node-version` (string, default `"20"`) and `enable-scripts` (boolean, default `false`). Runs `yarn test:unit`.

- [ ] **Step 1: Write the workflow file**

```yaml
name: Tests (Node)

on:
  workflow_call:
    inputs:
      node-version:
        description: Node.js version to use
        type: string
        default: "20"
      enable-scripts:
        description: Run package install scripts (sets YARN_ENABLE_SCRIPTS)
        type: boolean
        default: false

jobs:
  unit:
    name: Unit (Vitest)
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout caller repository
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false

      - name: Checkout shared actions at the called ref
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          repository: ${{ job.workflow_repository }}
          ref: ${{ job.workflow_sha }}
          path: ._shared
          persist-credentials: false

      - name: Set up Node + Yarn
        uses: ./._shared/.github/actions/setup-node-yarn
        with:
          node-version: ${{ inputs.node-version }}
          enable-scripts: ${{ inputs.enable-scripts }}

      - name: Run unit tests
        # GitHub Actions sets CI=true, so Vitest runs once (no watch mode).
        run: yarn test:unit
```

- [ ] **Step 2: Verify YAML parses**

Run: `uvx --with pyyaml python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1])); print('YAML OK:', sys.argv[1])" .github/workflows/test-node.yml`
Expected: `YAML OK: .github/workflows/test-node.yml`

- [ ] **Step 3: Verify zizmor is clean**

Run: `uvx zizmor --min-severity medium --min-confidence medium .github/workflows/test-node.yml`
Expected: exit 0, no `medium`+ findings.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/test-node.yml
git commit -m "feat: add test-node reusable workflow"
```

---

### Task 4: `e2e-cypress.yml` reusable workflow

**Files:**
- Create: `.github/workflows/e2e-cypress.yml`

**Interfaces:**
- Consumes: `setup-node-yarn` action from Task 1.
- Produces: reusable workflow callable as `.github/workflows/e2e-cypress.yml` with inputs `node-version` (string, `"20"`), `build-command` (string, `yarn build`), `start-command` (string, `yarn preview`), `wait-on` (string, `http://localhost:4173`), `wait-on-timeout` (number, `120`).

- [ ] **Step 1: Write the workflow file**

```yaml
name: E2E (Cypress)

on:
  workflow_call:
    inputs:
      node-version:
        description: Node.js version to use
        type: string
        default: "20"
      build-command:
        description: Command Cypress runs to build the app before serving
        type: string
        default: yarn build
      start-command:
        description: Command Cypress runs to serve the built app
        type: string
        default: yarn preview
      wait-on:
        description: URL Cypress waits for before running specs
        type: string
        default: http://localhost:4173
      wait-on-timeout:
        description: Seconds to wait for the server before failing
        type: number
        default: 120

jobs:
  e2e:
    name: E2E (Cypress)
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout caller repository
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false

      - name: Checkout shared actions at the called ref
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          repository: ${{ job.workflow_repository }}
          ref: ${{ job.workflow_sha }}
          path: ._shared
          persist-credentials: false

      - name: Set up Node + Yarn
        uses: ./._shared/.github/actions/setup-node-yarn
        with:
          node-version: ${{ inputs.node-version }}
          # e2e exercises the built web renderer served by preview, not native
          # modules — skip the install build scripts.
          enable-scripts: "false"

      - name: Install Cypress binary
        # Needed because install scripts were disabled above (which normally
        # triggers Cypress's own binary download on install).
        run: yarn cypress install

      - name: Run Cypress
        uses: cypress-io/github-action@fa4a118725a8f001170d49631ea89e5d66fee626 # v7.4.1
        with:
          install: false
          build: ${{ inputs.build-command }}
          start: ${{ inputs.start-command }}
          wait-on: ${{ inputs.wait-on }}
          wait-on-timeout: ${{ inputs.wait-on-timeout }}
```

- [ ] **Step 2: Verify YAML parses**

Run: `uvx --with pyyaml python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1])); print('YAML OK:', sys.argv[1])" .github/workflows/e2e-cypress.yml`
Expected: `YAML OK: .github/workflows/e2e-cypress.yml`

- [ ] **Step 3: Verify zizmor is clean**

Run: `uvx zizmor --min-severity medium --min-confidence medium .github/workflows/e2e-cypress.yml`
Expected: exit 0, no `medium`+ findings. (`build`/`start`/`wait-on` flow into the Cypress action's `with:` inputs, never a `run:` block, so no template-injection finding.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/e2e-cypress.yml
git commit -m "feat: add e2e-cypress reusable workflow"
```

---

### Task 5: README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the four files from Tasks 1–4 (their paths and inputs).
- Produces: documentation only.

- [ ] **Step 1: Add four rows to the "What's here" table**

Find the table under `## What's here`. After the `setup-uv` row, add:

```markdown
| `.github/workflows/lint-and-format-node.yml`   | Reusable workflow — runs `yarn lint` and `yarn format` (ESLint + Prettier)  |
| `.github/workflows/test-node.yml`              | Reusable workflow — runs `yarn test:unit` (Vitest)                          |
| `.github/workflows/e2e-cypress.yml`            | Reusable workflow — runs Cypress e2e (build → preview → wait → run)         |
| `.github/actions/setup-node-yarn`              | Composite action — Corepack + Node + `yarn install --immutable`             |
```

- [ ] **Step 2: Add reusable-workflow usage sections**

Under `## Reusable workflows`, after the `### Lint and format (`lint-and-format-python.yml`)` section, insert:

````markdown
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
      node-version: "20" # optional, defaults to "20"
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
````

- [ ] **Step 3: Add the composite-action usage section**

Under `## Composite actions`, after the `### `setup-uv`` section, insert:

````markdown
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
````

- [ ] **Step 4: Verify the README still renders as valid Markdown**

Run: `uvx --with pyyaml python -c "print(open('README.md').read().count('```') % 2 == 0 and 'code fences balanced' or 'UNBALANCED FENCES')"`
Expected: `code fences balanced`

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document Node/Yarn reusable workflows and setup-node-yarn"
```

---

### Task 6: scanner-ui caller snippets (deliver in chat — do NOT commit)

**Files:** none committed in this repo. Provide the two snippets below to the user for a separate scanner-ui PR.

**Interfaces:**
- Consumes: the three reusable workflows from Tasks 2–4.
- Produces: chat deliverable only.

- [ ] **Step 1: Produce `scanner-ui/.github/workflows/lint-and-format.yml`**

```yaml
name: Lint and format

on:
  push:
    branches: ['**']
  pull_request:

permissions: {}

concurrency:
  group: lint-and-format-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint-and-format:
    permissions:
      contents: read
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/lint-and-format-node.yml@main # TODO: pin to released SHA
```

- [ ] **Step 2: Produce `scanner-ui/.github/workflows/run-tests.yml`**

```yaml
name: Tests

on:
  push:
    branches: ['**']
  pull_request:

permissions: {}

concurrency:
  group: tests-${{ github.ref }}
  cancel-in-progress: true

jobs:
  unit:
    permissions:
      contents: read
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/test-node.yml@main # TODO: pin to released SHA

  e2e:
    permissions:
      contents: read
    uses: Retrams-AS/reusable-github-configuration/.github/workflows/e2e-cypress.yml@main # TODO: pin to released SHA
```

- [ ] **Step 3: Note the follow-up**

Tell the user: after this repo cuts a release, bump both `@main # TODO: pin to released SHA` refs to `@<sha> # <version>` (resolve with `git ls-remote https://github.com/Retrams-AS/reusable-github-configuration <version>`), exactly as `fast-forward.yml` is already pinned.

---

## Self-Review

**1. Spec coverage:**
- Component 1 (setup-node-yarn) → Task 1. ✓
- Component 2 (lint-and-format-node) → Task 2. ✓
- Component 3 (test-node) → Task 3. ✓
- Component 4 (e2e-cypress) → Task 4. ✓
- Component 5 (README) → Task 5. ✓
- Component 6 (scanner-ui snippets, uncommitted) → Task 6. ✓
- House rules (SHA pins, persist-credentials: false, contents: read, script contract) → in Global Constraints and every task's file body. ✓

**2. Placeholder scan:** The only `TODO` strings are the intentional `# TODO: pin to released SHA` markers in the scanner-ui snippets (Task 6) and the `<commit-sha> # <version>` placeholders in README usage blocks (matching the repo's existing convention). No unfinished plan steps.

**3. Type consistency:** The composite action input names (`node-version`, `enable-scripts`) and the action path (`./._shared/.github/actions/setup-node-yarn`) are identical across Tasks 1–4. The three SHA pins are byte-identical everywhere. Workflow input names/types match between each workflow and its README usage block and scanner-ui caller.
