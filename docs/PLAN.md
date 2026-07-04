# Plan: para-quest-notes

> Working plan for the `para-quest-notes` re-architecture. Lives in the
> repo so any agent session (or human) starting in the repo dir has the
> full design context. Update at large milestones; the README's
> roadmap section is the human-facing snapshot if/when it diverges.

## Problem

Most "AI for notes" tooling sends notes to a cloud-hosted model.
That has two costs:

1. **Privacy:** notes get sent to whoever hosts the model.
2. **Cloud dependency:** management of personal markdown shouldn't
   require network access to a third party.

The PARA + Quest reasoning that aligns day-to-day notes with
long-term goals (and escalates when the rules don't fit) is the
keeper. The "send everything to a cloud LLM" part is not.

## Approach

Re-architect into **scripted workflows** that run locally:

- Each workflow = a Python module that orchestrates deterministic
  scripts plus narrowly-scoped local LLM calls (Ollama).
- A workflow is callable two ways:
  - **Headless / CLI:** user (or cron) runs `python -m
    para_quest_notes.workflows.ingest_inbox <path>`.
  - **From an agent:** the new repo ships thin SKILL.md wrappers whose
    procedure is "call this CLI, surface the JSON result." The agent
    never sees note bodies; the workflow does.
- LLM is used *only* for understanding/summarization/classification
  decisions that benefit from natural-language reasoning. Everything
  else is plain code.
- Runtime: **plain Python + a thin adapter** (not LangChain). The
  adapter wraps Ollama, prompt templating, retries, and a small
  `Step`/`Workflow` abstraction. No framework lock-in.

Built in a **public repo** (clean slate, generic - no assumptions
about anyone's note history).

The deliverable is a **distributable CLI tool** users install once and
run from inside any markdown vault. PARA+Quest is the *value
proposition*: the workflows keep Quest reasoning front and center
because that's what enables project/activity prioritization.

## Decisions (locked from clarifying Q&A + follow-up)

- **Runtime:** plain Python + thin adapter. No LangChain.
- **Repo strategy:** new **public** parallel repo:
  `solvaholic/para-quest-notes`. Generic; no personal data.
- **Distribution:** install via `pipx`/`uv tool install`. Entry-point
  CLIs use the `pqn-` prefix (e.g., `pqn-ingest`, `pqn-validate`).
  Runs against any vault on disk, identified by `--vault` /
  `PARA_QUEST_VAULT` env / cwd discovery.
- **Config split:**
  - **In the user's vault (content):** Quest outline, Quest/Area
    notes, anything that's part of *their notes*. Workflows read
    these as data.
  - **In `~/.config/para-quest-notes/config.yaml` (XDG-respecting,
    falls back to `$HOME/.config`):** model selection, prompt
    version pins, default vault path, output verbosity, escalation
    behavior. Sensible defaults so first run works without a config
    file.
- **Pilot workflow:** `ingest-inbox-notes` - judgment-heavy, best
  stress test of LLM + escalation + Quest alignment.
- **Test corpus:** synthesized from `docs/notes-system.md` plus
  seed Quests. Doubles as docs/demo material in the public repo.
- **Eval strategy:** per-step golden judging. Each LLM step has a
  labeled fixture; eval reports per-step accuracy across models.
- **Agent integration:** deferred to a later phase. v1 ships CLIs +
  documented JSON contracts. SKILL.md wrappers come once the CLIs
  are stable.

## Architecture sketch

```
para-quest-notes/
├── README.md                       # public-facing: install, quickstart, demo
├── LICENSE
├── pyproject.toml                  # entry points: pqn-ingest, ...
├── docs/
│   ├── notes-system.md             # PARA+Quest spec (generic)
│   ├── configuration.md            # ~/.config layout, vault discovery
│   ├── PLAN.md                     # this file
│   └── workflows/                  # per-workflow user docs
├── src/para_quest_notes/
│   ├── adapter/                    # thin runtime
│   │   ├── llm.py                  # Ollama client wrapper
│   │   ├── prompts.py              # template loader, render
│   │   ├── step.py                 # Step / Workflow abstraction
│   │   ├── errors.py              # EscalateToUser + workflow errors
│   │   ├── config.py               # XDG config load + defaults
│   │   ├── vault.py                # vault path discovery
│   │   ├── cli.py                  # shared base parser (--vault, --format)
│   │   ├── fake_llm.py            # test double for unit/eval
│   │   └── trace.py               # JSONL run-trace logger
│   ├── workflows/
│   │   └── ingest_inbox/           # pilot
│   │       ├── __init__.py
│   │       ├── cli.py              # entry-point: pqn-ingest
│   │       ├── pipeline.py
│   │       ├── steps/
│   │       │   ├── scan_note.py           # read frontmatter + body, find attachments
│   │       │   ├── classify_para.py       # LLM step
│   │       │   ├── pick_quest.py          # LLM step
│   │       │   ├── propose_filename.py    # LLM step
│   │       │   ├── plan_destination.py    # pure code
│   │       │   └── apply_move.py          # pure code, atomic
│   │       └── prompts/
│   ├── corpus/                     # generator + sample vault for demos
│   │   ├── generate.py
│   │   ├── seeds.yaml              # generic Quests/Areas (e.g. Health,
│   │   │                           # Family, Craft) - no personal data
│   │   └── shapes/
│   └── eval/                       # eval harness code
│       ├── runner.py
│       ├── judges.py
│       └── report.py
├── eval/fixtures/                  # golden inputs + expected step outputs
└── tests/                          # unit + integration (fake LLM)
```

### Adapter shape (illustrative)

- `Step`: `name`, `run(context) -> StepResult`, optional `prompt_id`.
- `Workflow`: ordered list of steps; on `EscalateToUser` it stops and
  emits a structured escalation payload.
- `LLM`: model id, temperature, JSON-schema-constrained outputs (use
  Ollama's `format=json` or grammar where supported).
- All LLM calls record: model, prompt id, prompt hash, raw output,
  parsed output, latency. Trace goes to `runs/<timestamp>.jsonl` for
  the eval harness.

## Workstreams

Phases are dependency-ordered. No time estimates.

### Phase 0 - Repo bootstrap
- Create new **public** repo, README (install + quickstart against the
  bundled sample vault), `pyproject.toml` with CLI entry points,
  LICENSE.
- Port a generic copy of `docs/notes-system.md` (strip personal
  examples; replace with neutral ones).
- Ollama install/setup notes; pin a baseline model list
  (`granite4.1:30b`, `gemma3:27b`, `qwen3:30b`, `phi4-reasoning:14b` -
  validate exact tags on first run).
- `pre-commit` minimal: ruff + mypy (loose).
- CI: lint + tests (no Ollama in CI; tests for adapter use a fake LLM).

### Phase 1 - Adapter
- `LLM` client (Ollama), JSON-mode helper, retry, timeout.
- `Step` / `Workflow` primitives + escalation exception.
- Prompt template loader (Jinja2 or stdlib `string.Template`).
- **Config loader:** XDG-respecting (`$XDG_CONFIG_HOME` →
  `~/.config/para-quest-notes/config.yaml`), with sensible
  defaults so an empty config still works.
- **Vault discovery:** `--vault` arg → `PARA_QUEST_VAULT` env →
  walk-up-from-cwd looking for a marker (a directory containing both
  `areas/` and `projects/`) → `config.vault` → error with a helpful
  message.
- Run trace logger (JSONL) under
  `~/.local/state/para-quest-notes/runs/`.
- Fake LLM for unit tests (records calls, returns canned responses).

### Phase 2 - Synthetic corpus / sample vault ✅
- `corpus/seeds.yaml` with **generic** Quests/Areas (Health, Connect,
  Create + Side Quests Maintain Home, Stay Sharp). No personal data.
- `generate.py`: produces N notes across PARA types, location kinds
  (`para` / `topic` / `quest` / `inbox` / `daily`), frontmatter kinds
  (`none` / `obsidian_only` / `partial_para` / `full`), and orthogonal
  quirks (ambiguous quest, broken wikilinks, missing supports, etc.).
  Reproducible (seed-controlled).
- `samples/vault/` committed as a ~30-note sandbox. A reproducibility
  test (`tests/corpus/test_sample_vault.py`) regenerates it and
  asserts byte-equivalence so it can never silently drift.
- `python -m para_quest_notes.corpus` only — no `pqn-corpus` console
  script in v1 (the audience is maintainers + README quickstart, not
  end users with their own vaults).
- **Note for Phase 3:** the pilot's first step is `scan_note.py`
  (pure: read frontmatter + body, detect sibling attachments). The
  sketch and an earlier draft of this section called it
  `classify_location.py` — but for an inbox-only workflow the
  location is always inbox, so a "classify" verb would have been
  dishonest. An older revision of the sketch used `detect_shape.py`
  with a `gen1/gen2/gen3` reference — that's solvaholic-specific
  heritage and is intentionally absent from the public product.

### Phase 3 - Pilot workflow: `ingest_inbox` ✅
- Translated the legacy `ingest-inbox-notes` SKILL into discrete
  steps: `scan_note` → `classify_para` → `pick_quest` →
  `propose_filename` → `plan_destination` → `apply_move`. Each LLM
  step has its own prompt and validates its JSON output.
- CLI entry point `pqn-ingest`:
  `pqn-ingest [--vault PATH] [--apply] [--model ...] [--format json|text] [--file PATH]`.
- Default is dry-run; `--apply` performs moves, attachment moves,
  frontmatter merge, and incoming-wikilink rewrites across the vault
  excluding `archive/`.
- Escalation payload includes: file, step that escalated, reason,
  candidate options for the user.
- JSON output contract documented in
  [`docs/workflows/ingest.md`](workflows/ingest.md). That's the
  future agent interface too.

### Phase 4 - Eval harness ✅ landed (fixture set growing)
- `eval/fixtures/` - hand-labeled subset of generated corpus with
  per-step expected outputs (PARA class, Quest pick, filename, dest).
- `runner.py` matrix: `(model, temperature, prompt_version) x fixture`.
  Models run **sequentially** with explicit Ollama unload between
  them (local memory constraint; hosted inference is the future
  parallelization escape hatch).
- `judges.py`: exact-match for class/dest, normalized-match for
  filename, soft-match (Jaccard or LLM-judge as fallback) for Quest
  pick when multiple are defensible.
- `report.py`: markdown summary + per-fixture trace links.
- Eval runs live under `eval/runs/<timestamp>/`.
- See [`docs/eval.md`](eval.md). Landed with ~7 starter fixtures;
  grow toward ~30 before declaring Phase 4 done.

### Phase 5 - Translate remaining skills ✅

**First slice landed** (shared-infra lift + `pqn-validate`):

- Lifted `frontmatter.py` and `vault_quests.py` (now `vault/quests.py`)
  out of `workflows/ingest_inbox/` into a shared
  `src/para_quest_notes/vault/` package. Other workflows can import
  these without reaching into a sibling workflow.
- Added `adapter/cli.py` with a shared `build_base_parser()` so
  `--vault`, `--config`, `--format` semantics stay consistent across
  every `pqn-*` CLI. LLM workflows opt into `--model` via
  `add_llm_args()`.
- `pqn-validate` ships with three checks (`filename_uniqueness`,
  `frontmatter_yaml`, `backmatter_yaml`) mirroring the legacy
  `validate-note-integrity` SKILL. Read-only, no LLM. JSON contract
  in [`docs/workflows/validate.md`](workflows/validate.md).
- Library entry points: `validate_vault`, `validate_paths`,
  `check_basename_available` in
  `para_quest_notes.workflows.validate.api`.
- `pqn-ingest`'s `propose_filename` step now delegates collision
  detection to `check_basename_available` — single source of truth.

**Remaining slices.** Each is independently shippable; re-plan when
the previous one lands. Frontmatter is now the canonical metadata
location (see "Open questions" — decided 2026-05-12), so write-path
slices below all emit frontmatter and migrate any backmatter they
encounter on touch.

#### Slice 2 — `pqn-create` (shipped, no-LLM)

Shipped as a no-LLM workflow on branch `phase5-create`. The user
supplies type + title + supports up front, so no `resolve_quest`
step was needed. Good forcing function for the `dump_frontmatter()`
extraction and for confirming the per-slice branch flow.

- Lands `workflows/create/` + `pqn-create` console script + per-step
  tests + `docs/workflows/create.md` JSON contract.
- Steps as built: `validate_inputs` (Rule 1 + title regex + wikilink
  format), `compute_destination`, `check_collision` (delegates to
  `validate.api.check_basename_available`), `compose_note`
  (canonical frontmatter via shared `dump_frontmatter()` + body
  skeleton per type), `write_note` (`--apply`-gated atomic write,
  refuses to overwrite, TOCTOU re-check), `validate_after` (scoped
  to the new file).
- Default dry-run, like `pqn-ingest`.
- **Shared-infra landed:** `vault/frontmatter.py` now exports
  `canonical_frontmatter()` and `dump_frontmatter()`; `pqn-ingest`'s
  `apply_move` step routes its frontmatter merge through the same
  helpers, so writers stay in lockstep.
- **Deferred to a later slice (no consumer yet):**
  - LLM `resolve_quest` step for `pqn-create` — defer until a real
    user hits the "I don't know which Quest" case.
  - Moving `pick_quest.txt` to a shared prompts location — defer
    until a second workflow needs it (shared infra without a second
    consumer is speculation).
  - Flipping the eval harness's `EVALUABLE_STEPS` to per-workflow
    scoping — defer until a non-ingest workflow adds its first
    fixture.
- Out of scope: Capability index notes (escalate and stop — see
  "Open questions"), Daily notes (slice 4), modifying any existing
  file, auto-linking the new note from a Quest landing page.
- Known limitation: Areas without tasks must still pass `--supports`
  in v0.1; documented in `docs/workflows/create.md`.

#### Slice 3 — `pqn-archive` (shipped, Projects only, no-LLM)

Shipped as a no-LLM workflow on branch `phase5-archive`. Fence-aware
task rewriting, atomic write-then-remove move, legacy-backmatter
migration. Areas/Resources escalate as planned.

- Lands `workflows/archive/` + `pqn-archive` console script + per-step
  tests + `docs/workflows/archive.md` JSON contract.
- Steps as built: `resolve_target` (path-or-basename lookup under
  `projects/` only), `verify_project` (frontmatter + tail-backmatter
  read, requires `type: project`), `scan_open_tasks` (fence-aware
  candidate list), `decide_task_action` (escalation gate; opt-in via
  `--cancel-open-tasks`), `prepare_outcome` (require `--outcome "..."`
  when the body has no `## Outcome` heading; LLM drafting deferred),
  `compose_archive` (canonical frontmatter merge, block-id-aware task
  cancellation `[ ]`/`[/]` → `[-] … ❌ <today>`, Outcome append,
  destination = mirror sub-path under `archive/`), `write_and_move`
  (`--apply`-gated atomic write then `unlink` source; refuses
  overwrite), `validate_after` (scoped to new path).
- Default dry-run; `--apply` to write.
- **Shared-infra landed:** added `vault.frontmatter.split_note()` for
  reading legacy notes with deprecated tail backmatter. Frontmatter
  is canonical on write; tail backmatter is migrated and dropped.
- **Deferred to a later slice (no consumer yet):**
  - LLM Outcome generation for archive notes. This was the first
    prose-output prompt in the codebase, so Slice 3 punted it until
    there was active user demand.
- **Known limitation flagged in docs:** v0.1 escalates when an open
  task carries Obsidian Tasks scheduling emoji (📅 ⏳ 🛫 🔁 ✅ ❌)
  rather than silently rewriting around them.

#### Slice 4 — `pqn-daily` (shipped, filing-only, no-LLM)

Shipped as a no-LLM workflow. Files one date-shaped note
(`YYYY-MM-DD.md`) into `resources/daily_notes/YYYY/MM/`.
Idempotent re-run on an already-filed note is a no-op success
(cron-safe). Authoring (creating today's empty daily note from
scratch) is deferred — see "Post-v1 candidates" below.

- Lands `workflows/daily/` + `pqn-daily` console script + per-step
  tests + `docs/workflows/daily.md` JSON contract.
- Steps as built: `resolve_target` (basename search scoped to vault
  root + `inbox/` + `resources/daily_notes/`; explicit paths accepted
  anywhere), `detect_shape` (regex + real-calendar-date check, so
  `2026-02-31.md` is rejected here, not later), `inspect_parent`
  (escalates when source lives under `projects/`, `areas/`,
  `archive/`, or any other `resources/<...>/` subtree), `compute_destination`
  (sets `already_at_destination` when source already at canonical
  path), `check_collision` (uses `validate.api.check_basename_available`
  with `ignore_path=source` so source doesn't collide with itself;
  skipped on idempotent re-run), `compose_note` (preserves user
  frontmatter as-is — daily notes don't get canonical PARA
  frontmatter injected since they inherit Quest context from
  contents per the spec; migrates legacy tail backmatter on touch;
  prepends `# YYYY-MM-DD` H1 if absent), `move_file` (`--apply`-gated
  atomic write+unlink; in-place rewrite when already at destination
  but content changed), `validate_after` (scoped to new path).
- Default dry-run; `--apply` to write.
- **Shared-infra reuse:** no new shared helpers needed — the
  `ignore_path` parameter on `check_basename_available` already
  existed (added during slice 1 for `pqn-ingest`'s self-rename case).
- **Out of scope:** authoring (`--today` / `--date` to create empty
  daily notes; tracked under "Post-v1 candidates" below), bulk
  migration of legacy daily notes, task roundup sections.

#### Workflow conventions for all remaining slices

Each slice ships: workflow + CLI entry point + per-step fixtures +
documented JSON contract + (where it pays off) ingest/eval
integration. Branch naming: one `phase5-<workflow>` branch per
slice, merged to `main` as it lands; never more than two active
branches.

### Phase 5.5 - LLM polish + contributor onboarding (post-slice-4, pre-v0.1) ✅

Slices 2, 3, and 4 all shipped no-LLM to keep scope tight. This phase
was originally scoped as "fold the deferred LLM capabilities back in
before Phase 6's release polish." A planning conversation during the
slice-4 → 5.5 handoff reshaped it: the original 5.5b ("LLM
`resolve_quest` inside `pqn-create`") doesn't pay off, because
`pqn-create` only has `title` + `type` to work with — far too thin a
signal for an LLM Quest classifier to beat fuzzy string matching.
The richer signal (note body) already exists in `pqn-ingest`'s
`pick_quest`. So 5.5b is reshaped as a no-LLM inbox fallback, 5.5a
loses its second consumer and is deferred, and a contributor
onboarding doc (5.5e) is folded in.

One sub-slice per item; each can land on its own
`phase5.5-<thing>` branch and ship independently. Never more than
two open at once (mirrors phase 5).

- **5.5a — Shared prompts location *(deferred)*.** Original
  justification was "both `pqn-create` and `pqn-ingest` load
  `pick_quest`." With 5.5b reshaped (below), that second consumer
  disappears. Slice 2's deferral rationale still applies: shared
  infra without a second consumer is speculation. Defer until a
  real second consumer appears.
- [x] **5.5b — `pqn-create` inbox fallback (no LLM).** Shipped.
  `--supports` is optional. When omitted for a `project` or `area`,
  `pqn-create` files the note at `inbox/<basename>.md`, preserves the
  user-chosen `type:` frontmatter, and records the fallback in the
  plan. Canonical destinations remain unchanged when `--supports` is
  present; resources stay canonical. Compatibility landed with the
  slice: `pqn-ingest:classify_para` now honors pre-set `type:`
  frontmatter and skips the LLM call, while `pqn-validate` already
  tolerated inbox project notes without `supports:` because it only
  checks YAML syntax and basename collisions.
- [x] **5.5c — `pqn-archive --generate-outcome` (LLM, prose).** Shipped
  after review reshaped the UX from preview-then-commit to
  generate-on-apply. Adapter work landed: `OllamaClient` now has a
  clean raw-text path (no JSON parsing), FakeLLM can queue prose by
  prompt id, and the archive workflow/eval fixture set use the same
  prompt. Dry-run with `--generate-outcome` is cheap and model-free:
  the plan records `outcome_action = "will_generate"` and does not call
  the LLM. `--generate-outcome --apply` calls the model, appends
  `## Outcome` on success, echoes the prose, and returns
  `plan.outcome_action = "generated"` + `plan.outcome_text`. Empty or
  `INSUFFICIENT_CONTEXT` responses still escalate and abort the write.
- [x] **5.5d — Per-workflow eval scoping.** Flip the eval harness's
  `EVALUABLE_STEPS` from a global constant to per-workflow
  registry. With 5.5b no-LLM, the only new LLM step to evaluate is
  `pqn-archive:generate_outcome` (added by 5.5c). Pick the simplest
  judge for prose that gives signal (responds-at-all baseline plus
  e.g. Jaccard word overlap, or LLM-as-judge) and document the
  tradeoff in `docs/eval.md`. Continue growing the `pqn-ingest`
  fixture set toward the ~30 target from Phase 4.
- [x] **5.5e — `docs/CONTRIBUTING.md`.** Focused contributor onboarding (not
  encyclopedic): dev setup (`uv sync`), lint/format/types/test
  commands, the `phase<N>-<thing>` branch flow, how to add an eval
  fixture, `pqn-eval --fake` vs real-model usage, how to read a
  `report.md`. Pointer to `AGENTS.md` and this PLAN.md. Lives at
  `docs/CONTRIBUTING.md` (moved from repo root during phase 6).

### Phase 6 - Polish and release ✅ done at v0.1.0
- [x] 6a — Repo cleanup: stripped `at-home` references, moved
  `CONTRIBUTING.md` → `docs/CONTRIBUTING.md`, renumbered phases,
  synced roadmap (PR #11).
- [x] 6c — README quickstart end-to-end against `samples/vault`,
  walking all five workflows in order (PR #12).
- [x] 6b — Model recommendations section in `docs/eval.md`
  driven by a real `pqn-eval` run (PR #13).
- [x] 6d — `docs/headless.md` covering cron examples, exit codes,
  JSONL trace, vault discovery, "what not to cron" (PR #14).
- [x] 6e — Install instructions via
  `uv tool install git+...@v0.1` (PyPI deferred); full README
  audit alongside (PR #15).
- [x] 6f — Version bump to `0.1.0`, classifier flipped to
  `3 - Alpha`, [`docs/RELEASING.md`](RELEASING.md) authored; tag
  `v0.1.0` cut from the merge commit.

### Phase 7 - Grow eval fixtures
- Grow the `pqn-ingest` fixture set toward the ~30 target originally
  scoped under Phase 4.
- Revisit the `pqn-archive:generate_outcome` judge (5.5d carryover);
  currently using `granite4.1:30b` as a stopgap.
- Add fixtures for any workflow that gains LLM steps post-v0.1.

### Phase 8 (deferred / future) - Agent integration
- Author SKILL.md wrappers that tell an agent to call the CLIs with
  `--format json` and surface the structured result. Agent never
  sees note bodies.
- Optionally, expose a small Python API (`from para_quest_notes
  import ingest_inbox`) for agents that prefer in-process calls.
- Out of scope for v1; revisit once the CLIs have stabilized and
  there's a real second user (other than the author) asking for it.

### Post-v1 candidates (v0.2 and beyond)

Not promised for v0.1. Listed here so we don't lose them and don't
let them creep into the v1 release.

- **`pqn-daily` authoring mode.** A `--today` / `--date 2026-05-12`
  flag (no positional `target`) that creates the empty daily note
  in place at `resources/daily_notes/YYYY/MM/YYYY-MM-DD.md` if it
  doesn't exist. Open design choices: where the H1-only template
  lives (likely just the H1 and a blank body in v0.1), whether to
  seed any frontmatter (the spec says daily notes don't carry
  frontmatter — leaning "no"), whether to pre-populate routine
  tasks from Areas (see "Task roundup" below — same data source).
  Why not in v1: filing-mode usage will tell us what shape the
  authored note should have. Better as an additive flag on a
  stable filing CLI than a rushed inclusion.

- **`--file` richer input.** Extend `--file` on `pqn-ingest` (and any
  other workflow that gains it) to accept: a directory (process all
  `.md` files it contains), a glob pattern (process all matching
  files), or `-` (read the file list from stdin, one path per line).
  Repeatable as today - mix and match sources in one invocation.
  - **Open design choices:** does a directory walk recurse into
    subdirectories or only collect top-level `.md` files? And how do
    we dedupe and order when sources overlap (e.g. a path passed
    directly and also matched by a glob, or nested under a directory
    arg)? Pick once the feature gets scheduled, not before.

- **Task roundup in daily note.** A step on top of `pqn-daily` that
  scans the active vault (`areas/`, `projects/`) for tasks with
  scheduled/due metadata and writes a roundup section into today's
  daily note (overdue, due today, scheduled this week). Idempotent
  re-run (replace, don't append). Zero new dependencies; mirrors what
  Obsidian Tasks-style queries provide without requiring the plugin.
  - **Open design choice:** which task syntax to parse? Obsidian
    Tasks emoji (`📅 2026-05-15`), Dataview inline fields
    (`[due:: 2026-05-15]`), plain Markdown checkboxes, or all three.
    One-way door — pick after `pqn-daily` ships its bare-bones
    version so we have a feel for the data.
  - Why not in v1: v0.1's pitch is "PARA+Quest hygiene, locally."
    Task scheduling is adjacent, not core. Better as an additive
    step on a stable `pqn-daily` than as a rushed inclusion.

## Key risks and mitigations

- **Local models hallucinate Quest assignments.** Mitigated by
  per-step JSON-mode + schema validation + escalation when confidence
  is low or output doesn't validate.
- **Prompt drift across models.** Mitigated by prompt-version pinning
  and the eval matrix.
- **Synthetic corpus doesn't match real messiness.** Mitigated by
  iterating: generator gets new "shapes" whenever a real note
  surprises us. Add a hand-curated edge-case fixture set later if
  needed.
- **Adapter accidentally reinvents LangChain.** Hard cap on adapter
  size (target: <500 LOC). If it grows past that, revisit framework
  choice with real data.
- **Ollama model availability churn.** Pin exact tags in a
  `models.yaml`; eval reports name the exact tag used.
- **Models silently return empty strings under `format="json"`.**
  Observed in Phase 1 smoke testing: a trivial `'Reply with {"ok": true}'`
  prompt produced valid JSON from some models and an empty response from
  others. Eval harness (Phase 4) should include a cheap "did the model
  return *any* parseable JSON?" judge as the first gate, before scoring
  semantic correctness. Worth a per-model "responds at all" baseline.

## Out of scope (for v1)

- Multi-agent orchestration / planner agents.
- Vector indexing of the vault.
- Web UI.
- Routine/recurring task generator (separate concern in
  `docs/notes-system.md`).

## Open questions to revisit during implementation

- **Frontmatter vs. backmatter — consolidate to one?** **Decided
  2026-05-12 (during Phase 5 slice 1 → slice 2 handoff): frontmatter
  is canonical.** Backmatter (a trailing fenced YAML block) is
  tolerated on read for legacy notes and migrated to frontmatter on
  touch by write-path workflows (`pqn-ingest --apply` today;
  `pqn-create` and `pqn-archive` will follow; a `pqn-validate --fix`
  mode is a post-v1 candidate). Reflected in
  `docs/notes-system.md` ("Metadata schema (frontmatter)" section).
  Rationale: every workflow having two read/write paths doubles the
  validation surface, prompts have to teach the distinction, and the
  wider Markdown ecosystem (Obsidian Properties, Dataview, pandoc,
  SSGs) all assume frontmatter — so backmatter is invisible to those
  tools. The author confirmed they don't want both in one note.
- **Should `archive/` really be left out of wikilink rewrites?**
  Today `pqn-ingest` excludes `archive/` from rewrite scope on the
  theory that archived notes should preserve the historical name
  they linked to. Author isn't fully convinced. Wait until it bites
  someone (a confused archived link surfaced during a real lookup),
  then revisit with a concrete case rather than re-debating in the
  abstract.
- **Project name.** Provisionally `para-quest-notes` (CLI prefix
  `pqn-`). Picked early so Phase 0 had something to type; not
  permanently locked. If a better name emerges, renaming touches:
  GitHub repo, `pyproject.toml` (`name`, `[project.scripts]`),
  `src/<pkg>/` directory, `~/.config/<name>/` config path,
  `PARA_QUEST_VAULT` env var, and `pqn-*` CLI prefix. All mechanical.
- Prompt template language: Jinja2 vs stdlib `string.Template` -
  decide when writing the first prompt.
- Should escalation payloads ever round-trip back into a workflow
  ("user picked option B, resume from step N"), or always restart the
  file from scratch? Lean toward restart for v1 simplicity.
- How big a fixture set is "enough" for meaningful eval signal? Start
  ~30, grow as needed.
