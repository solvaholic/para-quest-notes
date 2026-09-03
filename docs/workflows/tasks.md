# pqn-tasks

Report open tasks that carry Obsidian Tasks dates, bucketed into
overdue / due today / due soon. Read-only. No LLM.

## What it does

Walks the vault, scans every note for task lines outside fenced code
blocks, and reports the **open** (`- [ ]`) and **in-progress**
(`- [/]`) tasks that carry a tracked date. Each task is bucketed by its
**effective date** relative to a reference date (today):

- **overdue** — effective date before today
- **due today** — effective date is today
- **upcoming** — effective date within `--due-in N` days (default 7)

Tasks whose effective date is beyond the horizon, tasks with no tracked
date, and completed (`- [x]`) / cancelled (`- [-]`) tasks are not
reported.

### Which date buckets a task

Obsidian Tasks encodes three dates: `📅` **due** (deadline), `⏳`
**scheduled** (your "do date"), and `🛫` **start**. A task can carry any
combination. Its **effective date** — the one that decides its bucket —
is the first present date in a precedence order (default: due, then
scheduled, then start). All three raw dates are still surfaced in the
JSON output; `date_source` records which one drove the bucket.

Because the resolution *falls through* to the first date a task actually
has, a user who tracks only one kind of date is fully served with no
configuration: if you use `⏳` scheduled exclusively as your "do date"
(due dates you find demoralizing, start dates you can't predict), your
tasks bucket on their scheduled date automatically. Precedence only
matters for a task carrying several dates.

Use `--date-field` to change the precedence or narrow the set:

```bash
# Do-date-first: a scheduled date wins over a deadline when both exist.
pqn-tasks --vault ~/notes --date-field scheduled --date-field due

# Purist: only scheduled dates count; due-only tasks are ignored entirely.
pqn-tasks --vault ~/notes --date-field scheduled
```

A field you omit from `--date-field` is ignored, so the second form is
both a precedence *and* a filter.

Set a persistent default in `config.yaml` when the same date model applies to every run:

```yaml
workflows:
  tasks:
    date_fields: [scheduled, due, start]
```

Precedence is `--date-field` flags, then `workflows.tasks.date_fields`, then the built-in `[due, scheduled, start]` default. The configured value must be a non-empty list containing only `due`, `scheduled`, and `start`; invalid values fail loudly with exit code `2`.

### Scan scope

The whole vault **except `archive/`** is scanned by default —
`areas/`, `projects/`, `resources/` (including daily notes under
`resources/daily_notes/`), and `inbox/`. A due date is a due date
wherever it lives; quick-capture tasks routinely land in `inbox/` and
daily notes. `archive/` is excluded because its tasks are
completed/stale (`pqn-archive` rewrites open tasks to cancelled on
archive). Pass `--include-archive` to include it.

Use repeatable, include-only `--type` flags to restrict the report to PARA types:

```bash
# Projects only.
pqn-tasks --vault ~/notes --type project

# Projects and Areas, excluding Resources.
pqn-tasks --vault ~/notes --type project --type area
```

The filter matches `pqn-search` semantics: once any `--type` is active, notes with no resolvable PARA type are excluded. This includes untyped notes outside `projects/`, `areas/`, and `resources/`, such as captures under `inbox/`. Daily notes remain `resource` by path, even without frontmatter, so `--type resource` includes them.

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

# Only tasks serving a specific Quest (wikilink or bare name,
# matched case-insensitively — same as pqn-quests --quest).
pqn-tasks --vault ~/notes --quest "[[Health]]"

# Compose repeatable PARA-type and Quest filters.
pqn-tasks --vault ~/notes --type project --quest "[[Health]]"

# Bucket on your "do date" (scheduled) instead of deadlines.
pqn-tasks --vault ~/notes --date-field scheduled

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
  "date_fields": ["due", "scheduled", "start"],
  "include_archive": false,
  "types": ["project"],
  "quest": "health",
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
      "raw": "Order soil ⏳ 2026-07-14 📅 2026-07-10",
      "state": " ",
      "bucket": "overdue",
      "effective_date": "2026-07-10",
      "date_source": "due",
      "due": "2026-07-10",
      "scheduled": "2026-07-14",
      "start": null,
      "block_id": null,
      "supports": ["Maintain Home"],
      "areas": ["Maintain Home"],
      "quests": ["Health"]
    }
  ]
}
```

`effective_date` is the date that drove the bucket; `date_source` names
which field it came from (`due`, `scheduled`, or `start`) under the
report's `date_fields` precedence. The three raw date fields are always
surfaced so consumers can regroup. The `tasks` list is flat (grouping is
a presentation concern applied to the markdown output only) so consumers
regroup on the per-task `bucket`, `quests`, and `areas` fields. Field
names are stable across releases; new fields may be added, existing ones
will not be renamed.

`types` is the sorted include-only PARA-type filter, or `null` when unfiltered. `quest` is the normalized, lower-case Quest basename, or `null` when unfiltered. These fields describe the active report scope; they do not change the flat task item shape.

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

- **A task needs at least one *tracked* date to be reported.** With the
  default precedence that means any of `📅` / `⏳` / `🛫`; under a
  narrowed `--date-field` set, only the listed fields count.
- **`--date-field` is both precedence and filter.** Listing a subset
  (e.g. `--date-field scheduled`) drops tasks that carry none of the
  listed dates.
- **`--type` drops untyped notes.** Once a type filter is active, notes with neither recognized `type:` frontmatter nor a PARA directory are excluded. Daily notes still resolve to `resource` from their path.
- **`--due-in 0`** reports only what is overdue or due today.
- **Grouped counts can exceed the total** when a note supports multiple
  Quests/Areas — the same task is listed under each.
