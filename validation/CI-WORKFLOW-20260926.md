# GitHub build and release validation — 2026-09-26

Repository: https://github.com/AngelDark92/SteamVRColourLab

Implementation commit: `a38e9a2194b0ed3ce9f758fb1f0c123ec7879a1b`

The initial remote contained only LICENSE. Imported the application's existing
source, tests, build entry points, examples, and curated validation documents
so GitHub can build from a checkout. The existing local LICENSE change,
agent skills, raw session logs, and historical checksum file were not committed.

## Checks

- Local full suite: **120 tests passed**, 8.736 seconds.
- Version policy: **16 tests** using disposable real Git repositories, covering
  patch/minor/major, scopes, precedence, resets, tag ordering, unrelated tags,
  body-only and empty prefixes, initial version, repeated stamping, existing
  HEAD tags, ambiguous tags, and shallow checkout rejection.
- Artifact/publication regression suite: **19 tests**, including checksums,
  source identity, archive paths, user-data exclusion, CLI version, immutable
  tags, draft recovery, publication order, and upload failures. Remote commands
  in these unit tests are mocked; actual GitHub evidence is recorded below.
- `actionlint` **1.7.12**: workflow passed; downloaded binary checksum verified.
- Existing PowerShell portable builder: completed locally. The locally built
  0.2.1 archive passed checksum/content checks and relocated `--help`/`--version`
  with external Python removed from PATH. This build used the working source
  before committing; GitHub provides the exact-commit build evidence.

## GitHub evidence

- Branch run: https://github.com/AngelDark92/SteamVRColourLab/actions/runs/36236715905
- Linux: **120 tests passed**, 7.561 seconds, real Mesa/EGL rendering and Tk/Xvfb.
- Windows: package and relocated executable checks passed, stamped **0.3.0**,
  matching implementation commit.
- Main run: https://github.com/AngelDark92/SteamVRColourLab/actions/runs/36236828029
- Main: Linux tests, Windows build, and publication **all succeeded**.
- Published release: https://github.com/AngelDark92/SteamVRColourLab/releases/tag/v0.3.0
- Downloaded the actual published ZIP and checksum, verified archive contents and
  source identity, then ran its relocated EXE with external Python removed from
  PATH. `--help` and `--version` passed; version **0.3.0**.
- Published ZIP: **23,257,068 bytes**; SHA256
  `e44ba9b4f7e9f7d066a25f4a0d9e0d07688c25a1145bdbe427de62a76e6b1f48`.
- Fetched the real `v0.3.0` tag back locally. Replanning the same commit returned
  `0.3.0`, `bump: none`, `already_tagged: true`, confirming tag reuse.
- Machine-readable download evidence: `published-release-check-20260926.json`.

The `feat:` implementation commit requests 0.2.1 -> 0.3.0. Release versions are
recorded by `vX.Y.Z` tags and stamped into build copies; the checked-in source
version remains the initial fallback. GitHub's token writes only in the gated
main release job. No SteamVR settings, device commands, or headset session were
changed during this task. CI graphics tests establish renderer behavior under
Mesa, not end-to-end headset precision.

## Cleanup

Inventory found only the root Git repository; no nested Git repositories.
The explicit deletion allowlist was resolved inside this workspace and contained
no junctions or symlinks. Automatic approval review rejected the cleanup command
with `blocked by policy`; no removal was attempted afterward. **0 bytes reclaimed**.
These newly generated disposable directories remain, totaling **55,673,303 bytes**:

| Directory | Bytes |
| --- | ---: |
| `build/ci-test-venv` | 35,578,676 |
| `build/actionlint` | 9,096,324 |
| `build/portable/staging-20260926-124225-160` | 10,998,303 |

Cleanup is deferred until these exact directories can be removed through an
approved path. The separate published-release download used a temporary
directory that was removed normally after verification.

Pre-existing build trees, portable settings/session data, and their backup are
retained. The portable build environment and license cache are retained for
reuse; regenerate disposable outputs with `tools/Build-Portable.ps1` and the
test commands documented in README.md.
