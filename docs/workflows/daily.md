# pqn-daily

File a single date-shaped note (`YYYY-MM-DD.md`) into its canonical
home at `resources/daily_notes/YYYY/MM/`. One note per invocation.
**Filing only in v0.1** — authoring an empty daily note from scratch
is deferred (see "Known limitations" below). No LLM.

## What it does

Eight pure steps (`--apply` only gates the actual disk write/move):

1. **`resolve_target`** — finds the source file from a path or
   basename. Basename search is scoped to vault root, `inbox/` (any
   depth), and `resources/daily_notes/` (any depth) — the only legal
   places a daily note can sit. Escalates on zero or multiple matches,
   or when an explicit path lands outside that scope.
2. **`detect_shape`** — basename must match
   `^\d{4}-\d{2}-\d{2}\.md$` *and* parse as a real calendar date
   (rejects e.g. `2026-02-31.md`). Stashes year / month / day for
   later steps. Escalates otherwise.
3. **`inspect_parent`** — examines the source's vault-relative parent.
   Allowed: vault root, `inbox/...`, `resources/daily_notes/...`.
   Escalates when under `projects/`, `areas/`, `archive/`, or any
   other `resources/<...>/` subtree — those imply a different PARA
   home, not a misfiled daily note.
4. **`compute_destination`** — `resources/daily_notes/YYYY/MM/YYYY-MM-DD.md`
   derived from the filename, not filesystem mtime. Sets
   `already_at_destination` when the source is already at this path.
5. **`check_collision`** — refuses to overwrite the destination, then
   delegates to `validate.api.check_basename_available` with
   `ignore_path=source` so the source itself doesn't count as a
   collision. **No silent merge.** When `already_at_destination`,
   skips the collision check (the source *is* the destination).
6. **`compose_note`** — reads the source via
   `vault.frontmatter.split_note` (tolerates legacy tail backmatter).
   Migrates any tail backmatter into frontmatter (frontmatter wins on
   conflict; tail fence dropped) per repo policy. Prepends
   `# YYYY-MM-DD\n\n` to the body when the first non-blank line isn't
   already an `# H1` matching the date. Daily notes do **not** get
   canonical PARA frontmatter injected — by design they inherit Quest
   context from their tasks and links, not from frontmatter (see
   [`docs/notes-system.md`](../notes-system.md), "Daily notes").
7. **`move_file`** — `--apply` only. Atomic write to destination
   (sibling temp + `os.replace`), then `unlink` the source.
   Write-first / remove-second means a crash leaves both copies, not
   neither. Refuses to overwrite a pre-existing destination (defensive
   re-check). When `already_at_destination`, this step is a no-op
   success (idempotent re-runs are safe — `pqn-daily 2026-05-12.md`
   from cron won't fail just because the file is already filed).
8. **`validate_after`** — `--apply` only. Runs
   `validate.api.validate_paths` scoped to the destination.

Frontmatter is the canonical metadata location (decided 2026-05-12;
see [`docs/PLAN.md`](../PLAN.md)). Backmatter is tolerated on read
and migrated on touch.

## Usage

```bash
# Dry-run, file a loose daily note from the vault root.
pqn-daily --vault ~/notes 2026-05-12

# Same, written.
pqn-daily --vault ~/notes 2026-05-12 --apply

# From inbox (auto-found by basename).
pqn-daily --vault ~/notes 2026-05-12.md --apply

# Disambiguate by path.
pqn-daily --vault ~/notes inbox/2026-05-12.md --apply

# Idempotent: already-filed file is a no-op success (cron-safe).
pqn-daily --vault ~/notes 2026-05-12 --apply
```

`target` accepts either a vault-relative path or a basename
(with or without `.md`).

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)).

Exit codes:

* `0` — planned (dry-run), moved (apply), or no-op idempotent re-run.
* `1` — escalation (rules didn't fit) or runtime error.
* `2` — invocation problem (vault not found, etc.).

## JSON contract

```json
{
  "vault": "/Users/me/notes",
  "apply": true,
  "ok": true,
  "plan": {
    "source": "inbox/2026-05-12.md",
    "destination": "resources/daily_notes/2026/05/2026-05-12.md",
    "date": "2026-05-12",
    "h1_inserted": true,
    "frontmatter_migrated": false,
    "already_at_destination": false
  },
  "moved": true,
  "escalation": null,
  "error": null,
  "run_id": "a1b2c3d4e5f6"
}
```

`already_at_destination` is `true` when the source is already at the
canonical path. In that case `moved` is `false`, `h1_inserted` may
still be `true` (the H1 fix is applied if needed) but only on
`--apply`, and `ok` is `true`.

### Common escalation shapes

```json
{
  "step": "detect_shape",
  "reason": "filename does not match YYYY-MM-DD.md",
  "options": [],
  "context": {"basename": "2026-05-12-notes.md"}
}
```

```json
{
  "step": "inspect_parent",
  "reason": "source is under projects/; pqn-daily files daily notes only (move it manually if it really is a daily note)",
  "options": [],
  "context": {"source": "projects/Brew Setup/2026-05-12.md"}
}
```

```json
{
  "step": "check_collision",
  "reason": "destination already exists with different content",
  "options": [{"existing": "resources/daily_notes/2026/05/2026-05-12.md"}],
  "context": {"destination": "resources/daily_notes/2026/05/2026-05-12.md"}
}
```

## Known limitations (v0.1)

* **Filing only — no authoring.** `pqn-daily` does not create today's
  empty daily note. The shape of an authoring mode (where the
  template lives, what frontmatter if any to seed, whether to
  pre-populate routine tasks from Areas) benefits from real filing
  usage feedback first. Tracked as a Phase 5.5 / post-v1 candidate
  in [`docs/PLAN.md`](../PLAN.md).
* **No bulk migration.** One target per invocation by design.
* **No task roundup.** Surfacing overdue / due-today / scheduled
  tasks into the daily note is a separate post-v1 candidate (see
  [`docs/PLAN.md`](../PLAN.md), "Post-v1 candidates").
* **No `git mv` integration.** Same as `pqn-archive`: write+unlink,
  so a git-tracked vault sees a delete + add pair.
