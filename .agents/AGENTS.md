# Hermes project entry

Read [../AGENTS.md](../AGENTS.md) and the project skill named there. Generated
output, build logs and test logs belong under `../builds/SteamVRColourLab`.

Hermes has no named agent presets. Delegate with `delegate_task`, pasting the role
contract from
[cavecrew/references/hermes-roles.md](skills/cavecrew/references/hermes-roles.md)
into each child's `context` with the goal and every path. Children cannot ask
questions; keep the `ambiguous. ask: <missing line>.` refusal. Run
`hermes skills trust` once in this checkout to load the project skills.
