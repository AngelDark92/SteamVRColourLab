# SteamVRColourLab

Keep generated files outside this checkout. The default output root is
`../builds/SteamVRColourLab`, relative to the repository root. Use `build/` for staging,
dependency environments, caches and build logs, `dist/` for packages, and `.venv/`
for the source development environment, all beneath that external root.

On this workstation the canonical root is
`D:\Angelo\Desktop\SteamLink-GalaxyXR-Windows-Toolkit-FULL\builds\SteamVRColourLab`.
`project` is a placeholder for the project name; never use a literal
`builds/project` folder. Keep any subfolders beneath `builds/SteamVRColourLab`.
Apply this rule to every agent and delegated task, including build/test logs.
For packaging or build-path changes, use the project skill
[steamvrcolourlab-build](.agents/skills/steamvrcolourlab-build/SKILL.md).

`COLOURLAB_OUTPUT_ROOT` overrides the root for builders, artifact verification
and source launchers. `tools/Build-Portable.ps1` also accepts `-OutputRoot`.
Keep CI artifact paths and the publisher's `build/` + `dist/` layout consistent.
Use overrides for another host or CI while retaining the project folder name,
unless the user explicitly requests a different destination.
Disable source bytecode generation during build/test commands.

Preserve saved `runs` and `settings`, unknown files in previous packages, and
historical validation evidence during cleanup. Validate resolved paths and
reject junctions/symlinks before moving or deleting generated trees.

## Agent host setup

This repository carries instruction files for several agent hosts. Each host
reads a different subset:

- **Hermes** reads this file and [.agents/AGENTS.md](.agents/AGENTS.md). Once the
  checkout is trusted (`hermes skills trust` in the repository root, once per
  machine), it also loads the project skills in [.agents/skills/](.agents/skills/).
- **Codex / Copilot** read `.github/agents/` and any `.codex/` presets.
- **Claude Code** reads `CLAUDE.md`.

Hermes ignores `.github/agents/`, `.github/copilot-instructions.md`, and
`.codex/`. Those presets stay for the other hosts. The Hermes equivalents:

- Delegated work uses the `delegate_task` tool, not named agent presets. Paste
  the role contract from
  [.agents/skills/cavecrew/references/hermes-role-contracts.md](.agents/skills/cavecrew/references/hermes-role-contracts.md)
  into each child's `context`, together with the goal and every path. A child
  starts with a fresh conversation and inherits the parent's tools and model.
  Children cannot call `clarify`; keep the `ambiguous. ask:` terminal line.
- The `cavecrew*` and `caveman*` skills in `.agents/skills/` are third-party and
  assume Claude Code or Anthropic hooks. Each carries a Hermes note where its
  mechanics differ. See [README.md](README.md#agent-instructions).
