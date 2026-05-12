# Notes System

The spec for how notes in your vault are organized. It helps both
human users and AI workflows:

- Reason about priorities and how work aligns with long-term goals
- Decide where a note belongs in the vault
- Generate a Main Quest index from the contents of the vault

> **Path conventions.** All paths in this doc are relative to the root
> of your notes vault. Directory names use `snake_case`. Note filenames
> use `Title Case.md` so wikilinks read naturally (e.g.,
> `[[Health]]`, `[[Replace Water Heater]]`). Wikilinks omit paths;
> Obsidian's prefix search (`[[hea...`) makes typed links fast. The
> trade-off is that two notes can't share a title - the
> `pqn-validate` workflow catches that.

## Two overlapping models

This system layers a **Quest** model on top of the **PARA** method.

### PARA (what kind of note is this?)

Every note is one of four things:

- **Project** - work that begins and ends, achieving an expected outcome
- **Area** - an ongoing topic or responsibility, no end date
- **Resource** - reference info, links, or knowledge about a thing
- **Archive** - a location, not a type. Notes move here when they are
  done, abandoned, or expired

### Quests (why does this work matter?)

Areas and Projects are tagged with a Quest so we know what they serve:

- **Main Quest** - an Area that supports core values and long-term
  goals. Essential, not optional.
- **Side Quest** - an Area that supports a Main Quest. Important but
  failing to advance one won't be catastrophic.
- **Project** - time-bound work that advances or sustains a Main or
  Side Quest.

#### Example Main Quests

These are illustrative only. Real Main Quests are user-defined and
expected to evolve. The synthetic corpus generator
(`para_quest_notes.corpus`) uses examples like:

- **Health** - physical and mental well-being
- **Connect** - family, community, relationships
- **Create** - things you make, ship, or grow

A Side Quest like **Maintain Home** might serve multiple Main Quests
(Health via a safe living space, Create via a workshop). That
multi-Quest reach is declared in its own frontmatter via `supports:`.
Related Areas like `Garden`, `Workshop`, or `Vehicles` are plain Areas
that support `[[Maintain Home]]`, not Side Quests in their own right.

Side Quests don't sit "under" Main Quests in the directory tree - the
layout is PARA-first, so all Quest notes live in `areas/`. The
relationship is declared in frontmatter: each Side Quest note's
`supports:` field lists the Main Quest(s) it serves. The index
generator picks up the relationship from there.

Resource notes are discovered via **incoming wikilinks** from active
Areas and Projects, not by forward links from the Resource itself. An
active Area or Project that uses a Resource links to it; the Areas
and Projects appear as backlinks on the Resource notes. No required
frontmatter on Resources.

Optional frontmatter on a Resource is fine when it helps - for example,
a Resource created before its consuming Project exists, or one that
serves many things and explicit forward links add value. When used,
the frontmatter follows the schema in "Metadata schema (frontmatter)"
below:

```yaml
---
type: resource
quest: none
supports:
  - "[[Health]]"
  - "[[Maintain Home]]"
---
```

Quote wikilinks in YAML - `[` is a flow-sequence character and
unquoted `[[foo]]` is ambiguous to strict YAML parsers. A linter or
formatter should enforce this.

## Directory layout

PARA dictates the *top-level* directory for each note. Below that,
organize freely - `resources/Home/Water Heater Models.md` is fine, so
is `projects/2026/Replace Water Heater.md`. Sub-structure is for
human browseability; tooling keys off the PARA top-level and
frontmatter, not the deeper path.

```
<vault>/
├── areas/        # Main Quest, Side Quest, and Capability notes
├── projects/     # Time-bound work
├── resources/
│   ├── daily_notes/YYYY/MM/YYYY-MM-DD.md
│   └── ...       # Free sub-structure
├── inbox/        # Quick-capture, ephemeral; ingested into the above
└── archive/
    ├── areas/
    ├── projects/
    └── resources/
```

Archived notes mirror the PARA structure **and the active note's full
sub-path**. A Project at `projects/foo/bar/Project Note.md` archives
to `archive/projects/foo/bar/Project Note.md`. Year sub-dirs (e.g.,
`archive/projects/2025/`) can be added if volume warrants.

## Archive: location, not type

