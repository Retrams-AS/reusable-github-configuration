# CalVer Release Workflow — Design

## Goal

Let consumers pin to a stable, dated version of this reusable-config repo instead of
the moving `@main` ref. Releases are cut deliberately, by hand, and produce an
immutable git tag whose commit SHA consumers pin to.

## Scope

- New workflow: `.github/workflows/release.yml`.
- README updates: a "Releasing" section + pinned-SHA usage snippets.

## Versioning

- Scheme: **CalVer `YYYY-MM.PATCH`** (e.g. `2026-06.0`, `2026-06.1`, `2026-07.0`).
- `PATCH` resets each year-month and starts at `0`.
- The next `PATCH` is the highest existing `PATCH` for the current `YYYY-MM`, plus one.

## Trigger

- `workflow_dispatch` only. Nothing is released automatically on merge.

## Behavior

On dispatch the workflow:

1. **Guard — branch.** Refuse unless run from `main` (`github.ref == refs/heads/main`).
2. **Guard — already released.** Refuse if a CalVer tag already points at the commit
   being released (`github.sha`). This blocks re-releasing an unchanged `main` while
   still allowing recovery from a previously failed run (a failed run left no tag, so
   nothing blocks). Non-CalVer tags on the commit are ignored.
3. **Compute version.** Determine current `YYYY-MM` (UTC) and the next `PATCH`.
4. **Create tag.** Create a lightweight tag ref via the GitHub REST API
   (`POST /git/refs`, `refs/tags/<tag>` → `github.sha`). No `git push`, so no
   persisted credentials.
5. **Report.** Write the new tag, the commit SHA, and ready-to-paste pin lines to the
   job summary — this is how a maintainer finds the new hash.

## Output

- A git tag only. No GitHub Release object.

## Security / conventions

- Top-level `permissions: {}`; job grants `contents: write` (tag creation only).
- `actions/checkout` pinned to SHA with `persist-credentials: false` (zizmor-clean).
- Run steps pass `github.*` values through `env`, never inline in the script
  (avoids template injection).
- `concurrency` group serializes releases so two runs can't race for the same patch.

## README changes

- New "Releasing" section: how to cut a release (Actions → Release → Run workflow),
  the CalVer scheme, and how to resolve a tag's SHA
  (`git ls-remote https://github.com/Retrams-AS/reusable-github-configuration <tag>`
  or the run's job summary).
- Update `setup-uv` and `lint-and-format-python.yml` usage snippets from `@main` to
  pinned-SHA form with the CalVer tag as a trailing comment.
