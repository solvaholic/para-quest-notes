# pqn-create

Author a single new note into its PARA home, with canonical frontmatter
and a type-appropriate body skeleton. No LLM. One note per invocation.
No moves, no rewrites - just one new file.

## What it does

Seven steps, all pure (`--apply` only gates the actual disk write):

1. **`validate_inputs`** - checks `--type`, `--quest`, `--title`
   (Title Case, allowed character set, no camelCase/PascalCase),
   `--supports` wikilink format, `--sub-path` shape, and resource
   constraints (`--quest none` for resources). When `--quest main` and
   no `--supports` is given, infers `--supports "[[<title>]]"` (a main
   quest area supports itself). For other project/area notes without
   `--supports`, it records an inbox-fallback note in the plan instead
   of escalating.
2. **`resolve_quest`** - when `--supports` is omitted for a
   project/area, tries to resolve the Quest deterministically from the
   destination path (same-named Area note from the filename stem or
   sub-path segments, then sibling consensus). On a hit, fills in
   `supports` and routes to the canonical destination instead of inbox.
   On a miss, leaves inputs unchanged (inbox fallback). No LLM.
3. **`compute_destination`** - chooses either the canonical PARA path
   (`<vault>/<type>s/[sub_path/]<Title>.md`) or `inbox/<Title>.md` when
   a project or area note has no `--supports`.
4. **`check_collision`** - refuses to overwrite the planned path, then
   delegates to `validate.api.check_basename_available` so a duplicate
   basename anywhere in the vault is also caught. Wikilinks resolve by
   basename.
5. **`compose_note`** - emits canonical frontmatter via
   `vault.frontmatter.dump_frontmatter` (single source of truth) plus a
   type-appropriate body skeleton. Empty `supports` is dropped from
   frontmatter.
6. **`write_note`** - `--apply` only. Creates the parent directory if
   needed and writes atomically (sibling temp + `os.replace`). A
   defensive re-check guards the TOCTOU window between collision check
   and write.
7. **`validate_after`** - `--apply` only. Runs `validate.api.validate_paths`
   scoped to the new file. Whole-vault validation stays the user's call
   (run `pqn-validate` for that).

Frontmatter is the canonical metadata location (decided 2026-05-12; see
[`docs/PLAN.md`](../PLAN.md)). Backmatter is tolerated on read but never
written by `pqn-create`.

## Usage

```bash
# Plan a new project at its canonical destination.
pqn-create --vault ~/notes \
  --type project --title "Brew Setup" --supports "[[Coffee]]"

# Same thing using a positional path (infers --type, --title).
pqn-create --vault ~/notes --supports "[[Coffee]]" \
  "projects/Brew Setup.md"

# Infer everything from a full path (vault + type + sub-path + title).
pqn-create --supports "[[Coffee]]" \
  "~/notes/projects/2026/Brew Setup.md"

# Plan a new project when you do not know the Quest yet.
pqn-create --vault ~/notes \
  --type project --title "Brew Setup"

# Same, write it.
pqn-create --vault ~/notes \
  --type project --title "Brew Setup" --supports "[[Coffee]]" \
  --apply

# Resource note with sub-path and source URL.
pqn-create --vault ~/notes \
  --type resource --title "Pour Over Guide" \
  --quest none --sub-path coffee \
  --source-url https://example.com/guide --apply

# Area supporting multiple Quests, JSON output for an agent wrapper.
pqn-create --vault ~/notes --format json \
  --type area --title "Home" \
  --supports "[[Home]]" --supports "[[Family]]" --apply

# Create a new main quest (--supports inferred as "[[Coffee]]").
pqn-create --vault ~/notes \
  --type area --quest main --title "Coffee" --apply

# Pipe body content from stdin (replaces the default skeleton).
echo "# Meeting Notes\n\nDecided to use React." | \
  pqn-create --vault ~/notes --type project --title "Frontend Rewrite" \
  --supports "[[Work]]" --body-stdin --apply

# Pipe from a file.
cat draft.md | pqn-create --vault ~/notes \
  --type project --title "Research Summary" --body-stdin --apply

# Use a named body template (from <vault>/resources/templates/).
pqn-create --vault ~/notes --type project --title "Weekly Review" \
  --supports "[[Work]]" --template weekly-review --apply
```

### Body templates

