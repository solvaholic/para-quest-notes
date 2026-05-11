# pqn-validate

Audit a vault for issues that quietly break wikilinks or note metadata.
Read-only. No LLM.

## What it does

Three checks, all derived from the legacy
[`validate-note-integrity`](https://github.com/solvaholic/at-home/blob/main/.agents/skills/validate-note-integrity/SKILL.md)
SKILL:

1. **`filename_uniqueness`** — flags any basename that appears in more
   than one directory. Wikilinks resolve by basename, so duplicates
   make `[[Notes]]` ambiguous. Case-insensitive (Obsidian's wikilink
   resolver and most personal-vault filesystems are too).
2. **`frontmatter_yaml`** — verifies the top `---...---` block parses
   as a YAML mapping. Reports the file:line of the first parse error.
3. **`backmatter_yaml`** — same, for the optional `---...---` fence at
   the *end* of a note (used by the archive workflow for Outcome
   statements). Absence is not an issue.

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

# Promote warnings to exit-code-1 (no built-in warnings today; safe to use).
pqn-validate --vault ~/notes --strict
```

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
  "checks_run": ["filename_uniqueness", "frontmatter_yaml", "backmatter_yaml"],
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

Inherited from the legacy SKILL — these are not bugs:

* No wikilink target validation (`[[Foo]]` pointing at a missing
  `Foo.md` is not flagged).
* No orphan or attachment-reference checks.
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
