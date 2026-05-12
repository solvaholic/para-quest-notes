# pqn-create

Author a single new note into its PARA + Quest home, with canonical
frontmatter and a type-appropriate body skeleton. No LLM. One note per
invocation. No moves, no rewrites — just one new file.

## What it does

Six steps, all pure (`--apply` only gates the actual disk write):

1. **`validate_inputs`** — checks `--type`, `--quest`, `--title`
   (Title Case, allowed character set, no camelCase/PascalCase),
   `--supports` wikilink format, `--sub-path` shape, and Rule 1
   (Project/Area must declare ≥1 `--supports`; Resource must be
   `--quest none`). Escalates if anything is off.
2. **`compute_destination`** — maps to
   `<vault>/<type>s/[sub_path/]<Title>.md`. The vault root contains
   `projects/`, `areas/`, `resources/` as siblings (per
   [`docs/notes-system.md`](../notes-system.md)).
3. **`check_collision`** — refuses to overwrite the planned path,
   then delegates to `validate.api.check_basename_available` so a
   duplicate basename anywhere in the vault is also caught.
   Wikilinks resolve by basename.
4. **`compose_note`** — emits canonical frontmatter via
   `vault.frontmatter.dump_frontmatter` (single source of truth)
   plus a type-appropriate body skeleton. Empty `supports` is dropped
   from frontmatter.
5. **`write_note`** — `--apply` only. Creates the parent directory if
   needed and writes atomically (sibling temp + `os.replace`). A
   defensive re-check guards the TOCTOU window between collision
   check and write.
6. **`validate_after`** — `--apply` only. Runs `validate.api.validate_paths`
   scoped to the new file. Whole-vault validation stays the user's
   call (run `pqn-validate` for that).

Frontmatter is the canonical metadata location (decided 2026-05-12;
see [`docs/PLAN.md`](../PLAN.md)). Backmatter is tolerated on read
but never written by `pqn-create`.

## Usage

```bash
# Plan a new project (dry-run).
pqn-create --vault ~/notes \
  --type project --title "Brew Setup" --supports "[[Coffee]]"

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
```

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)).

Exit codes:

* `0` — planned (dry-run) or wrote (apply) the note successfully.
* `1` — escalation (rules didn't fit) or runtime error.
* `2` — invocation problem (vault not found, etc.).

## JSON contract

```json
{
  "vault": "/Users/me/notes",
  "apply": true,
  "ok": true,
  "plan": {
    "filename": "Brew Setup.md",
    "destination": "projects/Brew Setup.md",
    "frontmatter": {
      "type": "project",
      "quest": "none",
      "supports": ["[[Coffee]]"],
      "created": "2026-05-12"
    }
  },
  "written": true,
  "escalation": null,
  "error": null,
  "run_id": "a1b2c3d4e5f6"
}
```

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

## Known limitations (v0.1)

* **Areas without tasks must still pass `--supports`.** Rule 1 is
  enforced strictly. A future `--no-tasks` flag could relax this for
  taskless Areas (e.g. a "Home / Outside / Garden" reference area).
* **No quest-resolution help.** If you don't know which Quest a note
  supports, `pqn-create` won't guess for you. A future LLM-backed
  `resolve_quest` step could mirror `pqn-ingest`'s prompt; deferred
  until a second workflow needs the same shared prompt.
* **No Daily-note or Capability-index authoring.** Both are out of
  scope. Daily notes are slice 4 (`pqn-daily`); Capability index notes
  are an open question in
  [`docs/notes-system.md`](../notes-system.md).