`pqn-create` supports user-defined body templates stored in the vault.
See [`docs/templates.md`](../templates.md) for the full reference
(template location, variables, escaping, config defaults, fallback
behavior).

Quick version: `--template weekly-review` loads
`<vault>/resources/templates/weekly-review.md` and substitutes
`$title`, `$type`, `$created`, etc. Priority: stdin > template >
config default > built-in skeleton.

### Positional path inference

`pqn-create` accepts an optional positional path that infers `--type`,
`--title`, `--sub-path`, and optionally `--vault` from the path structure:

```
[<vault>/]<para-dir>/<sub-path?>/<filename>.md
```

where `<para-dir>` is `projects`, `areas`, or `resources` (singular forms
also accepted). Examples:

- `projects/My Note.md` -> `--type project --title "My Note"`
- `areas/home/Garden.md` -> `--type area --sub-path home --title "Garden"`
- `~/notes/resources/python/Decorators.md` -> `--vault ~/notes --type resource --sub-path python --title "Decorators"`

**Explicit flags always override inferred values.** If you pass both
`--type area` and a path like `projects/Foo.md`, the explicit `--type area`
wins.

`--supports` is optional. When `--quest main` is given without
`--supports`, `pqn-create` infers `--supports "[[<title>]]"` and files
to the canonical `areas/` path (a main quest area supports itself).
For other projects or areas without `--supports`, `pqn-create` files the
note into `inbox/` so the user can flesh out the body and let
`pqn-ingest` resolve the Quest later.

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)).

Exit codes:

* `0` - planned (dry-run) or wrote (apply) the note successfully.
* `1` - escalation (rules didn't fit) or runtime error.
* `2` - invocation problem (vault not found, etc.).

## JSON contract

Canonical destination example:

```json
{
  "vault": "/Users/me/notes",
  "apply": true,
  "ok": true,
  "plan": {
    "filename": "Brew Setup.md",
    "destination": "projects/Brew Setup.md",
    "destination_mode": "canonical",
    "frontmatter": {
      "type": "project",
      "quest": "none",
      "supports": ["[[Coffee]]"],
      "created": "2026-05-12"
    },
    "notes": []
  },
  "written": true,
  "escalation": null,
  "error": null,
  "run_id": "a1b2c3d4e5f6"
}
```

### Inbox fallback

When `--supports` is omitted for a `project` or `area` that is *not*
`--quest main`, the plan reports that choice explicitly:

```json
{
  "vault": "/Users/me/notes",
  "apply": false,
  "ok": true,
  "plan": {
    "filename": "Test Thing.md",
    "destination": "inbox/Test Thing.md",
    "destination_mode": "inbox",
    "frontmatter": {
      "type": "project",
      "quest": "none",
      "created": "2026-05-12"
    },
    "notes": [
      "filed to inbox because no --supports was provided for type=project"
    ]
  },
  "written": false,
  "escalation": null,
  "error": null,
  "run_id": "a1b2c3d4e5f6"
}
```

`pqn-ingest` honors a pre-set `type:` frontmatter value on inbox notes,
so the note keeps the PARA intent chosen at create time. See
[`docs/workflows/ingest.md`](./ingest.md).

On escalation, `ok` is `false`, `written` is `false`, and `escalation`
contains the structured payload:

```json
{
  "step": "check_collision",
  "reason": "filename collides with existing note(s)",
  "options": [{"existing": "areas/Twin.md"}],
  "context": {
    "validate_message": "...",
    "filename": "Twin.md"
  }
}
```

## Known limitations

* **Deterministic-only Quest resolution.** When `--supports` is omitted,
  `pqn-create` resolves the Quest deterministically from the destination
  path (area note match from sub-path or filename). There is no LLM
  fallback yet - if the deterministic branch misses, the note goes to
  `inbox/`. An LLM branch (using `pick_quest`'s prompt) is planned once
  stdin body support (#46) provides the signal it needs.
* **Inbox fallback ignores `--sub-path`.** An unknown-Quest note is filed
  directly under `inbox/` so `pqn-ingest` sees it.
* **No Daily-note or Capability-index authoring.** Both are out of
  scope. Daily notes are slice 4 (`pqn-daily`); Capability index notes
  are an open question in
  [`docs/notes-system.md`](../notes-system.md).
