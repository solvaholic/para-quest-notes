# pqn-search

Keyword search over the vault, **PARA + Quest-aware**. Match notes by
title and/or body, scope by note type and Quest, and rank hits by the
model. Read-only, stateless, no LLM.

## Why not just `rg`?

Plain `rg` already does substring matching over `.md` files, so
`pqn-search` earns its place by knowing the model and meeting you where
you work:

- It filters by **note type** (`--type`) and **Quest** (`--quest`).
- It ranks **Resources by incoming-link count** - an inbound wikilink is
  re-use, and re-use is evidence of value. `docs/notes-system.md` treats
  incoming links as how Resources are discovered, so a Resource many
  active notes point at is more likely what you're after.
- It **finds your notes without making you think about where the vault
  is or how it's organized** - vault discovery is built in, and it runs
  the same way in every shell.

If you want raw substring matching with no ranking or scope, `rg` wins.
Reach for `pqn-search` when the PARA + Quest structure should shape the
results.

## What it does

- Matches on **title** (the note basename) and/or **body content**,
  case-insensitively.
- Multiple keywords are combined with **AND**: a note is a result only
  when every keyword appears in the searched fields. (Use `| head` or
  `--limit` to cap; pipe to `rg` for regex.)
- Filters the matches by `--type` (repeatable, include-only) and
  `--quest` (notes whose `supports:` includes that Quest).
- Ranks the survivors and prints a **flat list**, most-relevant first,
  as text (default) or JSON.

```bash
pqn-search --vault ~/notes sourdough
```

## Ranking (v1)

Results are sorted by, in order:

1. **Title hits before body hits.** A keyword in the basename beats one
   in the body.
2. **For Resources, tie-break by incoming-link count (descending).** The
   count is the number of **active** (non-`archive/`) notes that link to
   the Resource, *including* daily notes - daily-note links are signal.
   `archive/` links never count. Non-Resources don't get a link-count
   boost.
3. **Stable tie-break by vault-relative path.**

No term-frequency weighting in v1 - the goal is predictability. The
backlink count is what earns this over plain `rg`; it isn't just
substring matching.

## Scope

- **`inbox/` and daily notes are searched by default** - that's where
  recent, findable notes live, so they need no include flag.
- **`archive/` is excluded by default**; pass `--include-archive` to
  search it too. Even then, archived notes never confer inbound-link
  weight on a Resource (the ranking index is always built from the
  active set).
- Standard exclusions (`.git/`, `.obsidian/`, `.trash/`,
  `node_modules/`) are always skipped.

## Content matching and code blocks

`--content` matches **raw body text, including fenced code blocks**.
Search is lexical: missing `pqn-search docker` because the only mention
sits in a fenced command block would be worse than the occasional
example-code false positive. (Task parsing strips fences for *semantic*
reasons - a `- [ ]` inside a fence isn't a real task - but that
reasoning doesn't transfer to keyword search.)

## Usage

```bash
# Title and body (default), whole active vault.
pqn-search --vault ~/notes sourdough

# Title only, or body only.
pqn-search --vault ~/notes --title 5k
pqn-search --vault ~/notes --content docker

# Multiple keywords (AND) - both must appear.
pqn-search --vault ~/notes water heater

# Scope to a PARA type (repeatable, include-only) and/or a Quest.
pqn-search --vault ~/notes --type resource shoes
pqn-search --vault ~/notes --quest '[[Health]]' plan

# Cap results; search archived notes too.
pqn-search --vault ~/notes --limit 10 notes
pqn-search --vault ~/notes --include-archive manual

# Widen the snippet, or turn snippets off entirely.
pqn-search --vault ~/notes --snippet-radius 80 docker
pqn-search --vault ~/notes --snippet-radius 0 docker

# Flat JSON for agents/tools.
pqn-search --vault ~/notes --format json sourdough | jq
```

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)): `--vault` →
`PARA_QUEST_VAULT` → walk up from cwd → `vault:` in `config.yaml`.

