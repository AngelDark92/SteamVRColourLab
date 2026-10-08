# caveman-stats under Hermes

This skill is delivered by Claude Code hooks (`hooks/caveman-mode-tracker.js`)
reading the Claude Code session JSONL log. Hermes has neither the hook nor that
log, and it injects no stats. There is no Hermes equivalent of `/caveman-stats`
that reports real numbers — use the Hermes accounting surfaces instead, and never
invent a savings figure.

## Hermes accounting surfaces

- `/usage` in a Hermes session — provider credits, rate limits, and where
  applicable a live input/output token count from the Hermes session store.
- `~/.hermes/logs/` and the session store at `~/.hermes/state.db` — the
  authoritative record of turns and token usage for this instance.
- `hermes dump` — setup summary for support/debugging.
- `hermes status` — component status.

The Hermes store counts the *whole* session, not a caveman-vs-baseline delta.
There is no measured "savings versus non-caveman" number on this host.

## The rule-overhead question

Claude Code numbers in this skill assume ~1,250 input tokens per turn of injected
caveman rules and subtract that to get a net. Hermes injects a different rule
text, so that constant does not carry over. If you quote a net at all, state the
overhead assumption explicitly and label it an estimate — do not present it as a
Hermes measurement.

## If you want real numbers

Measure directly with the Hermes session store: compare token counts across two
sessions of the same task, one caveman and one not. Report session ids and the
`/usage` figures. That is an actual measurement; everything else is an estimate.
