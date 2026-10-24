# Build output and cleanup policy

The canonical output root is `../builds/SteamVRColourLab`, resolved from the
repository root, or `COLOURLAB_OUTPUT_ROOT` when set. Generated files never belong
inside this checkout.

- `build/` holds staging, dependency environments, caches, logs and previous
  packages. `dist/` holds the current `SteamVRColourLab` package, ZIP and checksum.
  `.venv/` holds the source test environment.
- Keep the newest previous package as recovery. Delete older staging, previous
  packages and `venv-*` environments that do not match the active source Python.
  The 7-day age gate may retain a recent unproven package or environment for one
  more run; the next successful build removes it once it is old enough.
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

## 2026-10-24 verification

- Local gate: `test_windows.bat` ran 200 tests, `OK`.
- Local CI simulation: release plan `0.7.0`, portable build and
  `verify_package.py` succeeded against commit `d24c1d2`.
- GitHub Actions run
  [#14](https://github.com/AngelDark92/SteamVRColourLab/actions/runs/40129070225):
  both `Portable Windows x64` and `Publish verified release` succeeded; release
  `v0.7.0` was published with the ZIP and SHA-256 asset.
- Post-build prune: 0 stale candidates; only the current package, newest previous
  package, active environments and retained evidence remain.

Historical relocation records remain in
[validation/BUILD-OUTPUT-HISTORY-2026-10.md](validation/BUILD-OUTPUT-HISTORY-2026-10.md).
Cleanup receipts are in `builds/_cleanup/`, with
`build/portable/stale-cleanup-build.json` for automatic builds and
`stale-cleanup-manual.json` for manual `-Apply` runs.
