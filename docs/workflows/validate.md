# pqn-validate

Audit a vault for issues that quietly break wikilinks or note metadata.
Read-only by default; `--fix` is the one opt-in write path. No LLM.

## What it does

Five checks:

1. **`filename_uniqueness`** — flags any basename that appears in more
   than one directory. Wikilinks resolve by basename, so duplicates
   make `[[Notes]]` ambiguous. Case-insensitive (Obsidian's wikilink
   resolver and most personal-vault filesystems are too).
2. **`frontmatter_yaml`** — verifies the top `---...---` block parses
   as a YAML mapping. Reports the file:line of the first parse error.
3. **`backmatter_yaml`** — same, for the optional `---...---` fence at
   the *end* of a note (used by the archive workflow for Outcome
   statements). Absence is not an issue.
4. **`metadata_in_backmatter`** *(warning)* — flags canonical PARA +
   Quest keys (`type`, `quest-kind`, `supports`, `source_url`,
   `created`, and the legacy `quest`) that appear in tail backmatter.
   Frontmatter is canonical; write-path workflows migrate backmatter on
   touch, but tools that only read frontmatter (Obsidian Properties,
   Dataview, SSGs — and historically `pqn-ingest`'s Quest discovery)
   miss it until then.
5. **`legacy_quest_key`** *(warning)* — flags a legacy `quest:`
   classifier key in *frontmatter* (the field was renamed to
   `quest-kind:` in #98). Tolerated on read, but tools reading only the
   canonical key miss it. Fixable in bulk with [`--fix`](#fix-migrate-legacy-quest-keys).

By design this workflow does **not** validate wikilink targets, orphan
detection, PARA placement, or semantic frontmatter content. Those are
out of scope until a concrete need surfaces.

`templates/` and `Templates/` directories skip the YAML checks
(template placeholders like `{{title}}` aren't valid YAML). They still
count toward filename uniqueness.

`archive/` is excluded from every check by default. Pass
`--include-archive` when you really mean it.

## Usage

```bash
# Scan the whole vault, human-readable output.
pqn-validate --vault ~/notes

# JSON output for piping or agent wrappers.
pqn-validate --vault ~/notes --format json

# Limit reporting to one path (vault-wide context still applies).
pqn-validate --vault ~/notes --path projects/Run a 5K.md

# Run a single check.
pqn-validate --vault ~/notes --check filename_uniqueness

# Promote warnings to exit-code-1 (e.g. the metadata_in_backmatter check).
pqn-validate --vault ~/notes --strict
```

## Fix: migrate legacy `quest:` keys

`--fix` is the one write path in an otherwise read-only workflow, and it
does exactly one thing: rename legacy `quest:` frontmatter keys to
canonical `quest-kind:` (the #98 rename). It's the batch counterpart to
the migrate-on-touch that write-path workflows already do — for static
notes (Resources, Areas) the tools never happen to write to.

```bash
# Preview what would change (dry-run — writes nothing).
pqn-validate --vault ~/notes --fix

# Actually rewrite the notes.
pqn-validate --vault ~/notes --fix --apply

# Scope the fix to one path.
pqn-validate --vault ~/notes --fix --apply --path resources/Sourdough.md
```

Rules:

* Migrates a note only when the legacy value is a valid kind
  (`main` / `side` / `none`), or when a canonical `quest-kind:` already
  exists (the redundant legacy key is then dropped). Any other value is
  **reported and skipped** — `--fix` never guesses.
* The rename preserves surrounding frontmatter (key order, other values)
  and the note body and any tail backmatter.
* **Idempotent** — a second run is a no-op once notes are migrated.
* Dry-run by default; `--apply` writes. This is the same convention as
  `pqn-ingest`, `pqn-create`, `pqn-archive`, and `pqn-daily`.
* Exit code is `1` when any note was skipped (an unresolved legacy value
  a human must sort out), `0` otherwise.

`--fix` only migrates `quest:`. It does **not** rename files, repair
malformed YAML, or promote backmatter — those need judgment or an
unbuilt capability (see [Limitations](#limitations)), so they stay
report-only.

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)): `--vault` →
`PARA_QUEST_VAULT` → walk up from cwd → `vault:` in `config.yaml`.

Exit codes:

* `0` — no issues at the requested severity.
* `1` — at least one error (or warning, with `--strict`).
* `2` — invocation problem (vault not found, etc.).

## JSON contract

```json
{
  "vault": "/path/to/vault",
  "files_scanned": 142,
  "checks_run": ["filename_uniqueness", "frontmatter_yaml", "backmatter_yaml", "metadata_in_backmatter", "legacy_quest_key"],
  "summary": {
    "total_issues": 2,
    "errors": 2,
    "warnings": 0
  },
  "issues": [
    {
      "check": "filename_uniqueness",
      "severity": "error",
      "path": "areas/Notes.md",
      "message": "filename 'Notes.md' is not unique in the vault (2 occurrences); wikilinks to it will be ambiguous",
      "line": null,
      "related": ["projects/Notes.md"],
      "detail": {"basename": "Notes.md", "count": 2}
    },
    {
      "check": "frontmatter_yaml",
      "severity": "error",
      "path": "areas/Bad.md",
      "message": "invalid YAML in frontmatter: while scanning a simple key ...",
      "line": 3,
      "related": [],
      "detail": {}
    }
  ]
}
```

Field names are stable across releases — agents (Phase 7) and humans
both consume this. New fields may be added; existing fields will not be
renamed.

## Use as a library

Other workflows compose validation by calling the Python API directly,
not by shelling out to the CLI. ``pqn-ingest`` does this from its
``propose_filename`` step:

```python
from para_quest_notes.workflows.validate.api import (
    check_basename_available,
    validate_paths,
    validate_vault,
)

# "Would this proposed filename collide with an existing note?"
issues = check_basename_available(vault, "Run a 5K.md", ignore_path=src)

# Or run the full check suite, scoped to one or more paths.
report = validate_paths(vault, [vault / "projects" / "Run a 5K.md"])

# Or against the whole vault.
report = validate_vault(vault)
```

## Limitations

Out of scope by design — these are not bugs:

* No wikilink target validation (`[[Foo]]` pointing at a missing
  `Foo.md` is not flagged). Will become useful once a workflow
  renames notes.
* No PARA placement check (frontmatter `type:` vs containing
  directory). Tracked as a follow-up — it's a no-LLM check that
  should land here.
* No orphan or attachment-reference checks. Same trigger as
  wikilinks: needed once a workflow moves attachments.
* No inline tag syntax validation.
* YAML is checked syntactically, not semantically — any well-formed
  YAML passes, even if the keys make no sense for your vault.

## Gotchas

* **A `---` line inside the body** (used as a horizontal rule) is fine
  unless it happens to land as the file's last non-blank line — then
  the backmatter scan will look for a matching opener above it. If you
  see a backmatter YAML error pointing at body content, suspect a
  stray rule.
* **The basename index is case-insensitive.** `Notes.md` and `notes.md`
  collide, even on case-sensitive filesystems, because Obsidian's
  wikilink resolver doesn't care about case.
