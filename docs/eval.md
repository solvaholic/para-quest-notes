# Eval harness

Per-step golden-judging eval for registered workflows. Today that means
`pqn-ingest` (Phase 4 in [`PLAN.md`](PLAN.md)); Phase 5.5d refactors the
harness so new workflows can register their own steps without editing
`runner.py`. Exposed as the `pqn-eval` console script so users can
compare model choices on their own; also runnable via
`python -m para_quest_notes.eval`.

## What it does

For each fixture x model x step, the runner:

1. Loads the fixture through that workflow's registered fixture loader.
2. Builds the workflow-specific eval context / scratchpad.
3. Calls the same `Step` class the production workflow uses - so the
   prompts, schema validation, and escalation logic under test are
   exactly what ships.
4. Captures the step's output (or escalation/error), runs the
   workflow-registered judge, and records a row.
5. Writes `report.md`, `rows.csv`, `summary.json`, and `trace.jsonl`
   under `eval/runs/<timestamp>/` (gitignored).

## Registry shape

The registry lives in `src/para_quest_notes/eval/registry.py`.
Each workflow registers:

- a `WorkflowEval` entry with a fixture loader, and
- one `EvaluableStep` per step to score.

Each `EvaluableStep` carries the things `runner.py` needs to stay
workflow-agnostic:

- `workflow` + `name`
- `step_factory(model)`
- `context_builder(fixture)`
- `judge(actual, fixture)`
- `has_expectation(fixture)`
- `uses_llm`
- optional fake-response and responds-baseline hooks

`pqn-ingest` wires its registrations in
`src/para_quest_notes/workflows/ingest_inbox/eval.py`.

## Steps evaluated

### `ingest`

- `classify_para` (LLM) - exact match on `type`.
- `pick_quest` (LLM) - set equality against any acceptable set;
  `skipped: true` for resources.
- `propose_filename` (LLM) - canonical-form match
  (lowercase, alphanumeric-only, single-spaced).
- `plan_destination` (pure) - exact path string.

Plus a `responds`-at-all baseline per LLM cell: for JSON steps, did the
model emit parseable JSON at all; for prose steps, did it emit any
non-empty text? Cheap gate per the PLAN.md risk note about empty model
replies.

### `archive`

- `generate_outcome` (LLM prose) - keyword-coverage judge, with optional
  reference-text Jaccard when a fixture wants extra anchoring. This is
  intentionally lighter than an LLM-as-judge pass: it is cheap,
  deterministic, and CI-safe, but it will miss good paraphrases when the
  expected keywords are too narrow.

## Local-only constraint

Local Ollama is memory-bound. The runner processes models strictly
sequentially and asks Ollama to unload each model (`keep_alive=0`) before
loading the next. Don't try to parallelize this loop locally - it will
thrash or OOM. Hosted inference (HuggingFace, Azure, OpenRouter) could
parallelize later.

## Usage

```bash
# CI-safe: FakeLLM returns each fixture's expected JSON. Verifies
# the harness end-to-end without touching Ollama.
pqn-eval --fake

# Real Ollama, one or more models, run sequentially.
pqn-eval --models granite4.1:30b,qwen3:30b

# Subset of steps. Bare names still imply the default workflow: ingest.
pqn-eval --fake --steps classify_para,pick_quest

# Explicit workflow-qualified steps also work.
pqn-eval --fake --steps ingest:classify_para

# Custom fixture set or output dir.
pqn-eval --fake \
  --fixtures path/to/fixtures \
  --out eval/runs/manual-smoke
```

