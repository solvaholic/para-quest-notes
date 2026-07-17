# pqn-tasks

Report open tasks that carry Obsidian Tasks due dates, bucketed into
overdue / due today / due soon. Read-only. No LLM.

## What it does

Walks the vault, scans every note for task lines outside fenced code
blocks, and reports the **open** (`- [ ]`) and **in-progress**
(`- [/]`) tasks that carry a `📅` due date. Each task is bucketed
relative to a reference date (today):

- **overdue** — due before today
- **due today** — due today
- **upcoming** — due within `--due-in N` days (default 7)

Tasks due beyond the horizon, tasks with no due date, and completed
(`- [x]`) / cancelled (`- [-]`) tasks are not reported.

Obsidian Tasks emoji dates are the canonical syntax: `📅` due, `⏳`
scheduled, `🛫` start. All three are parsed and surfaced in the JSON
output, but **bucketing is on the due date** — the report answers
"what's due when". Scheduled/start-only tasks (no `📅`) are not reported
in v1.

### Scan scope

The whole vault **except `archive/`** is scanned by default —
`areas/`, `projects/`, `resources/` (including daily notes under
`resources/daily_notes/`), and `inbox/`. A due date is a due date
wherever it lives; quick-capture tasks routinely land in `inbox/` and
daily notes. `archive/` is excluded because its tasks are
completed/stale (`pqn-archive` rewrites open tasks to cancelled on
archive). Pass `--include-archive` to include it.

### Grouping

`--group-by` controls how the markdown output is organized:

- **`due`** (default) — group by urgency bucket.
- **`quest`** — group by the Main Quest each task serves. A task's note
  declares `supports:` (a wikilink to a Main or Side Quest); Side
  Quests are rolled up to the Main Quest they support.
- **`area`** — group by the Area named directly in `supports:` (the
  Side Quest / Capability / Main Quest, without the roll-up).

Tasks in notes with no `supports:` (inbox captures, daily notes) group
under **unassigned**. When grouping by quest or area, a task whose note
supports several targets appears under each — the grouped view is a
lens, not a partition, so group counts can exceed the task total.

## Usage

```bash
# What's overdue or due in the next 7 days (markdown, default).
pqn-tasks --vault ~/notes

# Look two weeks ahead.
pqn-tasks --vault ~/notes --due-in 14

# Only what's already overdue.
pqn-tasks --vault ~/notes --overdue

# Group by Main Quest.
pqn-tasks --vault ~/notes --group-by quest

# Only tasks serving a specific Quest.
pqn-tasks --vault ~/notes --quest "[[Health]]"

# Structured output for agents / other tools.
pqn-tasks --vault ~/notes --format json
```

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)): `--vault` →
`PARA_QUEST_VAULT` → walk up from cwd → `vault:` in `config.yaml`.

The markdown output uses plain `-` bullets (not `- [ ]` checkboxes)
with the source note wikilinked, so a roundup can be pasted into a
daily note without re-parsing as live, duplicate tasks. Output is
stdout only; wiring a roundup into a daily note is a later `pqn-daily`
concern, not part of this command.

Exit code is `0` on success, `2` on an invocation problem (vault not
found). The reporter never fails on the *contents* of the vault — an
empty report is a valid result.

## JSON contract

```json
{
  "vault": "/path/to/vault",
  "reference_date": "2026-07-17",
  "due_in": 7,
  "group_by": "due",
  "include_archive": false,
  "files_scanned": 142,
  "summary": {
    "total": 3,
    "overdue": 1,
    "due_today": 1,
    "upcoming": 1
  },
  "tasks": [
    {
      "path": "projects/Build Raised Beds.md",
      "line": 12,
      "description": "Order soil",
      "raw": "Order soil 📅 2026-07-10",
      "state": " ",
      "bucket": "overdue",
      "due": "2026-07-10",
      "scheduled": null,
      "start": null,
      "block_id": null,
      "supports": ["Maintain Home"],
      "areas": ["Maintain Home"],
      "quests": ["Health"]
    }
  ]
}
```

The `tasks` list is flat (grouping is a presentation concern applied to
the markdown output only) so consumers regroup on the per-task
`bucket`, `quests`, and `areas` fields. Field names are stable across
releases; new fields may be added, existing ones will not be renamed.

## Scope / non-goals (v1)

- **Read-only.** No task mutation. Batch-complete or reschedule are
  separate concerns that feed existing write workflows (e.g.
  `pqn-archive --cancel-open-tasks`).
- **Emoji syntax only.** Dataview inline fields (`[due:: 2026-05-15]`)
  and plain `- [ ]` checkboxes without emoji dates are not parsed.
- **Fixed `-` bullet rendering.** Configurable task-state
  representation is deferred.
- No recurrence generation — this reports tasks that already exist.
- No daily-note integration — stdout only.

## Gotchas

- **A due date is required to be reported.** A task with only a `⏳`
  scheduled or `🛫` start date (no `📅`) is parsed but not bucketed.
- **`--due-in 0`** reports only what is overdue or due today.
- **Grouped counts can exceed the total** when a note supports multiple
  Quests/Areas — the same task is listed under each.
