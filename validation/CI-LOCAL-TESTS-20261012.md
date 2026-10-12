# Faster CI with a local test gate — 2026-10-12

## Change

- Removed the Ubuntu `test` job (apt install of Mesa/Xvfb/Tk + full suite).
  The workflow now has one build job (`windows`) plus the gated publisher.
- The build job calculates and stamps the release version itself
  (`release_policy.py --stamp --github-output`) and exports `version` and
  `release` for the publisher, so the package and the release decision come
  from the same commit without a second runner.
- Pull request runs cancel superseded ones; `main` releases still serialize.
- The full suite is now a local gate: `test_windows.bat` and
  `.githooks/pre-push` (`git config core.hooksPath .githooks`, enabled on this
  checkout). `AGENTS.md`, the build skill and TECHNICAL_REFERENCE.md updated.
- CI keeps the checks the package depends on: `tests.test_build_cleanup`,
  version stamp, `verify_package.py`, artifact upload.
- Fixed a pre-existing break in `main`: commit `b9f4b17` pointed the
  upload-artifact patterns at `COLOURLAB_OUTPUT_ROOT`, which is outside the
  workspace, and upload-artifact v4 rejects those patterns:

  > Invalid pattern 'D:\a\SteamVRColourLab\SteamVRColourLab/../builds/SteamVRColourLab/dist/SteamVRColourLab-Windows-x64.zip'. Relative pathing '.' and '..' is not allowed.

  Every run since run #6 (2026-10-08) failed at that step, after the build and
  `verify_package.py` had already passed. The build job now stages the ZIP, its
  checksum and `release-plan.json` into a workspace `ci-artifacts/` folder with
  the same `build/` + `dist/` layout, uploads that, and the publisher downloads
  it back into `ci-artifacts/`. The canonical output root stays external.

## Local evidence (this checkout, Windows)

- `test_windows.bat`: **128 tests, OK**, 17.8 s, exit 0.
- `.githooks/pre-push`: **128 tests, OK**, 17.1 s, exit 0. Without a test
  environment it exits 1 before any push.
- `actionlint` 1.7.12: workflow passes.
- CI version step reproduced locally: `release-plan.json` plus
  `github-output.txt` (`version=0.4.0`, `release=true`); source version restored
  afterwards.
- Staged artifact layout replayed locally through
  `tools.verify_package.verify_archive` with the publisher's exact call.
- Pre-existing local failure fixed: `test_shallow_history_is_rejected` cloned
  over `file:///C:/...`, which Git 2.53.0.windows.3 rejects; the test now uses
  `clone --depth=1 --no-local`, which still produces a real shallow clone.
- Logs: `../builds/SteamVRColourLab/build/logs/`.

## GitHub Actions evidence

Full runs, wall clock from `created_at` to `updated_at`:

| Run | Commit | Result | Wall |
| --- | --- | --- | ---: |
| #2 | `a38e9a2` | success | 138 s |
| #4 | `1691c98` | success | 119 s |
| #5 | `a0f8fe1` | success | 114 s |
| #6 | `b9f4b17` | failure (upload step) | 140 s |
| #7 | `096a9f6` | failure (upload step, inherited pattern) | 65 s |
| #8 | `13dbd04` | **success** | **81 s** |

Run #8 (https://github.com/AngelDark92/SteamVRColourLab/actions/runs/38226590011):
`Portable Windows x64` 62 s (cleanup test 16 s, build 27 s, verify 2 s, stage
1 s, upload 1 s), `Publish verified release` 13 s. Artifact
`SteamVRColourLab-0.4.0-Windows-x64`, 23,688,888 bytes. Run #7 exercised the
same jobs without the publisher in 65 s.

The `feat` commit already in `main` requested a minor bump, so run #8 also
published release `v0.4.0` from `13dbd04`. Downloaded the published ZIP and
checksum from the release: SHA256 matches
(`c9ff7484a6385782c53a312782d0c776146a2091a62c93f59709d1eed4f5e9b6`) and
`BUILD_INFO.json` reports version `0.4.0`, commit `13dbd04`.

Remaining Node 20 deprecation warning for the pinned `actions/checkout` and
`actions/upload-artifact` SHAs; the runner force-runs them on Node 24 and they
still pass. Headset runtime behavior is unchanged and still requires local
SteamVR validation.
