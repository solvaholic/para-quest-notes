# pqn-ingest

Triage notes from `<vault>/inbox/` into PARA + Quest locations.

## What it does

For each `.md` file under `<vault>/inbox/`, the workflow runs six
steps in order:

1. **scan_note** (pure) — read frontmatter + body, detect sibling
   attachments.
2. **classify_para** (LLM) — pick one of `project | area | resource`.
3. **pick_quest** (LLM) — pick one or more Quests from the vault's
   declared Main + Side Quests. Skipped for resources.
4. **propose_filename** (LLM, may skip) — if the source basename
   already passes a structural check (Title Case or identifier-style),
   keep it and skip the LLM; otherwise ask the LLM to pick from {keep,
   repair, generate}. Validated locally for collisions outside
   `archive/`.
5. **plan_destination** (pure) — flat layout under the PARA top-dir
   (`projects/`, `areas/`, `resources/`).
6. **apply_move** (pure, atomic) — dry-run by default. With `--apply`,
   moves the file + sibling attachments, merges spec frontmatter
   (`type`, `quest`, `supports`), and rewrites incoming wikilinks
   across the vault excluding `archive/`.

When a step decides the rules don't fit, it raises `EscalateToUser`
and the workflow stops with a structured payload. The CLI surfaces
that payload — that's the contract agents (Phase 7) and humans both
consume.

## Usage

```bash
# Dry run (default). Shows what would change, touches nothing.
pqn-ingest --vault ~/notes

# JSON output for piping or agent wrappers.
pqn-ingest --vault ~/notes --format json

# Process one file.
pqn-ingest --vault ~/notes --file inbox/quick-note.md

# Apply changes (moves, renames, frontmatter, wikilink rewrites).
pqn-ingest --vault ~/notes --apply

# Keep original filenames (skip renaming).
pqn-ingest --vault ~/notes --skip-rename --apply

# Override the default model from config.yaml.
pqn-ingest --vault ~/notes --model qwen3:30b
```

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)): `--vault` →
`PARA_QUEST_VAULT` → walk up from cwd → `vault:` in `config.yaml`.

Exit code is `0` if every file ran clean, `1` if any file escalated
or errored, `2` if no vault could be resolved.

## JSON contract

Top level:

```json
{
  "vault": "/path/to/vault",
  "run_id": "abcd1234efgh",
  "apply": false,
  "files": [ /* FileResult */ ]
}
```

Each `FileResult`:

```json
{
  "source": "inbox/train plan.md",
  "ok": true,
  "decisions": {
    "para_type": "project",
    "quests": ["Health"],
    "filename": "Run A 5K.md",
    "destination": "projects/Run A 5K.md"
  },
  "applied": false,
  "change": {
    "moved_from": "inbox/train plan.md",
    "moved_to": "projects/Run A 5K.md",
    "attachments_moved": [],
    "wikilinks_rewritten": [
      {"file": "areas/Health.md", "occurrences": 1}
    ],
    "frontmatter_updated": false
  },
  "escalation": null,
  "error": null,
  "run_id": "abcd1234efgh"
}
```

`change` is populated for both dry-run and apply modes — in dry-run
it describes what *would* happen, in apply mode it describes what
did. `applied` distinguishes the two.

When a step escalates, `ok` is `false`, `change` is `null`, and
`escalation` carries:

```json
{
  "step": "pick_quest",
  "reason": "no defensible Quest match",
  "options": [{"quest": "Health"}, {"quest": "Connect"}],
  "context": {"reason": "model couldn't decide"}
}
```

`options` is a list of structured choices the workflow could offer a
caller; `context` carries free-form state useful for triage.

## Behavior notes

- **Dry run by default.** `--apply` is required to touch disk.
- **`--skip-rename`** keeps the original inbox filename unchanged. The
  file is still classified, Quest-picked, and moved to its PARA
  destination directory - just without renaming. The collision check
  still runs against the destination. Useful when filenames carry
  special meaning (e.g., `sklearn.linear_model.SGDClassifier.md`) or
  must match references in other documents.
- **Wikilink rewriting** updates `[[old]]`, `[[old|alias]]`, and
  `[[old#anchor|alias]]` to the new title. Aliases and anchors are
  preserved.
- **Archive is left alone.** Files under `<vault>/archive/` are not
  rewritten — old links point at the historical name on purpose.
- **Resources skip the Quest step.** Per
  [`docs/notes-system.md`](../notes-system.md), `supports:` is
  optional on resources.
- **Pre-set `type:` frontmatter is authoritative.** If an inbox note
  already has `type: project`, `type: area`, or `type: resource`,
  `classify_para` is skipped and the existing value is used.
- **Filename auto-skip.** If the inbox source basename already passes
  the structural check — either Title Case (spaces between words, each
  starting uppercase/digit) or identifier-style (dot/hyphen/underscore-
  joined segments with no spaces, e.g.
  `sklearn.linear_model.SGDClassifier`, `CVE-2021-44228`),
  `propose_filename` keeps the source name and does not call the LLM.
  This preserves user-curated specifics (dates, brand names like
  `DeepWiki`, qualified identifiers) that an LLM rewrite often loses.
  The collision check still runs.
- **Filename validation** rejects path separators and disallowed
  characters; appends `.md` if missing. Enforces a structural rule: the
  stem must be **Title Case** (every whitespace-separated word starts
  with an uppercase letter or digit — no lowercase joiners like `a`,
  `of`, `to`; brand names with interior caps like `DeepWiki`, `GitHub`,
  `iPhone` are fine) **or identifier-style** (dot/hyphen/underscore-
  joined segments with no spaces, for qualified identifiers and IDs).
- **Bounded-choice rename.** When the structural check fails, the LLM
  is asked to pick one of `keep` (use source as-is), `repair` (use a
  mechanically capitalized variant), or `generate` (compose a new
  name). The chosen filename must still pass the structural check.
- **Collisions** outside `archive/` escalate from `propose_filename`
  with the colliding path in `options`.
- **Atomic move.** Uses `Path.replace`; safe within a single
  filesystem.
- **Trace.** Every run writes a JSONL trace under
  `$XDG_STATE_HOME/para-quest-notes/runs/` (or the configured
  `run_log_dir`). The CLI prints the trace path on text output.

## Known limitations (v1)

- Wikilinks inside `archive/` are not rewritten. (Whether that's the
  right call long-term is an open question — see `docs/PLAN.md`.)
- **Wikilink rewrite matches by basename, not path.** If a renamed
  inbox file shares its stem with an unrelated note elsewhere in the
  vault, links to the unrelated note will also be rewritten. Obsidian's
  "shortest-path-when-unique" resolution makes the boundary fuzzy.
  Mitigation today: keep basenames unique vault-wide (`pqn-validate`'s
  `filename_uniqueness` check enforces this).
- **Batch processing is per-file atomic, not batch atomic.** Each
  inbox file is moved + has its incoming wikilinks rewritten as a
  unit. If a multi-file run is interrupted (Ctrl-C, error), the files
  already processed are fully consistent, and the unprocessed files
  still sit in `inbox/` with their original names. Inbox→inbox links
  survive renames because the rewrite scope includes `inbox/`.
- Destination layout is flat under the PARA top-dir; mirroring an
  existing sub-structure is a planned enhancement.
- On escalation, the workflow stops the file. There's no resume — fix
  the underlying ambiguity (config, frontmatter, vault Quest list) and
  re-run.
- The Quest catalog is read at the start of each `ingest_inbox` run;
  modifying `areas/*.md` mid-run won't be reflected until the next
  invocation.
