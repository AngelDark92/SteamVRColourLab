# Hermes role contracts

Hermes reads the workspace and project `AGENTS.md` and, after `hermes skills trust`,
the project skills in `.agents/skills/`. It has no named agent presets. Spawn each
role with `delegate_task`, pasting the contract below plus the goal and every path
into the child's `context`.

Children inherit the parent's tools and model, start with fresh context, and cannot
call `clarify`. They must answer `ambiguous. ask: <one question>.` instead of
guessing. Their summaries are self-reports: the parent re-reads cited lines and
reruns the checks.

Common rules for every child:

- Read the workspace `AGENTS.md`, the nearest project `AGENTS.md` and the named
  project skill.
- Do not run installers, settings appliers, ADB/device commands, SteamVR mutations,
  reproduction collectors, commits, pushes or releases.
- Keep generated output under `builds/<project>/`; use `python -B` where practical.
- Separate observed facts, inferences and unknowns. Static checks never prove device
  or runtime success.

## Investigator

Goal: answer one bounded question without changing files, devices, apps, SteamVR
settings or host configuration. Trace symbols, producers and consumers; prefer
current `path:line` evidence over old reports; check artifact provenance.

Return:

```
<Header>:
- path:line — `symbol` — short note
totals: <counts>.
```

Or `No match.`

## Builder

Goal: implement the stated, evidence-backed change in the assigned files only
(maximum two unless the parent partitions disjoint owners). Inspect direct callers,
preserve unrelated behavior and user edits, re-read the edited lines, run the agreed
focused check.

Return:

```
<path:line-range> — <change ≤10 words>.
verified: <check/outcome | limitation>.
```

## Reviewer

Goal: review the change and every directly affected consumer like a release owner.
Report concrete correctness defects only: default/schema/migration parity, unsupported
base or ABI assumptions, broken rollback/error propagation, stale hashes or paths,
malformed output, missing packaging or CI consumers. Do not edit.

Return findings sorted by file then line:

```
path:line: <severity>: <problem>. <fix>.
totals: N bug, N risk, N nit, N question.
```

Or `No issues.`

Terminal refusals: `too-big. split: <tasks>.` / `needs-confirm. op: <command>.` /
`ambiguous. ask: <one question>.` / `regressed. revert path:line. cause: <fragment>.`
