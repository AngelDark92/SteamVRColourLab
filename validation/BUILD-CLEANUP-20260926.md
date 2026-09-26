# Portable build cleanup — 2026-09-26

Before this change, every successful build retained staging and a complete
previous-package copy. Initial `build` inventory: 575,165,608 bytes. There are
no nested repositories or reparse points in the audited output trees. No running
application/build process depended on those directories at the initial audit.

## Implemented behavior

Only the current invocation's `staging-TIMESTAMP` and `previous-TIMESTAMP` paths
are cleanup candidates. The builder runs cleanup after creating the ZIP and
checksum and restoring local `runs`/`settings`. Old generated files are removed
only when their hashes match the old ZIP, whose checksum is verified before it
is replaced. Restored user files are removed from the temporary backup only
when the new copy matches. Unknown, edited, or unrestored files remain.

All candidate/destination trees are checked before deletion; out-of-root paths,
links, and nested Git/Codex/Agents metadata refuse cleanup. Failures retain
remaining files and return the reason. `-KeepBuildFiles` preserves working files
after successful builds. Failed builds never enter the cleanup block.

## Verification

- 128 local tests passed, including 8 Windows cleanup tests with grouped cases
  for missing/corrupt checksums, unsafe ZIP entries, junctions, protected
  metadata, modified files, absent restored data, and historical path isolation.
- PowerShell parsing, actionlint, and independent review passed.
- Full build 1 (PowerShell 7): removed 61,473,894 bytes / 1,099 files; staging
  and previous folder `20260926-130426-602` no longer exist.
- Full build 2 (Windows PowerShell 5.1): removed 61,479,851 bytes / 1,100 files;
  staging and previous folder `20260926-130534-804` no longer exist.
- All 6 original user files have unchanged SHA256 after both builds.
- Final ZIP checksum, content/commit/version, technical reference inclusion,
  and relocated EXE help/version passed with external Python removed from PATH.
- Local builds used source baseline `8ae9a5a` plus this patch, app fallback
  version 0.2.1. The GitHub workflow stamps the release version separately.
- Published implementation commit: `1691c98bebcfc9e1436dba52aa030603812d9898`.
- [GitHub run 36237861820](https://github.com/AngelDark92/SteamVRColourLab/actions/runs/36237861820)
  passed all jobs. Windows cleanup tests passed 8/8; its fresh build removed
  10,943,782 staging bytes / 17 files. Package verification confirmed version
  0.3.1 and the exact implementation commit. Release v0.3.1 was published.

The removed byte totals include temporary copies created by each build; they
are not a claim that the historical backlog shrank by their combined size.
Detailed local evidence: `build-cleanup-data-before.json`,
`build-cleanup-run-1.json`, `build-cleanup-run-2.json`, and the 3 test/build logs
under `build/cleanup-*`. No headset/SteamVR runtime validation was performed.

## Existing folders and space

Measured before building; historical folders were not swept by this patch.

| Category | Bytes | Deletion guidance |
| --- | ---: | --- |
| 6 old `build/portable/staging-*` folders | 68,733,372 | Generated intermediates; removable once diagnostics are no longer needed. |
| `build/portable/venv-*` | 99,886,281 | Recreated by builder; installed Python and network required. Kept as reusable cache. |
| `build/ci-test-venv` | 35,578,676 | Disposable local test dependencies; next portable build does not use it. |
| `build/actionlint` | 9,096,324 | Disposable workflow checker; next portable build does not use it. |
| `build/portable/relocated-final-021` | 51,728,839 | Old extracted verification copy with no saved data. |
| `build/portable/previous-*` | 258,340,829 | Historical backups: check for modified/custom files before deletion. |
| `build/portable/relocated-check` | 51,718,014 | Preserve its distinct validation runs first (6 files, 9,207 bytes). |
| `.venv` | 36,019,037 | Source-launch environment; recreatable, outside build cleanup. |

Preserved: current `dist` package/ZIP/checksum and user data, historical evidence,
source/metadata directories, and the user's pre-existing LICENSE edit. The small
license cache (2,392 bytes) remains reusable. No current-run cleanup is deferred.
Regenerate output with `tools/Build-Portable.ps1`; tests use
`python -m unittest tests.test_build_cleanup -v` on Windows.
