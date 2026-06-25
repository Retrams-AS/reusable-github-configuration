# SemVer Release Workflow — Design

## Goal

Let consumers pin to a stable, released version of this reusable-config repo instead of
the moving `@main` ref. Releases are cut deliberately, by hand, and produce an
immutable git tag whose commit SHA consumers pin to.

> **Amended 2026-06-11.** Two parts of the original behaviour below have since changed:
> the manual `bump` input was replaced by auto-derivation from PR titles (see
> `2026-06-11-auto-derived-semver-from-pr-titles-design.md`), and the "already released"
> guard was removed in favour of GitHub's repository-level **Immutable releases** setting.
> The affected sections are annotated inline.

## Versioning scheme: SemVer (not CalVer)

This repo is an **internal library** — reusable workflows and a composite action with
multiple consumers and an input compatibility contract (e.g. `python-version`). The
org convention (see `digital_ocean_deployment` design spec,
`2026-06-09-argocd-gitops-bootstrap-fot-dev-design.md`) reserves **CalVer
`YYYY-MM.PATCH` for deployable release images** and keeps **SemVer for internal
libraries**, because images have a single consumer (the cluster) while libraries
carry a compatibility contract. This workflow therefore uses SemVer.

- Scheme: **`vMAJOR.MINOR.PATCH`** (e.g. `v0.1.0`, `v0.1.1`, `v1.0.0`).
- The maintainer chooses the bump at dispatch time (`patch` / `minor` / `major`); the
  next version is computed from the highest existing tag (base `v0.0.0` if none).
- The semver level answers: *if a consumer moved their pinned SHA to this release,
  would they have to change their `with:` block?* No → `patch`; new optional input →
  `minor`; changed/removed input → `major`.
- Note on the contract: consumers pin an **immutable SHA** and the tag is a trailing
  comment marker, so the version does not *gate* what they receive — it is an
  informational signal for maintainers scanning releases, not an enforced range.

## Scope

- New workflow: `.github/workflows/release.yml`.
- README updates: a "Releasing" section + pinned-SHA usage snippets.

## Trigger

- `workflow_dispatch` only. Nothing is released automatically on merge.
- Inputs: `bump` (choice: `patch`/`minor`/`major`, default `patch`) and `notes`
  (optional free-text summary).
  - *Amended 2026-06-11:* `bump` was removed; the bump is now derived from PR titles.
    A `version_override` input (optional) replaces it for the rare deliberate case.
    `notes` was also removed — the body is the auto-generated changelog, edited in the
    Release UI if a summary is wanted. A normal release now takes no inputs at all.

## Behavior

On dispatch the workflow:

1. **Guard — branch.** Refuse unless run from `main` (`github.ref == refs/heads/main`).
2. **Guard — already released.** Refuse if a SemVer tag already points at the commit
   being released (`github.sha`). This blocks re-releasing an unchanged `main` while
   still allowing recovery from a previously failed run (a failed run left no tag, so
   nothing blocks). Non-SemVer tags on the commit are ignored.
   - *Amended 2026-06-11:* this guard was **removed**. Release immutability is now
     enforced by GitHub's repository-level Immutable releases setting, and the
     "unchanged `main`" case is instead caught by step 3 finding no releasable PRs.
3. **Compute version.** Take the highest existing `vMAJOR.MINOR.PATCH` tag (base
   `v0.0.0` if none) and apply the chosen bump.
   - *Amended 2026-06-11:* the bump is no longer chosen by hand. It is derived from the
     Conventional Commit type of the PRs merged since that tag (breaking → major, feat →
     minor, fix/perf → patch; none → refuse). See the 2026-06-11 spec.
4. **Create tag.** Create a lightweight tag ref via the GitHub REST API
   (`POST /git/refs`, `refs/tags/<tag>` → `github.sha`). No `git push`, so no
   persisted credentials.
5. **Publish release.** Create a GitHub Release for the tag. Its body is the
   auto-generated changelog of merged PRs since the previous tag
   (`POST /releases/generate-notes` with `previous_tag_name`), with the maintainer's
   `notes` summary prepended when provided. The notes remain editable in the UI.
6. **Report.** Write the new tag, the commit SHA, the release URL, and ready-to-paste
   pin lines to the job summary — this is how a maintainer finds the new hash.

## Output

- A git tag **and** a GitHub Release. The Release carries human-readable notes ("what
  changed since the last release"); consumers still pin to the commit SHA, not to the
  Release.

## Security / conventions

- Top-level `permissions: {}`; job grants `contents: write` (tag + release creation).
- `actions/checkout` pinned to SHA with `persist-credentials: false` (zizmor-clean).
- Run steps pass `github.*` / input values through `env`, never inline in the script
  (avoids template injection).
- `concurrency` group serializes releases so two runs can't race for the same version.

## README changes

- New "Releasing" section: how to cut a release (Actions → Release (SemVer) → Run
  workflow, choosing the bump and optional notes), the SemVer scheme and bump
  guidance, and how to resolve a tag's SHA
  (`git ls-remote https://github.com/Retrams-AS/reusable-github-configuration <tag>`
  or the run's job summary / the published Release).
- Update `setup-uv` and `lint-and-format-python.yml` usage snippets from `@main` to
  pinned-SHA form with the SemVer tag as a trailing comment.
