# pqn-daily

Select, file, create, optionally refresh a managed task roundup, and open one date-shaped note (`YYYY-MM-DD.md`) in its canonical home at `resources/daily_notes/YYYY/MM/`. No LLM.

## What it does

The workflow preserves its original filing behavior and adds a safe missing-date authoring branch:

1. **`resolve_target`** finds an existing source from a path or basename. Basename search is scoped to vault root, `inbox/` (any depth), and `resources/daily_notes/` (any depth). When the selected target is an unambiguous date and missing-note creation is enabled, a zero-match result enters the creation branch instead of escalating. Arbitrary missing paths never do.
2. **`detect_shape`** requires `YYYY-MM-DD.md` and a real calendar date.
3. **`inspect_parent`** allows vault root, `inbox/...`, and `resources/daily_notes/...` for existing notes. It rejects `projects/`, `areas/`, `archive/`, and other `resources/` subtrees.
4. **`compute_destination`** derives `resources/daily_notes/YYYY/MM/YYYY-MM-DD.md` from the selected date and detects an existing canonical note.
5. **`check_collision`** refuses destination and basename collisions. It never overwrites or merges.
6. **`compose_note`** preserves the existing filing behavior: migrate tail backmatter to frontmatter and add a missing H1. A missing note is composed as exactly `# YYYY-MM-DD\n\n`, with no frontmatter or template.
7. **`compose_task_roundup`** runs only with `--task-roundup`. It scans tasks relative to the selected daily-note date, renders the default `pqn-tasks` report one heading level deeper, and inserts or replaces one marked region in the composed body. Ambiguous markers escalate before any write.
8. **`move_file`** is gated by `--apply`. Existing loose notes are atomically written to the destination and then removed. Missing notes are atomically created at the destination. Existing canonical notes remain idempotent.
9. **`validate_after`** runs scoped validation after an applied move, rewrite, or creation.

No dry-run creates directories, writes a note, removes a source, or opens a nonexistent planned path.

Editor launching happens outside the workflow after a successful result. The configured argv receives the absolute source or destination path as its final argument and runs with `shell=False`. Editor failure does not roll back a completed vault action.

## Usage

```bash
# Select today. Safe defaults report an existing note or escalate if missing.
pqn-daily --vault ~/notes
pqn-daily --vault ~/notes --today

# Existing positional filing behavior remains dry-run and non-opening by default.
pqn-daily --vault ~/notes 2026-05-12
pqn-daily --vault ~/notes 2026-05-12 --apply

# Select another date and plan or apply creation when it is missing.
pqn-daily --vault ~/notes --date 2026-05-12 --create-missing
pqn-daily --vault ~/notes --date 2026-05-12 --create-missing --apply

# Open an existing note, or create then open the canonical note.
pqn-daily --vault ~/notes --date 2026-05-12 --open
pqn-daily --vault ~/notes --date 2026-05-12 --create-missing --apply --open

# Plan, then write or refresh the default pqn-tasks roundup.
pqn-daily --vault ~/notes --date 2026-05-12 --task-roundup
pqn-daily --vault ~/notes --date 2026-05-12 --task-roundup --apply

# Create a missing note with its first managed roundup.
pqn-daily --vault ~/notes --date 2026-05-12 --create-missing --task-roundup --apply
```

Bare invocation is equivalent to `--today` for selection only. `target` accepts a vault-relative path or basename, with or without `.md`, and cannot be combined with `--today` or `--date`. Positional automation keeps its current write gate and never opens by default.

`--create-missing` / `--no-create-missing` and `--open` / `--no-open` override config in either direction. Vault discovery follows the [standard order](../configuration.md).

`--task-roundup` is explicit per invocation. Without it, `pqn-daily` does not scan the vault for tasks. The first integration slice intentionally does not proxy `pqn-tasks` filters or add a config default.

Exit codes:

- `0` - successful plan, move, create, open, or idempotent existing-note result.
- `1` - workflow escalation/runtime error or editor launch failure.
- `2` - invocation, vault, or configuration problem.

## Configuration

```yaml
workflows:
  daily:
    create_missing: false
    open_existing: false
    editor:
      - code
      - --reuse-window
```

`create_missing` and `open_existing` default to `false`. `editor` has no default because the workflow does not guess an OS-specific editor. It must be a non-empty argv list of non-empty strings. The resolved note path is appended as the final argument.

When `--task-roundup` is present, the report reuses `workflows.tasks.date_fields`; there is no duplicate daily-specific date setting. Invalid task date-field config affects only a requested roundup, not ordinary `pqn-daily` runs.

