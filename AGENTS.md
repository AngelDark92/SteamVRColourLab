# SteamVRColourLab

Inherit the [workspace rules](../AGENTS.md). This file adds the project contract.

## Output root

Generated files never go inside this checkout. The default root is
`../builds/SteamVRColourLab`, resolved from the repository root; on this workstation
it is
`D:\Angelo\Desktop\SteamLink-GalaxyXR-Windows-Toolkit-FULL\builds\SteamVRColourLab`.
`COLOURLAB_OUTPUT_ROOT` or `tools/Build-Portable.ps1 -OutputRoot` overrides it on
another host or in CI. Keep the project folder name and never use a literal
`builds/project`.

Keep the existing layout beneath that root: `build/` for staging, dependency
environments, caches, logs and previous packages; `dist/` for the current package
and archive; `.venv/` for the source test environment. Preserve saved `runs` and
`settings`, the current `dist/SteamVRColourLab` package and historical validation
evidence. Suppress source bytecode with `-B` or `PYTHONDONTWRITEBYTECODE=1`.

## Build, test and cleanup

```powershell
test_windows.bat
tools\Build-Portable.ps1
python -B tools\build_zipapp.py
python tools\verify_package.py --plan ..\builds\SteamVRColourLab\build\release-plan.json
```

`test_windows.bat` is the full local gate. Run it before reporting any task done and
report the `Ran N tests` / `OK` lines. `git config core.hooksPath .githooks` (once per
clone) runs the same suite before every push; `git push --no-verify` bypasses it and
CI will not catch the regression.

`tools/Build-Portable.ps1` automatically prunes stale staging, previous packages and
old build environments after a successful build. For a manual pass, preview with
`tools/Prune-Portable.ps1` and delete only after review with `-Apply`. Never delete
the current package, saved user data or evidence. Never run a full build unless the
task needs a package or the project gate requires it.

A local build reports `colourlab.__version__`; CI stamps the calculated release
version before building. Do not treat a local `BUILD_INFO.json` version as the
release tag.

## Skills and hosts

Use [steamvrcolourlab-build](.opencode/skills/steamvrcolourlab-build/SKILL.md) for
build, packaging or output-path work, and `cavecrew` for delegation. OpenCode reads
`AGENTS.md`, `.opencode/agents/` and `.opencode/skills/`; Cursor reads
[.cursor/rules/project.mdc](.cursor/rules/project.mdc); Hermes reads this file and
[.agents/AGENTS.md](.agents/AGENTS.md). Host shims add mechanics only; they do not
repeat these rules.