Exit codes: `0` on success (including zero matches - an empty result set
isn't an error), `2` for an invocation problem (vault not found).

## Flags

| Flag                | Meaning                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `query`             | One or more keywords (positional). AND across keywords, case-insensitive.                    |
| `--title`           | Match the note title (basename). Default: title and content.                                |
| `--content`         | Match the note body, including code blocks. Default: title and content.                     |
| `--type`            | Include only this PARA type (`project` \| `area` \| `resource`). Repeatable, include-only.  |
| `--quest`           | Restrict to notes whose `supports:` includes this Quest (wikilink or bare name).            |
| `--limit`           | Cap the number of results. Default: unlimited.                                              |
| `--snippet-radius`  | Characters of context per side of a body match (also gates the title snippet). `0` = no snippet. Default: 40. |
| `--include-archive` | Include notes under `archive/` (excluded by default).                                       |
| `--format`          | `text` (default) or `json`.                                                                  |
| `--vault`           | Vault path (falls back to discovery).                                                        |
| `--config`          | Path to `config.yaml`.                                                                       |

Passing both `--title` and `--content` is the same as passing neither:
both fields are searched.

## Configuration

The snippet width has a per-workflow config default under `search:` in
`config.yaml`, resolved as **`--snippet-radius` flag > config > built-in
default (40)**:

```yaml
workflows:
  search:
    snippet_radius: 60   # wider context; 0 to suppress snippets
```

A negative or non-integer value is a loud error (exit 2). Everything
else about a run - which vault, which config - is reported by
`pqn-config`.

## Text output

A flat list, most-relevant first. One bullet per result: the
vault-relative path, the PARA type (with the inbound-link count for
Resources, since that count drives their ranking), any declared
`supports:`, and where the hit landed plus a snippet.

```text
# Search results for "running" (3 matches)

- resources/Running Shoes.md (resource, 2 links) - title: "Running Shoes"
- projects/Run a 5K.md (project, supports: Health) - body: "...a running plan for..."
- resources/daily_notes/2026/02/2026-02-05.md (resource) - body: "...went running today..."
```

## JSON contract

A **flat list** under `results`, most-relevant first. Each result:

- `path` - vault-relative POSIX path.
- `type` - `project` | `area` | `resource` | `null`.
- `supports` - the note's declared `supports:` list (the Quest(s) it
  serves). A **list**, and deliberately not the same axis as
  `quest-kind`: `quest-kind:` is the main/side/none classifier,
  `supports:` is which Quest(s) the note serves.
- `match_context` - `{where, snippet}`. `where` is `"title"` or
  `"body"`; `snippet` is the title (title hit) or a whitespace-collapsed
  window around the first body match. The window width is set by
  `--snippet-radius` (`0` yields an empty `snippet`).
- `incoming_links` - inbound-link count (the Resource ranking signal;
  `0` for non-Resources), surfaced for transparency.

```json
{
  "vault": "/path/to/vault",
  "query": ["running"],
  "scope": {
    "title": true,
    "content": true,
    "types": null,
    "quest": null,
    "include_archive": false,
    "limit": null,
    "snippet_radius": 40
  },
  "summary": {"results": 3},
  "results": [
    {
      "path": "resources/Running Shoes.md",
      "type": "resource",
      "supports": [],
      "match_context": {"where": "title", "snippet": "Running Shoes"},
      "incoming_links": 2
    }
  ]
}
```

Field names are stable across releases - agents and humans both consume
this. New fields may be added; existing fields will not be renamed.

## Use as a library

```python
from para_quest_notes.workflows.search.api import render_text, search

results = search(vault, ["running"], types=["resource"])
print(render_text(results))
```

## Shared infrastructure

`pqn-search` is the sibling of `pqn-quests`; both consume the two
link-aware building blocks in the `vault/` package:

- **`vault/links.py`** - wikilink parser + backlink index (used for the
  Resource ranking).
- **`vault/scope.py`** - PARA-type detection and the `--type` / `--quest`
  filter.

## Scope / non-goals

- **Keyword/lexical only.** "Find similar notes" (semantic similarity)
  is out of scope - it needs either a cloud LLM (violates local-first)
  or a local vector index, and "Vector indexing of the vault" is listed
  under Out of scope in [`docs/PLAN.md`](../PLAN.md). A lexical
  similarity proxy (shared wikilinks + shared salient terms) would be a
  separate, later issue.
- **No graph rendering / pattern analysis.** Visualizing the wikilink
  graph or surfacing "surprising" relationships is a different concern
  (and overlaps
  [markdown-loom](https://github.com/solvaholic/markdown-loom));
  `pqn-search` is the headless, Quest-scoped complement.
- **No regex or term-frequency ranking in v1.** Keep it predictable,
  then iterate against real examples.
