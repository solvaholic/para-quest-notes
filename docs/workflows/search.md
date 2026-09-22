# pqn-search

Keyword search and direct one-hop link traversal over the vault, **PARA + Quest-aware**. Match notes by title and/or body, or resolve one target and inspect its outgoing links and incoming backlinks. Scope results by note type and Quest. Read-only, stateless, no LLM.

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
- It answers the direct graph question **"what does this note link to, and what links back to it?"** without requiring likely keywords first.

If you want raw substring matching with no ranking or scope, `rg` wins.
Reach for `pqn-search` when the PARA + Quest structure should shape the
results.

## Modes

Exactly one mode is required:

- **Keyword mode:** pass one or more positional keywords.
- **Link mode:** pass `--links TARGET`.

The modes are mutually exclusive. `--title`, `--content`, and `--snippet-radius` belong only to keyword mode and fail clearly with `--links`. Shared filters (`--type`, `--quest`, `--limit`, `--include-archive`) apply to both modes.

## Keyword mode

- Matches on **title** (the note basename) and/or **body content**,
  case-insensitively.
- Multiple keywords are combined with **AND**: a note is a result only
  when every keyword appears in the searched fields. (Use `| head` or
  `--limit` to cap; pipe to `rg` for regex.)
- Each result reports one ordered evidence item for every distinct query keyword. Keyword identity is case-insensitive, so repeated spellings collapse to the first supplied spelling and query position. An item reports the keyword, whether its preferred match is in the title or body, and a snippet. When the keyword occurs in both enabled fields, title evidence wins.
- Filters the matches by `--type` (repeatable, include-only) and
  `--quest` (notes whose `supports:` includes that Quest).
- Ranks the survivors and prints a **flat list**, most-relevant first,
  as text (default) or JSON.

```bash
pqn-search --vault ~/notes sourdough
```

## Link mode

`--links TARGET` resolves one note and returns its direct, one-hop neighbors:

- **outgoing** - the target links to the neighbor;
- **incoming** - the neighbor links to the target;
- **mutual** - both directions exist.

Each neighbor appears once. Directional occurrence counts include repeated links, while self-links are excluded from results. Anchors and aliases do not change identity, so `[[Foo]]`, `[[Foo#Heading]]`, and `[[Foo|Alias]]` resolve alike. A path-qualified wikilink such as `[[folder/Foo]]` resolves that exact note and can disambiguate duplicate basenames. Embedded wikilinks such as `![[Foo]]` count because they use the same canonical parser.

```bash
# Resolve a unique basename, with or without .md.
pqn-search --vault ~/notes --links "Running Shoes"

# Use a vault-relative path to disambiguate duplicate basenames.
pqn-search --vault ~/notes --links "resources/Running Shoes.md"

# Filters apply to neighboring notes, not to the target.
pqn-search --vault ~/notes --links "Running Shoes" \
    --type project --quest '[[Health]]' --limit 10
```

### Target resolution

The target is resolved against the same Markdown-file universe searched by the mode:

1. A vault-relative path selects that exact `.md` file.
2. Otherwise the target matches a note basename case-insensitively, with or without `.md`.
3. A missing target is an actionable error.
4. An ambiguous basename is an actionable error listing candidate paths; pass one of those paths.
5. Absolute paths, vault escapes, excluded directories, and archived notes without `--include-archive` do not resolve.

Shell completion follows the same contract: unique names complete as bare stems, while duplicate names complete as vault-relative paths.

### Unresolved outgoing links

The requested target must resolve uniquely, but links inside it may be broken or ambiguous. Link mode reports those separately without failing the lookup. Each unresolved item includes the normalized target, occurrence count, `missing` or `ambiguous` reason, and candidate paths for ambiguity. A link to an archived note is unresolved unless `--include-archive` places that note in the selected file universe.

### Link ranking

Link neighbors are sorted by:

1. mutual relation;
2. outgoing relation;
3. incoming relation;
4. total outgoing plus incoming occurrences, descending;
5. vault-relative path.

Resource backlink popularity does not affect link-mode ranking. The requested note's direct relationship is the signal.

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
- **`archive/` is excluded by default**; pass `--include-archive` to search it too. In link mode this applies to both target resolution and neighboring notes. In keyword mode archived notes never confer inbound-link weight on a Resource because the ranking index is always built from the active set.
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

# Direct outgoing links and backlinks.
pqn-search --vault ~/notes --links "Running Shoes"
pqn-search --vault ~/notes --links "resources/Running Shoes.md" --format json | jq
```

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)): `--vault` →
`PARA_QUEST_VAULT` → walk up from cwd → `vault:` in `config.yaml`.

Exit codes: `0` on success (including zero matches - an empty result set
isn't an error), `2` for an invocation problem (vault not found).

## Flags

| Flag                | Meaning                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `query`             | One or more keywords (positional). AND across keywords, case-insensitive. Mutually exclusive with `--links`. |
| `--links`           | Resolve one target and report direct outgoing links and incoming backlinks. Mutually exclusive with positional keywords. |
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

Passing `--title`, `--content`, or `--snippet-radius` with `--links` is an invocation error rather than a silently ignored option.

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

## Keyword text output

A flat list, most-relevant first. One bullet per result: the
vault-relative path, the PARA type (with the inbound-link count for
Resources, since that count drives their ranking), any declared
`supports:`, and where the hit landed plus a snippet.

Single-keyword output retains the original `title`/`body` tail. For multiple distinct keywords, the tail names each keyword and its preferred evidence location:

```text
# Search results for "running" (3 matches)

