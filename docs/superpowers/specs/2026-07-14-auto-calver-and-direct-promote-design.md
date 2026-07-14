# Auto-minted CalVer + direct-push Promote — Design

## Goal

Remove the two manual/wasteful parts of the release flow:

1. `release_calver.yml` requires the caller to type the CalVer version by hand.
2. `promote.yml` opens a promotion PR, whose creation + merge triggers 2–3
   pipeline runs that add nothing (the change is a one-line image-tag bump).

## Scope

- `.github/workflows/release_calver.yml` — auto-mint the version, expose it as
  a workflow output.
- `.github/workflows/promote.yml` — replace the PR flow with a direct commit
  to the default branch, made with a GitHub App token (same trust model as
  `fast-forward.yml`).
- README updates for both, including a release→promote chaining example.

## release_calver: auto-minted version

- The `version` input becomes **optional**. When provided it is validated and
  used exactly as today (deliberate override / recovery path).
- When omitted, the workflow resolves the version itself:
  1. **Reuse** — if a CalVer tag (`YYYY-MM.N`) already points at `GITHUB_SHA`,
     that version is reused and minting is skipped. Re-dispatching on an
     unchanged commit is therefore idempotent and still emits the version
     output for chained promotes.
  2. **Mint** — otherwise take the current UTC `YYYY-MM` and the highest
     existing `N` for that month among git tags, plus one (first release of a
     month is `YYYY-MM.1`). The checkout already uses `fetch-depth: 0`, so all
     tags are local.
- New `workflow_call` **output `version`** (minted or reused), so callers can
  chain `promote` with `needs.release.outputs.version`.
- Job-level `concurrency` group (`release-calver`) serializes runs so two
  dispatches cannot race to the same `N`.

## promote: direct push via GitHub App

- Drop `contents: write` / `pull-requests: write` on `GITHUB_TOKEN`; the job
  runs with `permissions: {}` and two new required secrets, `app-id` and
  `app-private-key` — a GitHub App that is a **bypass actor** on the default
  branch's ruleset. A **dedicated App** (the org's "Release App"), not the
  fast-forward one: commits are authored as `<app>[bot]`, so a release-only
  App keeps the deploy audit trail self-describing and its credentials
  revocable independently of merge authority.
- The bump is written with the **Contents API** (`PUT /repos/{repo}/contents/{file}`),
  not `git push`:
  - the file is read from the default-branch tip (not the dispatched ref), so
    the update replaces exactly what it read;
  - the blob `sha` parameter makes the update atomic — a concurrent change
    returns 409 instead of clobbering;
  - the commit is created server-side, shows as **Verified** (signed by GitHub
    on behalf of the App), and no git credentials ever touch the runner — the
    job needs no checkout at all.
- Commit message keeps the `[skip ci]` marker: App-token pushes (unlike
  `GITHUB_TOKEN` pushes) do trigger workflows, and a promotion commit has
  nothing for build/test/lint to check.
- The PR path is removed entirely. Dispatching promote **is** the deploy
  (Argo CD syncs the commit); rollback is `git revert` of the bump commit.
- Same-target promotes are serialized with a job-level `concurrency` group.

## Error handling

- release_calver: explicit-version regex validation unchanged; missing
  `<image>:<sha7>` artifact error unchanged.
- promote: missing overlay file → actionable `::error`; no quoted `newTag`
  line → `::error`; already at the requested version → clean no-op; concurrent
  write → 409 from the API fails the run loudly (re-dispatch retries).

## Security / conventions

- `create-github-app-token` pinned to the same SHA as `fast-forward.yml`, with
  `# zizmor: ignore[github-app]` (deliberate bypass actor, see issue #9).
- App token scoped to `permission-contents: write` only.
- All `github.*` / input values pass through `env`, never inlined in scripts.

## Testing

Exercised by dispatching the flow from a consumer repo (fot_server):
release with no version input → tag `YYYY-MM.N` appears; re-dispatch → same
version reused, no new tag; promote → single Verified bump commit on main, no
PR, no extra CI runs beyond Argo CD's sync.
