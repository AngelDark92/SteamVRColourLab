---
name: cavecrew
description: Delegate a bounded search, a one- or two-file edit, or a diff review to compact investigator, builder or reviewer subagents. Use when context economy matters or an independent review is needed.
---

# Cavecrew

Three subagent roles return compact receipts instead of prose. Use them for a
bounded search, a surgical edit or an independent diff review. Use the main thread
or the built-in `explore`/`general` agents for broad design work or narrative
analysis.

## Call contract

Every call states all five lines. If one is missing, the role returns
`ambiguous. ask: <missing line>.` instead of guessing.

1. **Role** — `investigator`, `builder` or `reviewer`.
2. **Goal** — one answerable question or one stated change.
3. **Bound** — exact files or directories; nothing outside them.
4. **Evidence** — symptom, log line, failing check or diff to start from.
5. **Write authorization** — `read-only`, or the exact files a builder may edit.

## Roles

- **Investigator** — read-only. Reads `AGENTS.md` and the project skill, traces
  symbols and callers, returns `path:line` evidence and what it ruled out.
- **Builder** — edits only the assigned files (maximum two), preserves unrelated
  behavior, re-reads the edited lines and runs the agreed focused check.
- **Reviewer** — read-only. Reviews the changed path and every direct consumer,
  reports concrete defects only, sorted file then line.

A role stops rather than exceeding its bound, writing without authorization, or
guessing a binary/device fact. A delegation adds no permission.

## Receipts

Investigator:

```
<Header>:
- path:line — `symbol` — short note
totals: <counts>.
```

Or `No match.`

Builder:

```
<path:line-range> — <change ≤10 words>.
verified: <check/outcome | limitation>.
```

Reviewer:

```
path:line: <severity>: <problem>. <fix>.
totals: N bug, N risk, N nit, N question.
```

Or `No issues.`

Terminal refusals: `too-big. split: <tasks>.` / `needs-confirm. op: <command>.` /
`ambiguous. ask: <one question>.` / `regressed. revert path:line. cause: <fragment>.`

## Hosts

OpenCode discovers `.opencode/agents/cavecrew-*.md` from the nearest project. Use
those IDs from that checkout.

Hermes has no named presets. Run the roles as `delegate_task` children, pasting the
matching contract from [references/hermes-roles.md](references/hermes-roles.md) into
each child's `context` with the goal and every path. Children inherit the parent's
tools and model, cannot call `clarify`, and must keep the `ambiguous. ask:` line.
Their summaries are self-reports: re-read the cited lines and rerun the checks.

Drop compression for security warnings, irreversible-action confirmations and any
output where a fragment could be misread.