## Task roundup

The roundup uses the selected daily note's date as the `pqn-tasks` reference date. Its fixed first-slice report settings are the normal unfiltered defaults: a 7-day horizon, overdue/due-today/upcoming grouping, no unscheduled tasks, no archive, type, or Quest filter, and the effective task date-field precedence.

The workflow owns exactly one region:

```markdown
<!-- pqn-daily:task-roundup:start -->
## Tasks as of 2026-05-12 (within 7 day(s))

### Overdue (1)
- [[Build Raised Beds]] Order soil (due 2026-05-11)
<!-- pqn-daily:task-roundup:end -->
```

The content is the existing `pqn-tasks` markdown report with headings demoted one level. Bullets stay plain `-` items, never live task checkboxes, so the next scan cannot count generated output as new tasks.

With no marked region, the workflow appends one after the user-owned body. With exactly one valid region, it replaces that region in place. A byte-identical refresh is `unchanged` and does not force an in-place rewrite. Existing unmarked Tasks headings remain user-owned and are never adopted or overwritten.

Markers count only as exact standalone lines outside backtick or tilde fenced code. Orphaned, reversed, nested, or duplicate marker sequences are ambiguous and escalate before `move_file`; the workflow does not guess or append a second generated region. A note that ends inside an unclosed fence also escalates when insertion would otherwise place the new region inside code.

Dry-run performs the full vault scan, rendering, marker validation, and composition, then reports what it would insert or replace without writing. Under `--apply`, the roundup is part of the same atomic destination content as the existing move, create, or in-place rewrite. Any report or marker failure therefore occurs before vault mutation.

Apply also verifies that an existing source note has not changed since composition began and preserves its file mode. A detected concurrent edit escalates rather than being overwritten; if an edit races the final write-first/remove-second move, the edited source is retained alongside the planned destination.

## Opening behavior

Opening occurs only after the workflow succeeds and only when a real file exists:

| Result | Path opened |
| --- | --- |
| Existing loose note, dry-run | Existing source |
| Existing loose note, apply | Canonical destination |
| Existing canonical note | Canonical note |
| Missing note, dry-run creation plan | Nothing |
| Missing note, applied creation | Canonical destination |

Escalations and workflow errors never launch the editor. A missing editor setting, missing executable, or non-zero editor exit returns code `1` and populates `open_error`. Any successful move or creation remains complete.

## JSON contract

Existing fields are preserved. Creation, opening, and task-roundup fields are additive:

```json
{
  "vault": "/Users/me/notes",
  "apply": true,
  "ok": true,
  "plan": {
    "source": null,
    "destination": "resources/daily_notes/2026/09/2026-09-02.md",
    "date": "2026-09-02",
    "h1_inserted": true,
    "frontmatter_migrated": false,
    "already_at_destination": false,
    "would_create": true
  },
  "moved": false,
  "created": true,
  "task_roundup": {
    "action": "insert",
    "applied": true,
    "reference_date": "2026-09-02",
    "due_in": 7,
    "group_by": "due",
    "date_fields": ["due", "scheduled", "start"],
    "include_archive": false,
    "unscheduled": "hide",
    "files_scanned": 142,
    "summary": {
      "total": 3,
      "overdue": 1,
      "due_today": 1,
      "upcoming": 1,
      "unscheduled": 0
    }
  },
  "opened": true,
  "open_path": "resources/daily_notes/2026/09/2026-09-02.md",
  "open_error": null,
  "escalation": null,
  "error": null,
  "run_id": "a1b2c3d4e5f6"
}
```

`would_create` distinguishes a missing-note branch in both dry-run and apply mode. `created` is true only after the file is written. `opened` and `open_path` are set only after a successful process launch. `open_error` records a launch failure separately from successful vault work.

`task_roundup` is `null` when the flag is absent. When requested, `action` is `insert`, `replace`, or `unchanged`; `applied` says whether write consent was present. The remaining fields describe the reused task-report scope and summary without duplicating task descriptions in the daily JSON or trace.

For existing notes, `source`, `destination`, `moved`, `h1_inserted`, `frontmatter_migrated`, and `already_at_destination` retain their prior meanings.

## Scope

- No templates or frontmatter for authored daily notes.
- No routine-task prepopulation or recurrence generation.
- No task mutation or proxy flags for custom `pqn-tasks` reports.
- No implicit or configured task-roundup activation.
- No bulk migration.
- No implicit `--apply`.
- No shell command strings or OS editor discovery.
- No `git mv` integration; filing remains atomic write plus source removal.
