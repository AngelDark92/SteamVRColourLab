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

## Local evidence (this checkout, Windows)

- `test_windows.bat`: **128 tests, OK**, 17.8 s, exit 0.
- `.githooks/pre-push`: **128 tests, OK**, 17.1 s, exit 0. Without a test
  environment it exits 1 before any push.
- `actionlint` 1.7.12: workflow passes.
- CI version step reproduced locally: `release-plan.json` plus
  `github-output.txt` (`version=0.4.0`, `release=true`); source version restored
  afterwards.
- Pre-existing local failure fixed: `test_shallow_history_is_rejected` cloned
  over `file:///C:/...`, which Git 2.53.0.windows.3 rejects; the test now uses
  `clone --depth=1 --no-local`, which still produces a real shallow clone.
- Logs: `../builds/SteamVRColourLab/build/logs/` (`pre-change-suite.txt`,
  `post-change-suite.txt`, `pre-push-hook.txt`, `ci-version-step/`).

## Not verified here

No push was made, so no GitHub Actions run was observed; hosted runner time for
the new workflow is unmeasured. Headset runtime behavior is unchanged and still
requires local SteamVR validation.
