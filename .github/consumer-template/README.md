# Consumer template

Copy the three files into your repo's `.github/workflows/`. Edit every value
marked `# EDIT:`, and replace each `@0000…` with the sha of the release you are
pinning.

| file | what it does |
|---|---|
| `build.yml` | Builds every push and PR, and pins dev's overlay to the sha it just built. dev tracks the default branch on both halves. |
| `release.yml` | Mints a CalVer version, then promotes prod to it in the same run. Cutting a version deploys it. |
| `promote.yml` | Moves prod to a version that already has a tag — a rollback, or a promotion split from its release. |

`release.yml` passes `create-tag: false` because promote lands the commit the tag
has to sit on. Release tagging first would put the tag on the commit before the
prod overlay names the new image, which is the skew this contract removes.

Keep `.github` out of `image-irrelevant-paths`. `build.yml` carries the build
recipe — image ref, index, CA — so a change there can change the image, and
retagging past one ships stale content.

The `uses:` shas are pinned per repo on purpose: a change to these workflows
reaches you when you edit that line, and not before.

Why prod's manifests and image come from one revision:
[repository README](../../README.md#manifests-and-image-from-one-revision).
