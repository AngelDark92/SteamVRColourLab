---
name: steamvrcolourlab-build
description: Build, package, verify or relocate SteamVRColourLab outputs using its external project folder. Use for changes to build scripts, CI artifact paths, source launchers or build cleanup in this repository.
---

# SteamVRColourLab builds

Read the repository [AGENTS.md](../../../AGENTS.md). The canonical local output
root is `../builds/SteamVRColourLab`, relative to the repository root:
`D:\Angelo\Desktop\SteamLink-GalaxyXR-Windows-Toolkit-FULL\builds\SteamVRColourLab`.
`project` in workspace path examples means the project name. Never create
literal `builds/project`, or put generated build directories in the checkout.

Keep subfolders beneath that root: `build/` for staging, dependency caches,
diagnostic logs and previous packages; `dist/` for distributable packages;
`.venv/` for source dependencies. Historical validation reports remain in source.
Suppress source bytecode with `-B` or `PYTHONDONTWRITEBYTECODE=1`.

Build from the repository root with `tools/Build-Portable.ps1` or
`build_portable_windows.bat`. Build the Python archive with
`python -B tools/build_zipapp.py`. Verify packages with `tools/verify_package.py`
and the matching external plan. Run local tests with
`..\builds\SteamVRColourLab\.venv\Scripts\python.exe -B -m unittest discover -v`.

Keep PowerShell, Python, batch launchers, documentation, CI and checksum records
consistent after changing paths. CI uses the same named folder beside its
checkout; upload and download the existing `build/` + `dist/` artifact layout.
`COLOURLAB_OUTPUT_ROOT` and PowerShell `-OutputRoot` support other hosts; retain
the project folder name unless the user requests a different destination.

Before moving or cleaning outputs, inventory owned paths, validate absolute
source and destination paths, reject junctions/symlinks, and preserve saved
`runs`/`settings`, unknown backup files and other projects' files. Verify moved
files and retained data by hash. Record results in `WORKSPACE_CLEANUP.md` and
distinguish local checks from GitHub Actions or headset runtime verification.
