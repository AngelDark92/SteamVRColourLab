# caveman-compress under Hermes

The `scripts/` in this skill drive two LLM backends: the `ANTHROPIC_API_KEY` SDK
path and the `claude --print` CLI fallback (see `scripts/compress.py`,
`call_claude`). Under Hermes, neither is required — the Hermes agent compresses
the file itself with the tools it already has.

## Preferred path (no API key, no `claude` CLI)

1. `read_file` the target.
2. Compress the prose per this skill's Compression Rules, leaving every code
   block, inline code span, URL, path, command, and heading exact.
3. Write the backup first, then the compressed file — see Backup path below.
4. Apply the same validator rules the scripts use: headings, fenced code, inline
   code, URLs, and file paths must survive byte-for-byte. Re-read and diff if
   anything is uncertain; a failed validation leaves the original untouched.

Do not overwrite the original before the backup exists.

## Fallback path (scripts)

The scripts still work when a Claude model is reachable, but they send raw file
bytes to a third-party API. Two consequences:

- `ANTHROPIC_API_KEY` unset and no `claude` on `PATH` → the subprocess raises
  `FileNotFoundError`. That is a hard stop, not a retry.
- The skill refuses sensitive basenames and path components before reading
  (`.env`, `credentials*`, `secrets*`, `id_rsa*`, `*_key`, `.*_token*`,
  `.ssh`, `.aws`, and similar — see `scripts/compress.py`). Under Hermes the
  same denylist applies, whether the agent or the script does the compression.

## Model note

`CAVEMAN_MODEL` selects the Anthropic model in the fallback path. It does nothing
for the Hermes path — the Hermes agent uses the session model. There is no
per-subagent model pin in `delegate_task`; children inherit the parent model.

## Backup path (unchanged)

The human-readable copy lives out of tree, never beside the source, so skill
auto-loaders do not re-ingest it as a live file:

- Windows: `%LOCALAPPDATA%\caveman-compress\backups\<parent-dir-name>\`
- else: `$XDG_DATA_HOME/caveman-compress/backups/<parent-dir-name>/`, else
  `~/.local/share/caveman-compress/backups/<parent-dir-name>/`

## What Hermes loads

Under Hermes the live context files are `.hermes.md`, the `AGENTS.md` chain,
`CLAUDE.md`, and `.cursorrules` — see `references/project-context-files.md` in the
`hermes-agent` skill. Compressing `CLAUDE.md` is pointless in a repo that already
ships an `AGENTS.md`: Hermes picks the first match only (`.hermes.md` →
`AGENTS.md` → `CLAUDE.md` → `.cursorrules`), so a lower-priority file never loads.
Compress the file Hermes actually reads — `AGENTS.md` or `.hermes.md` here.