- resources/Running Shoes.md (resource, 2 links) - title: "Running Shoes"
- projects/Run a 5K.md (project, supports: Health) - body: "...a running plan for..."
- resources/daily_notes/2026/02/2026-02-05.md (resource) - body: "...went running today..."

# Search results for "running plan" (1 match)

- projects/Run a 5K.md (project, supports: Health) - matches: running (body): "...a running plan..."; plan (body): "...a running plan..."
```

## Keyword JSON contract

A **flat list** under `results`, most-relevant first. Each result:

- `path` - vault-relative POSIX path.
- `type` - `project` | `area` | `resource` | `null`.
- `supports` - the note's declared `supports:` list (the Quest(s) it
  serves). A **list**, and deliberately not the same axis as
  `quest-kind`: `quest-kind:` is the main/side/none classifier,
  `supports:` is which Quest(s) the note serves.
- `match_context` - `{where, snippet}`. `where` is `"title"` or `"body"`; `snippet` is the title (title hit) or a whitespace-collapsed window around the earliest body match. This compatibility field prefers `"title"` when any keyword has title evidence, otherwise `"body"`. The window width is set by `--snippet-radius` (`0` yields an empty `snippet`).
- `matches` - ordered per-keyword evidence items: `{keyword, where, snippet}`. There is at most one item for each distinct case-insensitive query keyword; repeated query spellings use the first supplied spelling and position. `where` is `"title"` when that keyword matches both enabled fields, otherwise `"body"`. Body snippets are separate whitespace-collapsed windows around the keyword's first body occurrence; snippets are empty, but locations and keywords remain present, when `--snippet-radius 0` is used.
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
      "matches": [
        {"keyword": "running", "where": "title", "snippet": "Running Shoes"}
      ],
      "incoming_links": 2
    }
  ]
}
```

Field names are stable across releases - agents and humans both consume
this. New fields may be added; existing fields will not be renamed.

## Link text output

Link output names the resolved target, emits one bullet per neighbor with its relation and directional counts, and adds an unresolved-outgoing-links section only when needed:

```text
# Link neighbors for "resources/Running Shoes.md" (2 matches)

- projects/Run a 5K.md (project, supports: Health) - mutual: outgoing 1, incoming 2
- resources/Race Day.md (resource) - outgoing: outgoing 1, incoming 0

## Unresolved outgoing links

- Missing Note (missing, 1 occurrence)
```

Zero neighboring notes is successful and renders `No linked notes.` Unresolved outgoing links can still appear below that message.

## Link JSON contract

Link mode uses a distinct result contract and an explicit top-level `"mode": "links"`. Existing keyword JSON is unchanged.

The relation counts in `summary` describe returned results after filters and `--limit`. `unresolved_outgoing` and `unresolved_links` remain complete because filtering neighbors does not repair or hide links written in the target note.

```json
{
  "vault": "/path/to/vault",
  "mode": "links",
  "target": {
    "path": "resources/Running Shoes.md",
    "type": "resource",
    "supports": []
  },
  "scope": {
    "types": null,
    "quest": null,
    "include_archive": false,
    "limit": null
  },
  "summary": {
    "results": 2,
    "outgoing": 1,
    "incoming": 0,
    "mutual": 1,
    "unresolved_outgoing": 1
  },
  "results": [
    {
      "path": "projects/Run a 5K.md",
      "type": "project",
      "supports": ["Health"],
      "link_context": {
        "relation": "mutual",
        "outgoing_occurrences": 1,
        "incoming_occurrences": 2
      }
    }
  ],
  "unresolved_links": [
    {
      "target": "Missing Note",
      "occurrences": 1,
      "reason": "missing",
      "candidates": []
    }
  ]
}
```

## Use as a library

```python
from para_quest_notes.workflows.search.api import (
    LinkTargetError,
    render_link_text,
    render_text,
    search,
    search_links,
)

results = search(vault, ["running"], types=["resource"])
print(render_text(results))

try:
    neighbors = search_links(vault, "Running Shoes", types=["project"])
except LinkTargetError as exc:
    print(exc)
else:
    print(render_link_text(neighbors))
```

## Shared infrastructure

`pqn-search` is the sibling of `pqn-quests`; both consume the two
link-aware building blocks in the `vault/` package:

- **`vault/links.py`** - canonical wikilink parser, compatibility backlink index, and reusable one-pass in-memory note graph. The graph keys notes by vault-relative path, resolves basenames case-insensitively, stores directional occurrence counts, and preserves missing or ambiguous outgoing targets without a persistent index.
- **`vault/scope.py`** - PARA-type detection and the `--type` / `--quest`
  filter.

## Scope / non-goals

- **One hop only.** Link mode does not transitively traverse the graph and has no `--depth`; `pqn-quests --depth` is a separate `supports:` rollup concern.
- **No similarity search.** "Find related notes without a direct link" remains separate follow-up work. No embeddings, vectors, LLM, network, or opaque relevance score is introduced here.
- **No graph rendering / pattern analysis.** Visualizing the wikilink
  graph or surfacing "surprising" relationships is a different concern
  (and overlaps
  [markdown-loom](https://github.com/solvaholic/markdown-loom));
  `pqn-search` is the headless, Quest-scoped complement.
- **No regex or term-frequency ranking in v1.** Keep it predictable,
  then iterate against real examples.
