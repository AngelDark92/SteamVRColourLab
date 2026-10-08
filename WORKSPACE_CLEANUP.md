# Build output relocation - 2026-10-08

The output root is now
`D:\Angelo\Desktop\SteamLink-GalaxyXR-Windows-Toolkit-FULL\builds\SteamVRColourLab`.
Builders derive this as `../builds/SteamVRColourLab` from the source checkout, with
`COLOURLAB_OUTPUT_ROOT` available for other machines and CI.

Moved `build/`, `dist/`, `.venv/`, and source `__pycache__/` directories outside
the project: 20,056 files, 685,382,945 bytes (about 654 MiB). Every moved file was
verified against its original SHA-256 before rebuilding. This relocation freed
that space inside the checkout; it did not delete those files from the disk.
The file inventory is retained as `migration-20261008.json` in the output root.

The initial literal `builds/project` destination was corrected to the named
`builds/SteamVRColourLab` folder after the user's clarification. Only this
project's 24 owned entries were moved from the shared folder; all 20,061 files
(696,107,501 bytes, including the earlier inventory and validation outputs)
matched their pre-move SHA-256 hashes. The correction inventory is
`folder-correction-20261008.json` in the named output root. Other projects'
files were preserved in their existing locations.

Historical staging, previous-package backups, extracted validation copies,
dependency environments, logs and release plans were preserved externally.
Source `runs/`, historical `validation/` evidence, project metadata, and other
projects' existing output files were retained. Historical validation reports
keep their original paths as evidence of the runs that produced them.

Verification: 128 local tests passed, actionlint passed, the `.pyz` and Windows
portable builds succeeded, ZIP integrity/checksum/metadata and relocated
executable startup passed, and 6 saved portable data files remained byte-identical.
The successful portable build removed 61,479,265 bytes of its own disposable
staging and verified previous-package copies. No in-project build, dist,
environment or source bytecode directories were recreated by these checks.
GitHub Actions and headset runtime behavior were not tested in this task.

Regeneration from the source checkout:

```powershell
.\tools\Build-Portable.ps1
python -B tools\build_zipapp.py
..\builds\SteamVRColourLab\.venv\Scripts\python.exe -B -m unittest discover -v
```

Detailed validation logs are in the external `build/colourlab-relocation-*.log`
files. Future builds retain caches and saved data there, and automatically
clean only their own successful staging and verified previous-package files.

Checks repeated after the folder-name correction: 128 tests passed, both skills
passed validation, actionlint passed, the `.pyz` and Windows PowerShell 5.1
portable builds succeeded, and package verification and source launcher startup
passed. All 6 saved portable data files retained their hashes. The corrected
portable build reclaimed 61,484,401 bytes of its own disposable build files.
The fresh logs are `build/colourlab-named-folder-*.log` in the named output root.
Project `AGENTS.md`, `.agents/AGENTS.md`, cavecrew delegation guidance and the
`steamvrcolourlab-build` skill document the required output location.
