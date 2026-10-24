# Build output and cleanup policy

The canonical output root is `../builds/SteamVRColourLab`, resolved from the
repository root, or `COLOURLAB_OUTPUT_ROOT` when set. Generated files never belong
inside this checkout.

- `build/` holds staging, dependency environments, caches, logs and previous
  packages. `dist/` holds the current `SteamVRColourLab` package, ZIP and checksum.
  `.venv/` holds the source test environment.
- Keep exactly one previous package as recovery. Delete older staging, previous
  packages and `venv-*` environments that do not match the active source Python.
- `tools/Build-Portable.ps1` runs this prune automatically after a successful build.
  For a manual pass, preview with `tools/Prune-Portable.ps1`, then use `-Apply`.
- Never delete `dist/SteamVRColourLab`, saved `runs` or `settings`, and never delete
  a legacy directory whose user data is not already byte-identical in the current
  package. The pruner refuses those cases and reports them.
- Preserve historical validation evidence. Rebuildable staging and old package
  copies are not evidence.

## 2026-10-24 cleanup

Removed 19 stale directories (14,347 files, 590.7 MB): nine `staging-*`, seven old
`previous-*`, two `relocated-*`, and the stale Python 3.13 build environment. Moved
two unique legacy run sessions from `relocated-check` into the current
`dist/SteamVRColourLab/runs` and verified every file by SHA-256 before deleting the
legacy copy. Kept the current package, the newest previous package, the active
Python 3.14 environment, `.venv`, and all h264/telemetry/log evidence.

The next successful `Build-Portable.ps1` run reclaimed another 67,449,696 bytes in
1,199 staging files and left no new staging or previous directory behind.

Historical relocation records remain in
[validation/BUILD-OUTPUT-HISTORY-2026-10.md](validation/BUILD-OUTPUT-HISTORY-2026-10.md).
Cleanup receipts are in `builds/_cleanup/` and
`builds/SteamVRColourLab/build/portable/stale-cleanup.json`.
