# pqn-daily

Select, file, create, and optionally open one date-shaped note (`YYYY-MM-DD.md`) in its canonical home at `resources/daily_notes/YYYY/MM/`. No LLM.

## What it does

The workflow preserves its original filing behavior and adds a safe missing-date authoring branch:

1. **`resolve_target`** finds an existing source from a path or basename. Basename search is scoped to vault root, `inbox/` (any depth), and `resources/daily_notes/` (any depth). When the selected target is an unambiguous date and missing-note creation is enabled, a zero-match result enters the creation branch instead of escalating. Arbitrary missing paths never do.
2. **`detect_shape`** requires `YYYY-MM-DD.md` and a real calendar date.
3. **`inspect_parent`** allows vault root, `inbox/...`, and `resources/daily_notes/...` for existing notes. It rejects `projects/`, `areas/`, `archive/`, and other `resources/` subtrees.
4. **`compute_destination`** derives `resources/daily_notes/YYYY/MM/YYYY-MM-DD.md` from the selected date and detects an existing canonical note.
5. **`check_collision`** refuses destination and basename collisions. It never overwrites or merges.
6. **`compose_note`** preserves existing-note behavior: migrate tail backmatter to frontmatter and add a missing H1 without applying any selected template. For a missing note, it uses the shared creation substrate to load and parse an explicit or configured whole-note template, render the body with selected-date variables, preserve template metadata without generating PARA metadata, and enforce the daily H1 invariant. With no selected template, it preserves the exact `# YYYY-MM-DD\n\n` skeleton.
7. **`move_file`** is gated by `--apply`. Existing loose notes are atomically written to the destination and then removed. Missing notes use the same atomic no-overwrite publication path as `pqn-create`. Existing canonical notes remain byte-idempotent.
8. **`validate_after`** runs scoped validation after an applied move, rewrite, or creation.

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

# Select a whole-note template for missing-note creation.
pqn-daily --vault ~/notes --date 2026-05-12 --create-missing --template daily
pqn-daily --vault ~/notes --date 2026-05-12 --create-missing --template daily --apply

# Bypass a configured default template and keep the H1-only skeleton.
pqn-daily --vault ~/notes --today --create-missing --no-template --apply

# Open an existing note, or create then open the canonical note.
pqn-daily --vault ~/notes --date 2026-05-12 --open
pqn-daily --vault ~/notes --date 2026-05-12 --create-missing --apply --open
```

Bare invocation is equivalent to `--today` for selection only. `target` accepts a vault-relative path or basename, with or without `.md`, and cannot be combined with `--today` or `--date`. Positional automation keeps its current write gate and never opens by default.

`--create-missing` / `--no-create-missing` and `--open` / `--no-open` override config in either direction. `--template` and `--no-template` are mutually exclusive; selection precedence is explicit `--template`, explicit `--no-template`, `workflows.daily.template`, then the H1-only skeleton. Selecting a template does not enable missing-note creation or bypass `--apply`. Vault discovery follows the [standard order](../configuration.md).

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
    template: daily
    editor:
      - code
      - --reuse-window
```

`create_missing` and `open_existing` default to `false`; `template` defaults to null. Daily templates use `workflows.create.template_dir`, not a daily-specific directory. `editor` has no default because the workflow does not guess an OS-specific editor. It must be a non-empty argv list of non-empty strings. The resolved note path is appended as the final argument.

## Template behavior

Templates affect only creation of a missing daily note. An explicit or configured template is ignored when the selected note already exists, so a repeatable "open or create today" command never merges template content into user-owned bytes.

Dry-runs still resolve, load, parse, and render the selected template and complete normal destination/collision planning, but they do not create directories or files. Template frontmatter is parsed separately and never placeholder-rendered. Supplemental template metadata is retained, including tolerated legacy backmatter, but daily creation does not synthesize `type`, `quest-kind`, `supports`, `source_url`, or `created` metadata.

Daily template bodies use deterministic `string.Template.safe_substitute` semantics. Available variables are `$title`, `$date`, `$created`, `$year`, `$month`, and `$day`, all derived from the selected date. `$$` emits a literal dollar and unknown tokens such as `$supports` remain unchanged. After rendering, a custom first ATX H1 is preserved; otherwise `# YYYY-MM-DD` is prepended. See [Note Templates](../templates.md) for the shared parser, fallback, and escaping contract.

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

Existing fields are preserved. Creation and opening fields are additive:

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
    "would_create": true,
    "body_source": "template:daily"
  },
  "moved": false,
  "created": true,
  "opened": true,
  "open_path": "resources/daily_notes/2026/09/2026-09-02.md",
  "open_error": null,
  "escalation": null,
  "error": null,
  "run_id": "a1b2c3d4e5f6"
}
```

`would_create` distinguishes a missing-note branch in both dry-run and apply mode. `body_source` is `"template:<name>"`, `"skeleton"`, or `"skeleton (template not found)"` when a missing-note body was composed, and null for an existing note. `created` is true only after the file is written. `opened` and `open_path` are set only after a successful process launch. `open_error` records a launch failure separately from successful vault work.

For existing notes, `source`, `destination`, `moved`, `h1_inserted`, `frontmatter_migrated`, and `already_at_destination` retain their prior meanings.

## Scope

- Templates are creation-only; they never apply to existing daily notes.
- No generated PARA frontmatter for authored daily notes.
- No routine-task prepopulation or task roundup.
- No bulk migration.
- No implicit `--apply`.
- No shell command strings or OS editor discovery.
- No `git mv` integration; filing remains atomic write plus source removal.
