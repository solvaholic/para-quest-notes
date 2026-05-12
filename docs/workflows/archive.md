# pqn-archive

Move a completed Project note from `projects/` to `archive/projects/`
while freezing its task state and recording an `## Outcome` section.
One note per invocation. **Projects only in v1** — Areas and Resources
escalate. No LLM in v0.1.

## What it does

Eight pure steps (`--apply` only gates the actual disk write/move):

1. **`resolve_target`** — finds the file under `projects/` from a path
   or basename. Escalates on zero matches, multiple matches, or
   targets outside `projects/`.
2. **`verify_project`** — parses frontmatter (plus deprecated tail
   backmatter for legacy notes) and requires `type: project`.
3. **`scan_open_tasks`** — fence-aware: walks the body once and lists
   `- [ ]` (open) and `- [/]` (in-progress) lines outside fenced code
   blocks. The same candidate set drives the rewrite.
4. **`decide_task_action`** — if open tasks exist and the user didn't
   pass `--cancel-open-tasks`, escalate with the offending lines. The
   user re-invokes with or without the flag.
5. **`prepare_outcome`** — if the body already has an `## Outcome` (or
   `# Outcome`) heading, keep it. Otherwise require `--outcome "..."`
   text; escalate if missing.
6. **`compose_archive`** — builds the archived note's final content:
   - Merges legacy tail backmatter into canonical frontmatter
     (frontmatter wins on conflict; tail fence is dropped).
   - Rewrites `[ ]`/`[/]` -> `[-]` with `❌ <today>` cancellation marker,
     block-id-aware (`[ ] do thing ^abc123` -> `[-] do thing ❌ <today> ^abc123`).
   - Escalates if any open task carries Obsidian Tasks scheduling
     emoji (📅 ⏳ 🛫 🔁 ✅ ❌) — those need human attention.
   - Appends `## Outcome` if `--outcome` was supplied.
   - Computes the destination by mirroring the source's sub-path:
     `projects/foo/X.md` -> `archive/projects/foo/X.md`.
7. **`write_and_move`** — `--apply` only. Writes the archived content
   atomically (sibling temp + `os.replace`), then removes the source.
   Write-first/remove-second means a crash leaves both copies, not
   neither. Refuses to overwrite an existing destination.
8. **`validate_after`** — `--apply` only. Runs `validate.api.validate_paths`
   scoped to the new path. Whole-vault validation stays the user's
   call (`pqn-validate`).

## Usage

```bash
# Dry-run, project has Outcome + no open tasks.
pqn-archive --vault ~/notes "Brew Setup"

# Same, written.
pqn-archive --vault ~/notes "Brew Setup" --apply

# Project has open tasks → cancel them as part of archiving.
pqn-archive --vault ~/notes "Brew Setup" \
  --outcome "Shipped. New grinder + V60 routine." \
  --cancel-open-tasks --apply

# Disambiguate by passing a path.
pqn-archive --vault ~/notes "projects/2024/Brew Setup.md" \
  --outcome "..." --apply
```

The `target` argument accepts either a vault-relative path or just a
basename (with or without `.md`). Basename search is scoped to
`projects/` only.

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)).

Exit codes:

* `0` — planned (dry-run) or moved (apply) the note successfully.
* `1` — escalation or runtime error.
* `2` — invocation problem (vault not found, etc.).

## JSON contract

```json
{
  "vault": "/Users/me/notes",
  "apply": true,
  "ok": true,
  "plan": {
    "source": "projects/Brew Setup.md",
    "destination": "archive/projects/Brew Setup.md",
    "open_tasks": [
      {"line": 7, "state": " ", "text": "grind", "bullet": "- "}
    ],
    "tasks_cancelled": 1,
    "outcome_action": "inserted",
    "frontmatter_migrated": false
  },
  "moved": true,
  "escalation": null,
  "error": null,
  "run_id": "a1b2c3d4e5f6"
}
```

`outcome_action` is `"kept"` when the note already had `## Outcome`,
`"inserted"` when `--outcome` was applied, or `"none"` (only seen on
escalation paths that stopped before this step).

### Common escalation shapes

```json
{
  "step": "resolve_target",
  "reason": "pqn-archive v1 is Projects only (target is under areas/)",
  "options": [],
  "context": {"path": "areas/Home.md"}
}
```

```json
{
  "step": "decide_task_action",
  "reason": "2 open task(s) in this Project; close them in the editor or re-run with --cancel-open-tasks",
  "options": [
    {"line": 7, "state": " ", "text": "grind"},
    {"line": 8, "state": "/", "text": "pour"}
  ],
  "context": {"source": "projects/Brew Setup.md"}
}
```

```json
{
  "step": "prepare_outcome",
  "reason": "note has no '## Outcome' section; pass --outcome \"...\" with a brief summary of what came of this Project",
  "options": [],
  "context": {"source": "projects/Brew Setup.md"}
}
```

```json
{
  "step": "compose_archive",
  "reason": "some open tasks carry Obsidian Tasks scheduling metadata (📅/⏳/🛫/🔁); resolve them in the editor and re-run",
  "options": [{"line": 9}],
  "context": {"source": "projects/Brew Setup.md"}
}
```

## Known limitations (v0.1)

* **No LLM-drafted `## Outcome`.** The user supplies it. A future
  `--draft-outcome` flag could call a local model; deferred until
  there's appetite for the first prose-output prompt in the codebase.
* **Projects only.** Areas and Resources escalate. v2 could add them;
  the layout decision (`archive/areas/...`?) is open.
* **No bulk mode.** One target per invocation by design.
* **No inbound wikilink rewrites.** Wikilinks resolve by basename, so
  moving a note into `archive/` doesn't break `[[Title]]` references.
  Out of scope to update them.
* **No `git mv` integration.** We just write+unlink. If your vault is
  a git repo, expect a delete + add pair in `git status`.