(All examples also work as `uv run python -m para_quest_notes.eval ...`
when the package isn't installed.)

Exit code: `0` if every cell passed, `1` otherwise, `2` if no fixtures
were found.

## Step selection and fixture scoping

- If `--steps` is omitted, the runner evaluates every registered step
  for each fixture's workflow.
- `--steps classify_para` still means `ingest:classify_para`.
- `--steps workflow:step` opts into a specific workflow explicitly.
- Fixtures may declare `workflow: <name>`. If omitted, they default to
  `ingest`, so the existing fixture set stays unchanged.
- A workflow can introduce a different fixture schema later by swapping
  in its own loader hook; `load_fixtures()` now dispatches per fixture.

## Report sections

`report.md` contains:

- **Responds-at-all baseline** - % of LLM cells that emitted parseable JSON
  (JSON steps) or any non-empty text (prose steps).
- **Performance** - per model: LLM-cell count, total wall, mean / p50 /
  p95 / max latency. Computed from per-cell `latency_ms` (LLM steps only;
  pure-code steps excluded). Use this to spot the
  "gemma3:27b takes 13m, granite4.1:30b takes 1.5m" gap at a glance.
- **Accuracy by step** - pass/total per (model, step) plus an Overall
  column.
- **Per-step detail** - every cell with verdict and reason.

## Model recommendations

These come from a real `pqn-eval` matrix captured 2026-05-16 against
six locally-runnable models over 10 fixtures (7 `pqn-ingest` +
3 `pqn-archive`). Eval-run artifacts are local-only (see the
`.gitignore`); re-run with:

```bash
uv run pqn-eval --models \
    granite4.1:30b,granite4.1:3b,gemma4:26b,gemma4:e4b,nemotron-3-nano:30b,nemotron-3-nano:4b
```

### TL;DR

- **Default: `granite4.1:30b`.** Best overall (27/31, 87%), 100%
  responds-at-all, ~5.6s mean LLM-cell latency. Matches the
  documented CLI default. Needs ~18 GB RAM.
- **Smallest that still works: `granite4.1:3b`.** 23/31 (74%),
  100% responds-at-all, ~1.0s mean LLM-cell latency (~5× faster
  than the 30b). Strong on `classify_para`, `propose_filename`,
  and `plan_destination`; weaker on `pick_quest` and
  `archive:generate_outcome`. Reasonable for dry-runs, fast
  iteration on classification flows, or laptops that can't hold
  18 GB.
- **Not recommended right now:** `gemma4:26b` (latency variance —
  one 31s call, one timeout in the captured run), `gemma4:e4b`
  (weak on `propose_filename` and `archive:generate_outcome`),
  and both `nemotron-3-nano:*` (14% responds-at-all — most LLM
  cells return empty under `format="json"`).

### What to use when

| You want… | Pick |
|---|---|
| Best accuracy, you have the RAM | `granite4.1:30b` (default) |
| Fast iteration / small footprint | `granite4.1:3b` |
| LLM-prose `archive:generate_outcome` quality | `granite4.1:30b` (currently the 5.5d judge stopgap) |

### Per-step shape from the captured run

| Step | Best model in this run | Notes |
|---|---|---|
| `classify_para` | `gemma4:e4b` (7/7), `granite4.1:30b` (6/7) | Small models do fine here once they respond |
| `pick_quest` | `granite4.1:30b` (6/7) | Other models struggle with "Quest name (type)" format and over-pick `Health (main)` |
| `propose_filename` | `granite4.1:3b` (7/7), `granite4.1:30b` (6/7) | Smallest model is actually best |
| `plan_destination` | All models 7/7 | Pure-code step in practice; LLM judgment rarely needed |
| `archive:generate_outcome` | `granite4.1:30b`, `gemma4:26b` (2/3) | Prose judge is keyword-coverage; brittle, see Phase 7 carryover |

### Caveats

- Tiny fixture set (10 fixtures). These rankings will shift as the
  fixture set grows toward ~30 (Phase 7 carryover).
- Latency numbers were captured on one machine, sequentially
  (per the local-only constraint above). Your `mean` will differ.
- The `archive:generate_outcome` judge is keyword-coverage and
  known-brittle. `granite4.1:30b` looks best here partly because
  it's the model the prose evaluator was tuned against; treat the
  prose numbers as a smoke signal, not a ranking. See "Future
  work" below.



Hand-curated YAML under `eval/fixtures/`. See
[`eval/fixtures/README.md`](../eval/fixtures/README.md) for the schema
and conventions.

Phase 4 landed with ~10 fixtures (7 `pqn-ingest` + 3 `pqn-archive`).
The plan target is ~30 before the fixture set is considered "done";
growing it is **Phase 7**.

## Adding a new workflow to eval

1. Add a workflow-specific fixture parser / loader.
2. Register a `WorkflowEval` and one `EvaluableStep` per scored step.
3. Give each step a judge and fake-response hook so `pqn-eval --fake`
   keeps covering the harness end-to-end.
4. Add fixtures for that workflow. Existing ingest fixtures do not need
   to change unless you want to mark them with `workflow: ingest`
   explicitly.

## Future work

- Tune the `generate_outcome` prose judge if keyword coverage proves too
  brittle on real-model runs. LLM-as-judge is the heavier fallback if we
  need semantic scoring later.
- LLM-as-judge fallback for ambiguous Quest picks (PLAN.md mentions this
  as a "soft-match" option). Set-equality with acceptable-sets is enough
  for a starter signal.
- Hosted inference + parallel matrix execution.
- Auto-running `--fake` eval in CI as a smoke test.
