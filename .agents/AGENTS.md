# Project agents and skills

Inherit [the project instructions](../AGENTS.md). All agents and project skills
must place generated build files, packages, caches, environments and build/test
logs under `../builds/SteamVRColourLab` relative to the repository root.
Preserve their existing subfolder structure. Never use literal `builds/project`.

Use [steamvrcolourlab-build](skills/steamvrcolourlab-build/SKILL.md) for build and
packaging work. Keep these instructions project-scoped.

Under Hermes, delegation uses the `delegate_task` tool, not named agent presets.
Paste the role contract from
[cavecrew/references/hermes-role-contracts.md](skills/cavecrew/references/hermes-role-contracts.md)
into each child's `context`, with the goal and every path. Run
`hermes skills trust` in the repository root once so these project skills load.
