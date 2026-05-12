# Agent Instructions

Welcome. This file orients AI agents (and humans) starting fresh in
this repo.

## What this repo is

`para-quest-notes` is a set of **local, scripted workflows** for
managing markdown notes organized by **PARA + Quest**, powered by
small LLMs running locally via [Ollama](https://ollama.com/).

Public, MIT-licensed, generic - no personal data. Designed to install
as a CLI (`pipx`/`uv tool install`) and run against any markdown
vault on disk.

## Read these first

In order, before doing any work:

1. **[`docs/PLAN.md`](docs/PLAN.md)** - the working plan. Decisions,
   architecture sketch, phased workstreams, open questions.
   **The current state of "what we're building and why."**
2. **[`docs/notes-system.md`](docs/notes-system.md)** - the PARA +
   Quest spec. Every workflow operates on notes shaped by this spec.
3. **[`docs/configuration.md`](docs/configuration.md)** - the
   tool-config / vault-content split, vault discovery rules.
4. **[`README.md`](README.md)** - the public-facing pitch and
   roadmap.

## Conventions

- **Python:** `>=3.11`. Build backend: hatchling. Dep manager: `uv`.
- **CLI prefix:** `pqn-` for entry-point names (e.g., `pqn-ingest`).
- **Package name:** `para_quest_notes` (under `src/`).
- **Lint/format/types:** ruff (lint + format), mypy (loose). Run
  `uv run ruff check .` / `uv run ruff format .` / `uv run mypy src`.
- **Tests:** `uv run pytest`. CI runs lint + format-check + mypy +
  pytest on Python 3.11/3.12/3.13. **No Ollama in CI** - use the
  fake LLM (Phase 1) for adapter tests.
- **Workflow philosophy:** scripts do the heavy lifting; LLM is used
  only for judgment calls and natural-language summarization.
  Per-step JSON-schema-validated outputs. Escalate to user when rules
  don't fit.

## Where things go

```
para-quest-notes/
├── src/para_quest_notes/      # all production code
│   ├── adapter/               # Phase 1: thin runtime (Ollama, Step, etc.)
│   ├── vault/                 # Phase 5: shared vault helpers
│   │                          #   (frontmatter parser, quest discovery)
│   ├── workflows/<name>/      # one dir per workflow
│   ├── corpus/                # Phase 2: synthetic note generator
│   └── eval/                  # Phase 4: per-step eval harness
├── docs/                      # specs, plan, per-workflow docs
├── tests/                     # pytest, fake LLM only
└── .github/workflows/ci.yml   # lint + types + tests matrix
```

## Phase status

See `docs/PLAN.md` for the full breakdown.

- [x] **Phase 0** - bootstrap (this commit/repo)
- [x] **Phase 1** - thin adapter
- [x] **Phase 2** - synthetic corpus generator (see
  [`docs/corpus.md`](docs/corpus.md), [`samples/vault/`](samples/vault/))
- [x] **Phase 3** - pilot workflow (`pqn-ingest`)
- [ ] **Phase 4** - eval harness ✅ landed (see
  [`docs/eval.md`](docs/eval.md), [`eval/fixtures/`](eval/fixtures/));
  fixture set still small (~7), grow toward ~30 before declaring done
- [ ] **Phase 5** - translate remaining workflows
  - [x] Slice 1: shared-infra lift (`vault/` package,
    `adapter/cli.py` base parser) + `pqn-validate` (no LLM,
    wired into `pqn-ingest` via
    `validate.api.check_basename_available`) + frontmatter locked
    as canonical metadata location (backmatter tolerated on read,
    migrated on touch).
  - [x] Slice 2: `pqn-create` (shipped no-LLM; LLM `resolve_quest`
    and shared `pick_quest.txt` extraction deferred — see
    [`docs/PLAN.md`](docs/PLAN.md))
  - [ ] Slice 3: `pqn-archive` (Projects only in v1; LLM
    `## Outcome` drafting, fence-aware task rewrites).
  - [ ] Slice 4: `pqn-daily` (single-file only; bulk migration
    out of scope).
- [ ] **Phase 6** - polish + v0.1
- [ ] **Phase 7** (deferred) - agent SKILL.md wrappers

## Heritage

The reasoning patterns (PARA + Quest alignment, escalation when
rules don't fit) come from `solvaholic/at-home`, which used
cloud-hosted Copilot agents loading SKILL.md files. This repo
re-implements those patterns as local scripted workflows so notes
never leave the user's machine. See `docs/PLAN.md` "Problem" for
the full motivation.
