# Node/Yarn frontend reusable CI — Design

## Goal

Give the org's Yarn-based frontends the same shared-CI treatment the Python
services already have. Extract `scanner-ui`'s per-repo CI (`lint-and-format.yml`,
`run-tests.yml`) into this repo as reusable workflows plus one composite action,
so the Node/Yarn setup preamble is maintained once and reused everywhere — the
Node analog of the existing `setup-uv` action + `lint-and-format-python.yml`.

## Context

- First consumer: `Retrams-AS/scanner-ui` — Vue 3 + Electron app on **Yarn 4**
  (Corepack, `packageManager` pinned in `package.json`). Its `fast-forward.yml`
  is already a caller of this repo's reusable workflow; only `lint-and-format.yml`
  and `run-tests.yml` remain to extract.
- scanner-ui's three CI jobs (lint, unit, e2e) share one setup preamble:
  `checkout` → `corepack enable` → `setup-node (cache: yarn)` →
  `yarn install --immutable` with `YARN_ENABLE_SCRIPTS=false` (skip the slow
  Electron native rebuild that lint/unit/web-e2e don't need). That repetition is
  the composite action to extract.
- Follows the repo's established `._shared` self-checkout pattern
  (`lint-and-format-python.yml`): a reusable workflow checks itself out at
  `job.workflow_repository`@`job.workflow_sha` into `._shared/`, so its composite
  action is always version-locked to the workflow the caller pinned.

## Decisions (locked)

- **Two workflows, mirroring Python.** `lint-and-format-node.yml` +
  `test-node.yml` (unit). Independently callable — a repo can adopt one without
  the other. Parallels `lint-and-format-python.yml` / planned `test-python.yml`.
- **E2E is its own workflow.** `e2e-cypress.yml` handles the Cypress
  build/preview/wait/run flow separately, keeping the unit path clean.
- **Yarn only.** Corepack + `yarn install --immutable`, exactly as scanner-ui
  does. No package-manager auto-detection (a future `feat:` if an npm frontend
  adopts these).
- **Hardcoded yarn script names.** Workflows invoke `yarn lint`, `yarn format`,
  `yarn test:unit`, `yarn build`, `yarn preview` directly — same way
  `lint-and-format-python.yml` hardcodes `uv run ruff check .`. This is the
  consumer contract; a repo aliases its scripts to these names. Keeps the run
  steps injection-free and matches "the workflow from that repo". Overridable
  inputs are a deferred `feat:`.
- **Reuse already-vetted action SHAs** rather than introducing new pins:
  `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2`,
  `actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e # v6.4.0`,
  `cypress-io/github-action@fa4a118725a8f001170d49631ea89e5d66fee626 # v7.4.1`.
- **This task ships the reusable side only.** scanner-ui caller files are
  provided as snippets, not committed here (they need a released SHA to pin to,
  which doesn't exist until this repo cuts a release).

## House rules (applied to every file)

Every `uses:` SHA-pinned with a version comment (zizmor `unpinned-uses`);
`persist-credentials: false` on all checkouts (none push git); least-privilege
`permissions:` (`contents: read`) on each reusable job.

## Component 1 — `.github/actions/setup-node-yarn/action.yml`

Composite action. Does **not** checkout (the calling workflow checks out first,
exactly like `setup-uv`).

**Inputs**

| Input | Default | Purpose |
| --- | --- | --- |
| `node-version` | `"20"` | forwarded to `setup-node` |
| `enable-scripts` | `"false"` | value of `YARN_ENABLE_SCRIPTS` for the install; `"true"` runs postinstall (e.g. native rebuilds) |

**Steps**

1. `corepack enable` (activates the Yarn version pinned in `packageManager`).
2. `actions/setup-node@…v6.4.0` with `node-version: ${{ inputs.node-version }}`
   and `cache: yarn`.
3. `yarn install --immutable`, `env: YARN_ENABLE_SCRIPTS: ${{ inputs.enable-scripts }}`.

## Component 2 — `.github/workflows/lint-and-format-node.yml`

**Inputs:** `node-version` (`"20"`), `enable-scripts` (boolean, `false`).

**Job `lint-and-format`** — `permissions: contents: read`:
checkout caller (`persist-credentials: false`) → checkout self into `._shared`
(`repository: ${{ job.workflow_repository }}`, `ref: ${{ job.workflow_sha }}`,
`persist-credentials: false`) → `./._shared/.github/actions/setup-node-yarn` →
`yarn lint` → `yarn format`.

## Component 3 — `.github/workflows/test-node.yml`

Same inputs, permissions, and setup as Component 2; final step runs
`yarn test:unit` (Vitest; CI=true makes it single-run).

## Component 4 — `.github/workflows/e2e-cypress.yml`

**Inputs**

| Input | Default | Purpose |
| --- | --- | --- |
| `node-version` | `"20"` | forwarded to setup |
| `build-command` | `yarn build` | Cypress action `build:` |
| `start-command` | `yarn preview` | Cypress action `start:` |
| `wait-on` | `http://localhost:4173` | Cypress action `wait-on:` |
| `wait-on-timeout` | `120` | Cypress action `wait-on-timeout:` |

**Job `e2e`** — `permissions: contents: read`:
checkout caller → checkout self into `._shared` → `setup-node-yarn`
(`enable-scripts: false`) → `yarn cypress install` (explicit, because install
scripts were skipped) → `cypress-io/github-action@…v7.4.1` with `install: false`
and the build/start/wait inputs. Command/URL values flow only into the Cypress
action's `with:` inputs, never a `run:` block.

## Component 5 — README

Add the three workflows and the action to the "What's here" table; add a usage
section per component using the `@<commit-sha> # <version>` pin convention; state
the **script contract** (`yarn lint` / `yarn format` / `yarn test:unit` /
`yarn build` / `yarn preview`) so consumers know what to expose.

## Component 6 — scanner-ui caller snippets (delivered in chat, not committed)

- `lint-and-format.yml` → one caller job of `lint-and-format-node.yml`.
- `run-tests.yml` → two caller jobs: `unit` → `test-node.yml`, `e2e` →
  `e2e-cypress.yml` (keeps scanner-ui at its current two files).
- Both keep the caller's own `on:` triggers and `concurrency:` group; pinned
  `@main` with a `# TODO: pin to released SHA` note (the same bootstrap path
  `fast-forward.yml` took), to be bumped to `@<sha> # <version>` after this repo
  releases.

## Out of scope / follow-ups

- Converting scanner-ui to callers (separate PR, after a release SHA exists).
- npm auto-detection and overridable script-name inputs (deferred `feat:`s).
- Updating the `retrams-conventions` `github-actions` skill inventory line
  (lives in another repo).
