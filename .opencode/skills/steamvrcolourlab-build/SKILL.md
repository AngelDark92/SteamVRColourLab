---
name: steamvrcolourlab-build
description: Build, package, verify or clean SteamVRColourLab outputs in the external project folder. Use for build scripts, CI paths, launchers or output cleanup.
---

# SteamVRColourLab builds

Inherit [AGENTS.md](../../../AGENTS.md). The output root is
`../builds/SteamVRColourLab`, resolved from the repository root; on this workstation
`D:\Angelo\Desktop\SteamLink-GalaxyXR-Windows-Toolkit-FULL\builds\SteamVRColourLab`.
`COLOURLAB_OUTPUT_ROOT` and `Build-Portable.ps1 -OutputRoot` override it. Keep the
project folder name; never create `builds/project` or generated trees inside the
checkout.

Use `build/` for staging, build environments, caches, logs and previous packages;
`dist/` for the current package and archive; `.venv/` for source dependencies.
Preserve saved `runs`/`settings`, `dist/SteamVRColourLab`, and historical validation
evidence. Suppress bytecode with `-B` or `PYTHONDONTWRITEBYTECODE=1`.

## Commands

```powershell
test_windows.bat
tools\Build-Portable.ps1
python -B tools\build_zipapp.py
python tools\verify_package.py --plan ..\builds\SteamVRColourLab\build\release-plan.json
tools\Prune-Portable.ps1            # preview
tools\Prune-Portable.ps1 -Apply     # delete stale staging/previous/old venvs
```

`test_windows.bat` is the full local gate and matches `.githooks/pre-push`. Hosted
CI runs only `tests.test_build_cleanup`, the release plan, the portable build,
package verification and publication. Report `Ran N tests` / `OK` separately from
CI evidence.

`Build-Portable.ps1` prunes stale portable output after a successful build unless
`-KeepBuildFiles` is set. The pruner keeps the newest previous package, the active
`venv-*`, the current package and any `runs`/`settings` not already present
byte-identically in `dist`. A local build reports `colourlab.__version__`; CI stamps
the calculated release version first.

## CI layout

The workflow writes to `${{ github.workspace }}/../builds/SteamVRColourLab`.
`actions/upload-artifact` rejects paths outside the workspace, so the build job copies
the ZIP, its checksum and `release-plan.json` into a workspace `ci-artifacts/` folder;
the publisher reads that folder. Keep artifact patterns inside the workspace.

When changing a path, update the PowerShell, Python, BAT launchers, CI, README,
checksums and tests together. Record cleanup results in `WORKSPACE_CLEANUP.md` or the
external receipt, and label local checks separately from GitHub Actions or headset
runtime proof.
