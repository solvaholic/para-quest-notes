# pqn-quests

Generate the **Quest index** from the vault: walk every note, group each
under the Quest(s) it supports, and print the rollup. Read-only,
stateless, no LLM.

## What it does

Following `docs/notes-system.md` "Quest index":

- **Main / Side Quest notes** (`quest: main` / `quest: side` under
  `areas/`) define the sections and their order — Main Quests first
  (alphabetical), then Side Quests. Main Quest notes list themselves in
  `supports:`, so they appear in their own section.
- **Areas and Projects** declare the Quest(s) they serve in frontmatter
  via `supports:` (a list of wikilinks; a note may support more than
  one). Each is grouped under **every** Quest it supports.
- **Capabilities** (cross-cutting Areas with `capability: true`) get
  their own section rather than being duplicated under every Quest they
  touch.
- **Resources** are surfaced via **incoming wikilinks** from active
  (non-archived) Areas and Projects — not from their own frontmatter and
  not from daily notes. A Resource rolls up under the union of its
  linkers' Quests.
- **Unassigned** collects Areas/Projects with no `supports:` and
  Resources that roll up to no Quest, so they can be triaged.

The tool **does not create or own an index note.** It writes to stdout;
redirect the markdown into whatever note you like. That keeps it
stateless and sidesteps the "who overwrites the note" problem.

```bash
pqn-quests --vault ~/notes > index.md
```

## Scope

Always excluded:

- **`inbox/`** — pre-PARA staging owned by `pqn-ingest`; un-triaged
  notes don't belong in the Quest index. There is deliberately no
  `--include-inbox` toggle (unlike `--include-archive`): archived notes
  are fully-formed PARA notes that were merely relocated ("archive is a
  location, not a type"), so toggling them back in yields a coherent
  historical rollup. Inbox notes are the opposite — they usually lack
  `type:` and `supports:`, so they'd land in Unassigned as noise.
  Triage is `pqn-ingest`'s job; once a note is ingested it's placed and
  shows up here naturally.
- **`resources/daily_notes/`** — an activity log, not a reference
  Resource. (Daily-note wikilinks are usage *weight*, a separate axis
  `pqn-search` uses for ranking — not Quest *assignment*.)

`archive/` is excluded by default; pass `--include-archive` to include
it. Even then, archived notes are not "active", so an archived
Area/Project never rescues a Resource from Unassigned.

## Usage

```bash
# Whole vault, markdown (default) — redirect into a note.
pqn-quests --vault ~/notes > index.md

# Flat JSON for agents/tools.
pqn-quests --vault ~/notes --format json

# Only Areas and Projects (include-only, repeatable). Excluding 'area'
# also drops the Capabilities section, by design.
pqn-quests --vault ~/notes --type area --type project

# One Quest only (wikilink or bare name). Omits Capabilities/Unassigned.
pqn-quests --vault ~/notes --quest '[[Health]]'

# Include archived notes.
pqn-quests --vault ~/notes --include-archive
```

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)): `--vault` →
`PARA_QUEST_VAULT` → walk up from cwd → `vault:` in `config.yaml`.

Exit codes: `0` on success, `2` for an invocation problem (vault not
found).

## Flags

| Flag                | Meaning                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `--type`            | Include only this PARA type (`project` \| `area` \| `resource`). Repeatable, include-only.  |
| `--quest`           | Restrict to a single Quest; a note matches when its `supports:` includes it.                |
| `--include-archive` | Include notes under `archive/` (excluded by default).                                       |
| `--format`          | `text` (markdown, default) or `json`.                                                        |
| `--vault`           | Vault path (falls back to discovery).                                                        |
| `--config`          | Path to `config.yaml`.                                                                       |

## Markdown output

One `##` section per Quest (Main first, then Side), then `## Capabilities`
and `## Unassigned`. A note supporting two Quests appears under **both** —
intentional, and the reason JSON (not markdown) is the machine-readable
surface.

Each bullet carries a parenthetical hint: Main and Side Quest notes are
labeled by their **Quest kind** (`main quest` / `side quest`) so a Side
Quest serving this Quest is distinguishable from a plain supporting Area
at a glance; everything else shows its PARA type.

```markdown
# Quest index

## [[Health]]

- [[Health]] (main quest)
- [[Maintain Home]] (side quest)
- [[Run a 5K]] (project)
- [[Sourdough Notes]] (resource)

## [[Maintain Home]]

- [[Maintain Home]] (side quest)
- [[Workshop]] (area)

## Capabilities

- [[Be Organized]] (area)

## Unassigned

- [[Random Topic]] (area)
- [[Orphan Resource]] (resource)
```

## JSON contract

**Flat**: every note appears exactly once, carrying its own `supports`
list and the `quests` it rolls up under. Consumers group by `quests`
themselves.

```json
{
  "vault": "/path/to/vault",
  "scope": {"types": null, "quest": null, "include_archive": false},
  "summary": {"quests": 3, "notes": 12, "capabilities": 1, "unassigned": 2},
  "quests": [
    {"name": "Health", "quest_kind": "main"},
    {"name": "Maintain Home", "quest_kind": "side"}
  ],
  "notes": [
    {
      "path": "projects/Run a 5K.md",
      "title": "Run a 5K",
      "type": "project",
      "quest": "none",
      "supports": ["Health"],
      "quests": ["Health"],
      "capability": false,
      "unassigned": false,
      "archived": false
    }
  ]
}
```

Field names are stable across releases — agents and humans both consume
this. New fields may be added; existing fields will not be renamed.

## Use as a library

```python
from para_quest_notes.workflows.quests.api import (
    build_quest_index,
    render_markdown,
)

index = build_quest_index(vault, types=["area", "project"])
print(render_markdown(index))
```

## Notes on behavior

- **PARA type** is read from frontmatter `type:` (canonical), falling
  back to the note's top-level directory (`areas/`, `projects/`,
  `resources/`). A note in a free-form folder with no `type:` is
  skipped.
- **Resource assignment is link-only** (`docs/notes-system.md` settled
  decision). A Resource with its own `supports:` but no incoming
  Area/Project link is still Unassigned. This keeps two axes distinct:
  *assignment* (Quest membership, needs an active Area/Project link) vs.
  *weight* (any inbound link, used by `pqn-search`).

## Shared infrastructure

`pqn-quests` is the first link-aware CLI, so it lands two reusable
pieces in the `vault/` package:

- **`vault/links.py`** — wikilink parser + backlink index (lifted from
  `pqn-ingest`'s private link-scanning code).
- **`vault/scope.py`** — PARA-type detection and the `--type` / `--quest`
  filter.

Both are reused by `pqn-search`.

## Limitations / non-goals

- No `--depth` / level cap in v1 (deferred).
- No single-note focus mode ("given note X, show its Quests and
  neighbors") — that overlaps backlinks and `pqn-search`.
- Not a link-graph visualizer or orphan analyzer.
