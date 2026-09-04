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
- **Main-quest `--supports` inference (decided 2026-07-04, #41):**
  `pqn-create --type area --quest main` without `--supports` is valid.
  A main quest area note supports itself, so `pqn-create` infers
  `--supports "[[<title>]]"` and files to `areas/` (canonical path).
  The inbox fallback still applies to projects/areas with a non-main
  quest when `--supports` is omitted.
- **The CLI + `--format json` contract is the integration seam
  (decided 2026-08-08, #114):** external front-ends integrate by
  invoking `pqn-*` CLIs and parsing `--format json`, not by importing
  the Python packages, and not through a cache, index, or long-running
  daemon. The `api.py` modules (`search`, `quests`, `validate`) stay a
  convenience for in-tree callers and other workflows; they are not a
  supported external API. Rationale: the CLI + JSON contract is the
  part most likely to survive a re-implementation in another language
  (see "Open questions"), so binding front-ends to it keeps them
  working across one. It also makes those front-ends the first serious
  non-human consumers of the JSON output, which is the pressure that
  finds gaps in it. Accepted cost: repeated invocations re-walk the
  vault, so interactive callers see ~160-320 ms per command on a
  ~1,700-note vault. We instrument rather than optimize (#114) and
  revisit the plumbing only as part of a re-implementation, or if
  measured p50 latency crosses the point where the wait is a felt tax.

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

#### Slice 2 — `pqn-create` (shipped; deterministic by default, opt-in LLM merge)

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
- **Deferred (status updated post-v0.3):**
  - Deterministic `resolve_quest` step landed (path-based inference
    from sub-path/filename). LLM fallback when deterministic
    resolution misses — defer until stdin body signal makes it
    useful.
  - Moving `pick_quest.txt` to a shared prompts location — defer
    until a second workflow needs it (shared infra without a second
    consumer is speculation).
  - Flipping the eval harness's `EVALUABLE_STEPS` to per-workflow
    scoping — defer until a non-ingest workflow adds its first
    fixture.
- Out of scope: Capability index notes (escalate and stop — see
  "Open questions"), Daily notes (slice 4), modifying any existing
  file, auto-linking the new note from a Quest landing page.
- Known limitation (relaxed in v0.3, #41): `--quest main` areas infer
  `--supports "[[<title>]]"` automatically. Other projects/areas
  without `--supports` still fall back to inbox.

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

#### Slice 4 — `pqn-daily` (shipped, selection + filing + authoring + opening, no-LLM)

Shipped as a no-LLM workflow. Selects today or an explicit date, files one date-shaped note (`YYYY-MM-DD.md`) into `resources/daily_notes/YYYY/MM/`, can create an exact H1-only note when missing, and can open a real resolved note through configured editor argv. Safe defaults keep creation and opening disabled, `--apply` remains the only write consent, and idempotent re-runs remain cron-safe.

- Lands `workflows/daily/` + `pqn-daily` console script + per-step
  tests + `docs/workflows/daily.md` JSON contract.
- Steps as built: `resolve_target` (basename search scoped to vault
  root + `inbox/` + `resources/daily_notes/`; explicit paths accepted
  anywhere; a missing bare date can enter the opt-in authoring branch),
  `detect_shape` (regex + real-calendar-date check, so
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
  prepends `# YYYY-MM-DD` H1 if absent; emits exact H1-only content for
  creation), `move_file` (`--apply`-gated atomic create or write+unlink;
  in-place rewrite when already at destination but content changed),
  `validate_after` (scoped to new path).
- Default dry-run; `--apply` to write.
- **Shared-infra reuse:** the `ignore_path` parameter on
  `check_basename_available` already
  existed (added during slice 1 for `pqn-ingest`'s self-rename case).
- **Wave 5 delivered (#124):** optional positional target; bare/`--today`/`--date` selection; independently configurable and positively/negatively overridable missing-note creation and editor opening; additive JSON/text results; effective-config provenance. Missing-note authoring is exact H1-only content and remains `--apply` gated.
- **Out of scope:** templates, frontmatter, routine tasks, task roundup sections, bulk migration, implicit apply, and OS editor discovery.

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

- **`pqn-daily` authoring mode - delivered in Wave 5 (#124).** Bare/`--today`/`--date` selection, explicit/configured missing-note creation, and configured editor opening landed as additive behavior. Authored notes are exactly an H1 plus a blank line, with no frontmatter, template, or routine tasks. Writes still require `--apply`.

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

- **Whole-note templates (#75) - delivered in Wave 6.** `pqn-create`
  templates can include frontmatter that merges under generated values
  (generated wins on conflict; templates provide supplemental keys like
  `status: draft`). The implementation reuses `split_note()` and
  `canonical_frontmatter()` so legacy backmatter tolerance, malformed
  metadata handling, migration, and key ordering match other write paths.
  `resources/templates/` remains excluded from `pqn-validate` because
  templates aren't PARA notes.

- **Stdin placeholder rendering (#110) - delivered in Wave 6.** Non-empty `pqn-create --body-stdin` bodies pass through the same deterministic renderer and finalized variable mapping as template bodies. Stdin keeps priority over explicit and configured templates without loading their body or supplemental frontmatter; frontmatter-looking stdin remains body text. Empty stdin keeps its template-or-skeleton fallback, and no LLM or new flag is involved.

- **Template + stdin merge (#49) - delivered in Wave 6.** `pqn-create --merge-template` is the explicit, generate-on-apply local-LLM branch. Dry-run performs static template/input/destination validation and reports routing as deferred without calling Ollama. Apply routes stable stdin block IDs only to stable existing-heading IDs or `unsorted`, validates complete one-to-one accounting, reconstructs the note from original rendered text, and still aborts before any write on unusable output. Template frontmatter remains deterministic, and ordinary stdin priority is unchanged without the flag.

- **Task roundup in daily note.** The *reporting* half shipped as
  the standalone `pqn-tasks` reporter (#83, v0.5; see
  [`docs/workflows/tasks.md`](workflows/tasks.md)) — read-only,
  scans the whole vault except `archive/` for open tasks carrying
  Obsidian Tasks due dates and buckets them overdue / due today /
  upcoming. What remains deferred is the `pqn-daily` *integration*: a
  step that writes (and idempotently replaces) a roundup section into
  today's daily note. `pqn-tasks` emits plain `-` bullets (not
  `- [ ]`) precisely so a pasted roundup never re-parses as live
  tasks.
  - **Open design choice — resolved:** parse Obsidian Tasks emoji
    (`📅 2026-05-15`) as the canonical syntax in v1. Dataview inline
    fields (`[due:: 2026-05-15]`) and plain checkboxes are deferred to
    a future contributor.
  - Why the reporter came first: reporting and filing are separable,
    and a reporter is useful to cron and agents on its own. Task
    scheduling is adjacent to v0.1's "PARA+Quest hygiene, locally"
    pitch, so it lands as an additive read-only tool rather than a
    rushed inclusion.

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
- **Re-implementation in another language?** Genuinely open. The
  intent has been to get features mostly steady in Python, then
  consider a rewrite - Go is the leading candidate, but TypeScript or
  a Python re-architecture are live options. Nothing is committed.
  What this open question *does* decide today is what we don't build
  in the meantime: no cache, index, or daemon, because the dominant
  cost in the read-only workflows is the vault walk (~70-90% of a
  `pqn-search` invocation; ~111 ms for ~1,700 notes), and a concurrent
  walk in a compiled language plausibly erases most of it. Building
  Python-side state now risks solving a problem the rewrite deletes
  for free. Revisit when features settle, or when instrumentation
  (#114) shows the current latency actually hurts. Related: the CLI +
  `--format json` seam decision above exists precisely so front-ends
  survive whatever this resolves to.
- Prompt template language: Jinja2 vs stdlib `string.Template` -
  decide when writing the first prompt.
- Should escalation payloads ever round-trip back into a workflow
  ("user picked option B, resume from step N"), or always restart the
  file from scratch? Lean toward restart for v1 simplicity.
- How big a fixture set is "enough" for meaningful eval signal? Start
  ~30, grow as needed.