Archive is **where** done/abandoned/expired notes go - not what they
are. The note keeps its original `type`, `quest`, and `supports:`
values; only its location changes. This preserves provenance ("what
did I do for Health in 2026?") and keeps the schema simple.

For Projects, the heuristic for "is this still active?" is whether
any line matches `^- \[[ /]\] ` (Obsidian Tasks open or in-progress
state). Zero such lines = archive-eligible. The mechanics of
archiving (when to do it, what to do with stale wikilinks, whether
to add an outcome statement) are out of scope for this spec; see the
`pqn-archive` workflow.

## Capabilities (cross-cutting Areas)

Some Areas serve multiple Quests and don't sit cleanly under one.
These are **Capabilities** - reusable skills, knowledge domains, or
tools. Examples: "Technical Troubleshooting", "Amateur Radio",
"Be Organized".

Capabilities are still Areas. Per Rule 1, a Capability with tasks
must support at least one Quest in `supports:`; cross-cutting
Capabilities list every Quest they serve. The index generator should
surface them in their own section (e.g., flagged with
`capability: true` in frontmatter) rather than duplicating them under
every Quest they touch.

## Daily notes

Daily notes are a special Resource. They live at
`resources/daily_notes/YYYY/MM/YYYY-MM-DD.md`. Tasks emitted by the
routine generator (see "Repetitive, ongoing work" below) land in
daily notes by default. Daily notes inherit Quest context from the
tasks and links they contain, not from frontmatter.

## Quest index

The Main Quest index is **generated** from the vault, not
hand-maintained. Inputs:

- Hand-authored Main Quest notes (one per Main Quest, e.g.,
  `areas/Health.md`) provide the name, purpose, and ordering
- Areas and Projects across the vault declare their Quest in
  frontmatter (wikilink to the Main or Side Quest note)
- Resources are surfaced via incoming wikilinks from active Areas and
  Projects (no required frontmatter)

The generator walks the vault, groups by Quest, and emits an index
note (e.g., `index.md`). Regenerating is cheap and idempotent. Areas
or Projects with no Quest tag, and Resources with no incoming links,
are listed under "Unassigned" so they can be triaged.

## Metadata schema (frontmatter)

This schema is a starting point. Expect it to evolve with use;
capture deviations and revise this section.

**Canonical location: frontmatter** (the leading `---...---` YAML
block). Some legacy notes carry the same schema in *backmatter* (a
trailing `---...---` YAML block at the end of the file); workflows
tolerate it on read and migrate it to frontmatter on touch (e.g.
`pqn-ingest --apply`). New notes should always use frontmatter.

Every note that needs metadata declares two things: its **PARA
type** and its **Quest type**. Notes that support one or more Quests
list those Quests in `supports:`.

```yaml
---
type: project           # project | area | resource
quest: none             # main | side | none
supports:
  - "[[Health]]"
  - "[[Maintain Home]]"
---
```

- **`type`** mirrors the note's PARA classification. Archive is a
  *location*, not a type: when a note moves under `archive/`, its
  `type` stays at whatever PARA value it had while active
  (`project`, `area`, `resource`).
- **`quest`** is `main` for Main Quest notes, `side` for Side Quest
  notes, and `none` for everything else. Always a string; do not use
  the YAML boolean `false` - keeping the field a single type avoids
  parser-round-trip surprises.
- **`supports`** lists wikilinks to the Quests this note serves:
  - **Main Quest notes** (`quest: main`) explicitly list themselves
    in `supports`. This makes implicit self-support visible to
    tooling.
  - **Side Quest notes** (`quest: side`) must list one or more Main
    Quests they serve. A Side Quest may serve multiple Main Quests.
  - **Areas and Projects** (`quest: none`) with tasks must list one
    or more Quests (Main or Side) they support. Without tasks,
    `supports` is optional.
  - **Resources** (`quest: none`) - `supports` is always optional.

Quote wikilinks in YAML - `[` is a flow-sequence character and
unquoted `[[foo]]` is ambiguous to strict YAML parsers.

## Mapping table

| PARA type         | `quest` value | Has tasks? | `supports` required?           | Example                                                                       |
| ----------------- | ------------- | ---------- | ------------------------------ | ----------------------------------------------------------------------------- |
| Area (Main Quest) | `main`        | Sometimes  | Yes (lists itself)             | `areas/Health.md`                                                             |
| Area (Side Quest) | `side`        | Sometimes  | Yes (1+ Main Quests)           | `areas/Maintain Home.md`                                                      |
| Area (other)      | `none`        | Sometimes  | If tasks present, 1+ Quests    | `areas/Garden.md` (supports `[[Maintain Home]]`)                              |
| Project           | `none`        | Usually    | Yes, 1+ Quests                 | `projects/Replace Water Heater.md`                                            |
| Resource          | `none`        | No         | Optional                       | `resources/Home/Water Heater Models.md`                                       |

Archived notes keep their pre-archive `type`, `quest`, and
`supports:` values. Archive is a location, not a type.

## Rules, with examples

1. **Notes with tasks must support one or more Quests.** Areas and
   Projects declare support via `supports:` in frontmatter. Main Quest
   notes (`quest: main`) with tasks list themselves in `supports`;
   Side Quest notes (`quest: side`) with tasks must list one or more
   Main Quests. `inbox/` and `resources/daily_notes/` are exempt -
   inbox notes are ephemeral (ingested into Areas/Projects later) and
   daily notes inherit Quest context from the tasks and links they
   contain.

   - OK: `projects/Replace Water Heater.md` has tasks and
     `supports: ["[[Maintain Home]]"]` in frontmatter.
   - Not OK: `areas/Random Topic.md` has tasks but no `supports:`
     entry. Add one, or it's not really an Area worth keeping.

2. **When drafting a Project, ruthlessly prioritize toward Main and
   Side Quests.** If a proposed Project doesn't serve one, archive
   the idea or drop it.

3. **Every active Resource must be linked from at least one active
   Area or Project.** Resources discovered via incoming wikilinks;
   frontmatter Quest tags optional. A Resource with no incoming links
   from active notes is a candidate for `archive/resources/`.

4. **Areas don't end; Projects do.** When a Project's outcome is
   reached (or it's abandoned), move it to `archive/`. Areas stay put.

## Repetitive, ongoing work

Mowing the lawn, servicing the car, paying quarterly taxes - these
don't fit cleanly as Projects (they don't end) or as Areas (they're
not topics, they're recurring obligations).

Treat them as **routines that belong to an Area**. The Area note owns
the recurrence; individual occurrences become dated tasks (in daily
notes or a Project note for a specific instance).

### Pattern

- **Routine definition lives in the Area note.**
  Example: `areas/Garden.md` has a "Routines" section listing
  "Mow lawn - weekly Apr-Oct", "Service mower - annually in spring",
  etc.

- **Recurrence is generated, not hand-maintained.** A scheduled job
  reads the Area's routines and emits dated tasks into daily notes
  (or into the inbox) on the right cadence. (Workflow not yet
  implemented; tracked under "Open questions".)

- **A single occurrence can graduate to a Project** if it grows
  beyond the routine. "Service car" is a routine; "replace the
  transmission" is a Project under the same Area.

- **Resources support routines.** `resources/Home/Lawn Mower Manual.md`
  gets linked from the Area's Routines section so workflows can find
  it when generating tasks.

### Example

`areas/Garden.md` (Area supporting `[[Maintain Home]]`):

```markdown
## Routines
- Mow lawn - weekly, Apr-Oct -> [[Lawn Mower Manual]]
- Service mower - annually in spring
- Replace mulch - every 2 years

## Active Projects
- [[Build Raised Beds]]
```

The recurring-task generator turns "Mow lawn - weekly, Apr-Oct" into
`- [ ] Mow lawn ⏳ 2026-05-02` in the daily note for that Saturday.
The task inherits its Quest from `areas/Garden.md`, so rule 1 is
satisfied without per-task tagging.

## Open questions

- Where exactly does the routine generator live, and what triggers it?
- Should one-off tasks (e.g., "call plumber") flow through the inbox
  and get assigned to an Area later, or should the workflow refuse to
  capture a task without a Quest link?
- Do we want a lightweight "Main Quest index" note that lists all
  Main and Side Quests in one place, or is the `areas/` directory
  listing enough? (Leaning toward generated index.)
- How do we deactivate an Area without archiving it? (Likely just
  `archive/areas/old-area.md` with a "why" note.)
- Do Capabilities need their own top-level dir, or do they live in
  `areas/` with a flag? (Leaning toward `areas/` with
  `capability: true` in frontmatter.)
