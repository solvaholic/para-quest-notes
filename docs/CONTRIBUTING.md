# Contributing

Start here, then branch out:

- [`AGENTS.md`](../AGENTS.md) for repo orientation, layout, and conventions
- [`docs/PLAN.md`](PLAN.md) for the current roadmap and slice status
- [`docs/eval.md`](eval.md) for the full eval-harness design

## Dev setup

Python `>=3.11`. This repo uses `uv`.

```bash
uv sync
```

That installs the project plus the dev tooling used below. CI currently uses `uv sync --all-extras --dev`; today there are no extras, so `uv sync` is enough for local contributor setup.

## Daily commands

These match the checks in CI:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

## Branch flow

Phase work lands one sub-slice at a time:

- branch names: `phase<N>-<thing>` (e.g., `phase6-cleanup`)
- base from `main`
- merge back to `main` as each slice lands
- keep no more than two open slice branches at once

Recent commits also use this trailer:

```text
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

## Adding an eval fixture

Put fixtures under [`eval/fixtures/`](../eval/fixtures/). Start with [`eval/fixtures/README.md`](../eval/fixtures/README.md), then copy a nearby example like:

- [`eval/fixtures/clean_project_5k.yaml`](../eval/fixtures/clean_project_5k.yaml)
- [`eval/fixtures/ambiguous_quest_family_hike.yaml`](../eval/fixtures/ambiguous_quest_family_hike.yaml)

At a glance, each fixture YAML gives the runner:

- `id` - unique fixture name
- `title` - note title shown to the workflow
- `body` - note body markdown
- `frontmatter` - optional seeded metadata
- `quest_catalog` - the Quest options available to `pick_quest`
- `expected` - per-step goldens to judge against

For `expected.pick_quest.acceptable`, treat each listed quest list as an exact acceptable set. A run passes if the picked quest set matches one of those sets exactly. Use `skipped: true` when the workflow should not call that step.

Do not duplicate the full schema here. See [`docs/eval.md`](eval.md) and [`eval/fixtures/README.md`](../eval/fixtures/README.md).

## Running `pqn-eval`

CI-safe smoke test, no Ollama required:

```bash
uv run pqn-eval --fake
```

Real local-model run:

```bash
uv run pqn-eval --models granite4.1:30b,qwen3:30b
```

Important local constraint: models run sequentially, not in parallel. The harness unloads each model with `keep_alive=0` before loading the next because local Ollama runs are memory-bound. See [`docs/eval.md`](eval.md) for the full runner behavior and CLI options.

## Reading a report

Each run writes under `eval/runs/<timestamp>/`, including `report.md`, `rows.csv`, `summary.json`, and `trace.jsonl`.

`report.md` is the fast read:

- **Responds-at-all baseline** - did the model emit parseable JSON for JSON steps, or any non-empty text for prose steps?
- **Performance** - LLM-cell count plus total, mean, p50, p95, and max latency
- **Accuracy by step** - pass/total per model and step, plus overall
- **Per-step detail** - one row per fixture/model cell with verdict and reason

In the detail tables, `Verdict` is pass or fail for that judged step, and `Reason` is the judge explanation or an escalation/error note.

For the full meaning of each artifact and judge, see [`docs/eval.md`](eval.md).

## Where to look next

- [`AGENTS.md`](../AGENTS.md) - orientation, package layout, commands, current phase summary
- [`docs/PLAN.md`](PLAN.md) - authoritative roadmap and current slice definitions
