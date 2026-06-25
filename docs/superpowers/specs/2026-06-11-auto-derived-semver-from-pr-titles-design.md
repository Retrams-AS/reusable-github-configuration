# Auto-derived SemVer from PR titles — Design

## Goal

Remove the manual version judgment from cutting a release. Today a maintainer dispatches
the release workflow and must choose `patch` / `minor` / `major`. Instead, **derive the
bump automatically** from the Conventional Commit type of each PR merged since the last
tag. Releases stay manually triggered (deliberate timing), but require no version
decision at release time — that judgment is captured once, per PR, by its author, when
the change is freshest.

## Context

- Builds on the existing `.github/workflows/release.yml` (SemVer, manual
  `workflow_dispatch`, in-house bash + `gh`).
- Versioning stays SemVer `vMAJOR.MINOR.PATCH` (see
  `2026-06-10-semver-release-workflow-design.md`). This spec only changes **how the bump
  is determined** — not the scheme, the trigger model, or the tag/release mechanics.

## Decisions (locked)

- **Convention source: PR titles.** Merge-strategy-agnostic; same "PRs since last tag"
  window the changelog already uses.
- **Trigger: manual `workflow_dispatch` retained.** The `bump` input is removed.
- **Tooling: in-house.** Extend `release.yml`; no third-party release tooling, no bot
  token — preserves the repo's zizmor-clean, minimal-permission posture.
- **Mapping: strict SemVer, including at 0.x.** A breaking change bumps major even from
  `0.x` (`0.3.1 → 1.0.0`).
- **Escape hatch: optional `version_override` input** for deliberate cases.
- **Enforcement: in-house PR-title check**, required via the org Ruleset.

## Inputs (`workflow_dispatch`)

- `version_override` (optional, **new**) — when set, bypasses derivation. Accepts a bump
  level (`patch` / `minor` / `major`) or an explicit `vX.Y.Z`. Used for forcing a major,
  cutting `v1.0.0`, or a one-off version. Empty on the normal path.
- `bump` — **removed**.
- `notes` — **removed**. The release body is the auto-generated changelog
  (`generate-notes`); a maintainer who wants a summary edits the published Release in the
  UI, so a dispatch input is redundant.

A normal release therefore takes **zero inputs** — just "Run workflow".

## Behavior

On dispatch:

1. **Guard — branch.** Refuse unless run from `main` (unchanged).
2. **Resolve the window.** Find the highest existing SemVer tag (`latest`; base `v0.0.0`
   if none).
3. **Determine the bump.**
   - If `version_override` is set → use it. A bump level applies to `latest`; an explicit
     version is used as-is after validating it is valid SemVer and strictly greater than
     `latest`.
   - Otherwise **derive from PR titles**: list PRs merged since `latest`, classify each
     title's Conventional Commit type, and take the highest-ranked type:
     - breaking — the type carries a `!` in the **title** (e.g. `feat!:`, `fix(x)!:`) →
       **major**. (A `BREAKING CHANGE:` footer lives in the PR body, which is not parsed;
       breaking changes must therefore mark the title with `!`.)
     - `feat` → **minor**
     - `fix`, `perf` → **patch**
     - other types (`docs`, `chore`, `ci`, `build`, `refactor`, `test`, `style`,
       `revert`) → no bump
   - If the derived bump is "none" (no releasable PRs in the window) → **refuse** with a
     clear error naming `latest`.
4. **Compute the new version** by applying the bump to `latest`.
5. **Create the tag** via the REST API (unchanged: `refs/tags/<tag>` → `github.sha`, no
   `git push`, no persisted credentials).
6. **Publish the release** with the `generate-notes` changelog as its body (editable in
   the Release UI afterwards).
7. **Report** the new tag, commit SHA, release URL, and ready-to-paste pin lines to the
   job summary (unchanged).

### Resolving "PRs merged since the last tag"

- For each commit in `latest..HEAD` on `main`, resolve its associated PR(s) via the
  GitHub API (`GET /repos/{repo}/commits/{sha}/pulls`); collect the unique PR titles.
  This works across squash, rebase, and merge-commit strategies.
- Commits with no associated PR (e.g. direct pushes) contribute no type and therefore do
  not raise the bump. (Dedup/implementation detail belongs to the plan.)

### Classifying a PR title

- Grammar: `type(optional scope)(optional !): subject`.
- Type match is case-insensitive against the known set. An **unrecognized** type is
  ignored (does not raise the bump). The enforcement check below stops unrecognized
  titles from merging going forward, so this only covers legacy/edge PRs.

## Enforcement — PR-title check

- A new workflow (`.github/workflows/pr-title-check.yml`) on `pull_request`
  (`opened` / `edited` / `reopened` / `synchronize`) validates the PR **title** against
  the Conventional Commit grammar using an in-house regex, and fails with a helpful
  message (allowed types + examples) on mismatch. It also exposes `workflow_call` so it
  can be required org-wide, like zizmor.
- In-house regex only — no third-party action to pin, consistent with the repo's
  zizmor-clean posture.
- **Governance:** add this check to the org Ruleset as required-to-merge (same model as
  the zizmor workflow). That config lives outside this repo; the README notes it.
- GitHub's squash-merge default uses the PR title as the squash commit subject, so
  enforcing the title also keeps `main`'s history conventional.

## Edge cases

- **No releasable PRs** since `latest` → refuse:
  `No releasable changes (feat/fix/perf/breaking) since <latest>`.
- **PR carrying multiple logical changes** → only the title's single type counts (one PR
  = one type by convention). Sub-PR granularity is intentionally out of scope.
- **Unrecognized / legacy title** → ignored for the bump.
- **`version_override`** that is not a valid bump level, or not a valid SemVer strictly
  greater than `latest` → refuse with a clear error.
- **First release** (no existing tag) → base `v0.0.0`; derivation applies (first `feat` →
  `v0.1.0`, first `fix` → `v0.0.1`). Use the override if a different first version is
  wanted.

## Unchanged

Branch guard, REST-API tag creation (no `git push`, no persisted creds), `generate-notes`
changelog, job-summary pin lines, top-level `permissions: {}` with job
`contents: write`, `concurrency` serialization, and env-passed values (no inline template
injection in run steps).

## Docs (README)

- "Cut a release": drop the bump step — releasing is "Run workflow" (optionally with
  `version_override`).
- Add a short **PR-title convention** section for contributors: the allowed types and how
  `feat` / `fix` / `!` map to the version, so they understand the title *is* the version
  signal.
- Note the required PR-title check (Ruleset-governed).

## Out of scope

- Fully automatic (push-triggered or release-PR) flows — deliberately rejected in favour
  of manual release timing.
- Per-commit (rather than per-PR) granularity.
- Monorepo / multi-package versioning.
