# Running headless

Everything `pqn-*` does interactively also works from a cron job or
an agent wrapper. This doc covers the four pieces you need:

1. Structured output (`--format json`) for piping to `jq` or other
   tools.
2. The JSONL trace each run writes for after-the-fact inspection.
3. The exit-code contract shared by every CLI, so cron can tell
   "fine" from "broken" from "you held it wrong."
4. Resolving the vault in contexts where `cwd` is unreliable.

The last section is concrete crontab examples per workflow, plus
a "what not to cron" callout.

## Structured output: `--format json`

Every workflow CLI accepts `--format json` and prints a single JSON document
to stdout. Text output goes to stderr, so you can mix the two
without polluting the JSON.

```bash
pqn-validate --vault /path/to/vault --format json | jq '.summary'
```

Sample shapes:

```bash
# pqn-validate: vault, files_scanned, checks_run, summary, issues[]
pqn-validate --format json | jq '.summary.total_issues'

# pqn-ingest: run_id, files[] (each with ok, plan, escalation, error)
pqn-ingest --format json | jq '[.files[] | select(.ok == false)]'

# pqn-create / pqn-daily / pqn-archive: run_id, ok, plan, escalation,
# error, and action booleans such as written / moved / created / opened
pqn-archive "Some Project" --format json | jq '.plan.outcome_action'
```

For the full field-by-field contract, see the per-workflow doc
under [`workflows/`](workflows/).

## The JSONL trace

Every run writes a one-line-per-event trace at:

```
$XDG_STATE_HOME/para-quest-notes/runs/<timestamp>.jsonl
```

falling back to `~/.local/state/para-quest-notes/runs/` when
`XDG_STATE_HOME` is unset. The exact path is printed in the text
output's `trace:` line and is also recoverable from `--format json`
output via `run_id`.

The trace records every LLM call (prompt, response, latency) and
every workflow step (inputs, outputs, escalations). It's the source
of truth when a run's behavior surprises you. Tail it like any
JSONL:

```bash
tail -f ~/.local/state/para-quest-notes/runs/run-*.jsonl | jq .
```

Wrapper scripts that need to surface "what the LLM said" without
seeing note bodies should consume the trace, not parse stdout.

## Exit codes

All five CLIs share the same contract:

| Code | Meaning |
|---:|---|
| `0` | Success. Work happened (or would happen, for dry-runs) and nothing escalated. |
| `1` | The run completed but at least one item errored or escalated. Triggered when any `pqn-ingest` file fails, when `pqn-create` / `pqn-daily` / `pqn-archive` escalate or hit a runtime error, when a requested daily editor launch fails, or when `pqn-validate` finds errors (or any warning with `--strict`). |
| `2` | The run couldn't even start. Invalid arguments, unresolvable vault, malformed config. Always printed to stderr. |

In cron contexts, treat `2` as "page me" and `1` as "look at the
output / trace when convenient." Both are non-zero, so `set -e`
catches both unless you explicitly tolerate `1`.

## Vault resolution in cron

`cwd`-based discovery isn't reliable from cron, where the working
directory may be `/` or the user's home. Use one of:

1. `--vault /absolute/path` on the command line.
2. `PARA_QUEST_VAULT=/absolute/path` in the cron environment.
3. `vault:` in `~/.config/para-quest-notes/config.yaml`.

`--vault` wins if both are set. See
[`configuration.md`](configuration.md) for the full discovery order.

## Crontab examples

Each example assumes the user has `uv` on `PATH`. If your cron
doesn't pick up your shell's `PATH`, either set it explicitly at
the top of the crontab or use an absolute path to `uv`.

```cron
# Cron-friendly environment
PATH=/usr/local/bin:/usr/bin:/bin
PARA_QUEST_VAULT=/home/me/Notes
```

### `pqn-validate` — nightly health check

```cron
# 02:00 daily: warn if the vault has structural issues. --strict
# treats warnings as errors so the exit code catches drift early.
0 2 * * *  uv run pqn-validate --strict --format json \
             > /var/log/pqn/validate.json 2>> /var/log/pqn/validate.err
```

`--format json` here makes the output easy to diff between runs
or feed to a monitoring agent. Exit-code `1` from `--strict` is
the signal you want; pipe it through your usual cron-mail or
alerting setup.

### `pqn-ingest` — nightly dry-run digest, never auto-applies

```cron
# 03:00 daily: triage proposal only; never auto-applies. Review
# the JSON in the morning before deciding to --apply.
0 3 * * *  uv run pqn-ingest --format json \
             > /var/log/pqn/ingest-$(date +\%F).json 2>&1
```

There's no `--apply` here on purpose. See "What not to cron" below.

### `pqn-create` — usually NOT a cron job

`pqn-create` takes per-note `--title` / `--type` / `--supports`
arguments, so it doesn't fit a recurring schedule. The exception
is templated wrappers (e.g., "create a weekly retro note from a
shell script"):

```cron
# Mondays at 09:00: scaffold this week's retro as a Project.
0 9 * * 1  uv run pqn-create \
             --type project --title "Retro $(date +\%G-W\%V)" \
             --quest-kind none --supports '[[Work]]' --apply
```

### `pqn-daily` — file yesterday's daily note each morning

If your editor authors `<vault>/2026-05-15.md` and you'd rather
not move it by hand:

```cron
# 06:00 daily: file yesterday's daily note if it exists.
0 6 * * *  uv run pqn-daily "$(date -d 'yesterday' +\%F)" --apply \
             2>> /var/log/pqn/daily.err
```

Because this invocation does not enable missing-note creation, `pqn-daily` exits `1` if the target does not exist. This preserves the existing cron-safe signal that yesterday's note was never authored.

### `pqn-archive` — usually NOT a cron job

Archive needs a specific Project target, the same RAM-hungry model
the user picked, and (with `--generate-outcome --apply`) the LLM to
write prose. Run it interactively or from a wrapper that's already
sure the Project is done. See "What not to cron" below.

## What not to cron

A few patterns that look reasonable but bite:

- **`pqn-ingest --apply`.** The pilot rewrites incoming wikilinks
  across the vault when it renames a note. Reverting that by hand
  is tedious. Cron-apply on top of a small / new model is a fast
  way to mangle a vault overnight. Run dry-run on a schedule;
  apply interactively.
- **`pqn-archive --generate-outcome --apply`.** This loads a local
  LLM (potentially 18 GB for `granite4.1:30b`), writes prose into
  your notes, and moves the file. Don't run it on a schedule;
  archiving is per-Project anyway.
- **Anything with a real model on a laptop that's asleep at the
  scheduled time.** Use `--fake` only in CI; on a real machine,
  prefer `--format json` dry-runs.
- **Two `pqn-*` jobs at overlapping times that both call the
  model.** Local Ollama is memory-bound; the eval harness
  serializes models on purpose. Stagger your cron jobs by at
  least the model's typical end-to-end run time (a couple of
  minutes is usually enough for `granite4.1:30b`).
