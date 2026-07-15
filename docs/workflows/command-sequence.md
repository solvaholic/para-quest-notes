# Command sequence

How the `pqn-*` commands relate to each other, and the order to run
them for common scenarios.

## Command dependency map

```
pqn-validate   (read-only, no deps - run anytime)
pqn-config     (read-only, no deps - inspect effective config)
pqn-create     (needs vault path; creates areas/, projects/, resources/)
pqn-daily      (needs vault path; files existing date-shaped notes)
pqn-ingest     (needs Ollama + Quest notes in areas/ to classify against)
pqn-archive    (needs a project note in projects/ to archive)
```

Key relationships:

- **`pqn-create` enables `pqn-ingest`** - ingest's `pick_quest` step
  picks from declared Quest notes in `areas/`. No Quest notes = ingest
  can't classify. Create your Main Quest and Side Quest area notes
  first.
- **`pqn-create` enables `pqn-archive`** - you can only archive a
  project that exists under `projects/`.
- **`pqn-daily` is independent** - it files date-shaped notes into
  `resources/daily_notes/YYYY/MM/`. It doesn't create new notes; it
  moves existing ones to their canonical path.
- **`pqn-validate` is a bookend** - run it before and after mutations
  to confirm vault health.
- **`pqn-config` is read-only inspection** - reports the effective
  config (and its provenance) a run will use. Run it anytime to answer
  "which vault/model/templates will this pick, and why?"

## Design principles

**Dry-run first.** Every mutating command defaults to dry-run. The
intended rhythm is: run, review output, re-run with `--apply`. This
protects against surprises and lets you inspect what will change
before it happens.

**One note per invocation.** Commands operate on one file at a time
(except `pqn-validate` and `pqn-ingest`, which scan). For bulk
operations, loop with `--format json` and collect escalations. See
"Scripting patterns" below.

**Escalation, not failure.** When a command can't decide (ambiguous
classification, missing Quest, duplicate filename), it escalates with
a structured payload rather than crashing. The user (or agent)
resolves the issue and re-runs.

## Scenarios

### New vault setup

You have a vault of markdown notes that aren't yet organized under
PARA structure. Your notes lack consistent frontmatter and you haven't
encoded your Main Quests as Area notes yet.

**Prerequisites:**

- Specify your vault with `--vault PATH` on every command, or set
  `vault:` in `~/.config/para-quest-notes/config.yaml`. Vault
  discovery by walking up from cwd won't work until `areas/` and
  `projects/` exist.

**Sequence:**

```
1. Move vault contents into {vault}/inbox/
2. pqn-validate --vault PATH              (baseline - expect issues)
3. pqn-create Main Quest area notes       (establishes areas/)
4. pqn-create Side Quest area notes       (optional, adds classification targets)
5. pqn-ingest --file ... --apply          (iteratively ingest from inbox/)
6. pqn-daily --apply                      (file any date-shaped notes)
7. pqn-validate --vault PATH              (confirm health)
```

Step 5 is iterative. Use `rg` or similar to identify inbox files by
topic, wikilink target, or folder, then ingest them in batches.
Escalations stay in inbox for the next pass.

Notes about templates: if your vault had a templates directory, those
files are now in inbox too. Ignore them - para-quest-notes has no use
for templates until a future milestone. Leave them in inbox or move
them aside manually.

### Daily use (human)

You have a working vault with Quest notes in place. Your config.yaml
has `vault:` set so you can run commands from anywhere.

```
pqn-create --type project --title "..." --supports "[[Quest]]" --apply
pqn-create --type resource --title "..." --apply
pqn-daily 2026-07-05.md --apply         (file today's daily note)
pqn-ingest --apply                       (sweep inbox/)
pqn-validate                             (periodic health check)
pqn-archive "Done Project" --apply       (archive completed projects)
```

Order doesn't matter for daily use - each command is independent once
the vault has Quest notes. The validate sandwich (validate before and
after a batch of mutations) is good practice but not required.

### Agent automation

An agent running on behalf of a human. Same commands, different
emphasis: structured output and escalation handling.

```bash
# Sweep inbox - collect results as JSON
pqn-ingest --vault ~/notes --format json --apply

# Create notes as needed
pqn-create --vault ~/notes --format json --apply \
  --type project --title "..." --supports "[[Quest]]"

# Archive completed projects
pqn-archive --vault ~/notes --format json --apply "Project Name"
```

When a command escalates (exit code 1 + JSON payload), the agent
should:
1. Log the escalation for human review, or
2. Resolve it (e.g., create the missing Quest, then re-run), or
3. Skip and move on (the note stays in inbox)

### Pre-release / CI check

The smoke script (`scripts/smoke.sh`) runs this sequence without
Ollama to verify CLI arg parsing and vault interactions:

```
pqn-validate  (vault well-formed)
pqn-create    (scaffold a note)
pqn-daily     (file a daily note)
pqn-archive   (archive a project)
pqn-ingest    (expect escalation without Ollama)
pqn-validate  (vault still well-formed after mutations)
```

## Scripting patterns

### Bulk ingest with escalation collection

```bash
# Ingest everything, collect escalations
for f in $(find inbox/ -name '*.md'); do
  pqn-ingest --vault ~/notes --file "$f" --format json --apply 2>&1
done | jq -s '[.[] | select(.escalated)]' > escalations.json
```

### Scheduled daily filing

```bash
# In crontab or launchd - file today's daily note if it exists
pqn-daily --vault ~/notes --apply "$(date +%Y-%m-%d).md" 2>/dev/null
```

### Validate as a CI gate

```bash
pqn-validate --vault ~/notes --format json --strict
# Exit 0 = clean, Exit 1 = issues found
```

## What's not here

- **Undo / recovery:** no `pqn-unarchive` exists. To recover from a
  wrong archive or ingest, manually move the file back and fix
  frontmatter. `pqn-validate` afterward confirms you're clean.
- **Quest evolution:** renaming a Main Quest, retiring a Side Quest,
  or splitting an Area requires manual edits to frontmatter across
  affected notes, then `pqn-validate` to confirm. No tooling for this
  yet.
- **Routine generation:** the notes-system spec describes recurring
  tasks generated into daily notes. This workflow doesn't exist yet.
- **Note authoring for `pqn-daily`:** currently filing-only. It moves
  an existing `YYYY-MM-DD.md` to its canonical path but doesn't
  create a blank daily note from scratch.
