# Plan: para-quest-notes

> Working plan for the `para-quest-notes` re-architecture. Lives in the
> repo so any agent session (or human) starting in the repo dir has the
> full design context. Update at large milestones; keep
> `docs/ROADMAP.md` as the human-facing snapshot if/when it diverges.

## Problem

The predecessor (`solvaholic/at-home`) relied on cloud-hosted Copilot
agents loading skills (`SKILL.md`) and reasoning over the user's notes.
Two issues:

1. Privacy: notes get sent to whoever hosts the model.
2. Cloud dependency: management of personal markdown shouldn't require
   network access to a third party.

The agent's reasoning (Quest alignment, escalation when rules don't fit)
is the keeper. The "send everything to a cloud LLM" part is not.

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

Built in a **new public, parallel repo** (clean slate, generic - no
assumptions about anyone's note history). Existing `at-home` keeps
working unchanged during the experiment.

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
│   │   ├── escalation.py           # raise EscalateToUser pattern
│   │   ├── config.py               # XDG config load + defaults
│   │   ├── vault.py                # vault path discovery
│   │   └── io.py                   # YAML, JSON output
│   ├── workflows/
│   │   └── ingest_inbox/           # pilot
│   │       ├── __init__.py
│   │       ├── cli.py              # entry-point: pqn-ingest
│   │       ├── pipeline.py
│   │       ├── steps/
│   │       │   ├── detect_shape.py        # gen1/gen2/gen3, pure code
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
│   └── eval/
│       ├── runner.py
│       ├── judges.py
│       ├── report.py
│       └── fixtures/               # golden inputs + expected step outputs
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
  walk-up-from-cwd looking for a marker (e.g. `notes-system.md` or
  configured marker) → error with a helpful message.
- Run trace logger (JSONL) under
  `~/.local/state/para-quest-notes/runs/`.
- Fake LLM for unit tests (records calls, returns canned responses).

### Phase 2 - Synthetic corpus / sample vault
- `corpus/seeds.yaml` with **generic** Quests/Areas (e.g. Health,
  Family, Craft) - no personal data, suitable for a public repo.
- `generate.py`: produces N notes across PARA types, gen1/2/3 shapes,
  daily notes, messy inbox cases (missing frontmatter, ambiguous
  Quests, attachments). Reproducible (seed-controlled).
- Output doubles as: (a) test corpus for eval, (b) demo vault for
  README quickstart, (c) docs material.

### Phase 3 - Pilot workflow: `ingest_inbox`
- Translate the existing `ingest-inbox-notes` SKILL.md into discrete
  steps (see steps/ in sketch above). Each LLM step has its own
  prompt and JSON output schema.
- CLI entry point `pqn-ingest`:
  `pqn-ingest [--vault PATH] [--apply] [--model ...] [--format json|text]`.
- Default is dry-run; `--apply` performs moves + rename rewrites.
- Escalation payload includes: file, step that escalated, reason,
  candidate options for the user.
- Document the JSON output contract (this is the future agent
  interface too).

### Phase 4 - Eval harness
- `eval/fixtures/` - hand-labeled subset of generated corpus with
  per-step expected outputs (PARA class, Quest pick, filename, dest).
- `runner.py` matrix: `(model, temperature, prompt_version) x fixture`.
- `judges.py`: exact-match for class/dest, normalized-match for
  filename, soft-match (Jaccard or LLM-judge as fallback) for Quest
  pick when multiple are defensible.
- `report.py`: markdown summary + per-fixture trace links.
- Eval runs live under `eval/runs/<timestamp>/`.

### Phase 5 - Translate remaining skills
Once pilot + eval are green, translate in this order (cheapest first):
1. `validate-note-integrity` (no LLM, pure port) → `pqn-validate`.
2. `create-note` (light LLM use) → `pqn-create`.
3. `archive-note` (LLM for Outcome summarization) → `pqn-archive`.
4. `daily-note-ingest` (mostly script, narrow LLM tiebreak) →
   `pqn-daily`.

Each gets the same: workflow + CLI entry point + per-step fixtures +
documented JSON contract.

### Phase 6 - Polish and release
- README quickstart that runs end-to-end against the bundled sample
  vault (no LLM-free fallback path required, but document model
  recommendations from eval results).
- `solvaholic/at-home`: deprecation/migration notes pointing here.
- Document running workflows headlessly (cron examples).
- Tag a `v0.1` release; `pipx`/`uv tool install` instructions.

### Phase 7 (deferred / future) - Agent integration
- Author SKILL.md wrappers that tell an agent to call the CLIs with
  `--format json` and surface the structured result. Agent never
  sees note bodies.
- Optionally, expose a small Python API (`from para_quest_notes
  import ingest_inbox`) for agents that prefer in-process calls.
- Out of scope for v1; revisit once the CLIs have stabilized and
  there's a real second user (other than the author) asking for it.

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
- Migrating the `at-home` scripts (`quick-capture`, `backup-notes`,
  `setup-notes`) - they keep working in the old repo.
- Routine/recurring task generator (separate concern in
  `docs/notes-system.md`).

## Open questions to revisit during implementation

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
