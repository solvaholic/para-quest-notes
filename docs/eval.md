# Eval harness

Per-step golden-judging eval for `pqn-ingest` (Phase 4 in
[`PLAN.md`](PLAN.md)). Maintainer tool — no `pqn-eval` console
script; invoke via `python -m para_quest_notes.eval`.

## What it does

For each fixture × model × step, the runner:

1. Builds a minimal `StepContext` with a pre-seeded scratchpad
   (synthetic `ScanResult`, vault Quest catalog, upstream
   decisions).
2. Calls the **same `Step` class the production workflow uses** —
   so the prompts, JSON schema validation, and escalation logic
   under test are exactly what ships.
3. Captures the step's output (or escalation/error), runs the
   appropriate judge, and records a row.
4. Writes `report.md`, `rows.csv`, `summary.json`, and
   `trace.jsonl` under `eval/runs/<timestamp>/` (gitignored).

## Steps evaluated

- `classify_para` (LLM) — exact match on `type`.
- `pick_quest` (LLM) — set equality against any acceptable
  set; `skipped: true` for resources.
- `propose_filename` (LLM) — canonical-form match
  (lowercase, alphanumeric-only, single-spaced).
- `plan_destination` (pure) — exact path string.

Plus a `responds`-at-all baseline per LLM cell: did the model emit
parseable JSON at all? Cheap gate per the PLAN.md risk note about
empty `format=json` replies.

## Local-only constraint

Local Ollama is memory-bound. The runner processes models **strictly
sequentially** and asks Ollama to unload each model
(`keep_alive=0`) before loading the next. Don't try to parallelize
this loop locally — it will thrash or OOM. Hosted inference
(HuggingFace, Azure, OpenRouter) could parallelize later.

## Usage

```bash
# CI-safe: FakeLLM returns each fixture's expected JSON. Verifies
# the harness end-to-end without touching Ollama.
uv run python -m para_quest_notes.eval --fake

# Real Ollama, one or more models, run sequentially.
uv run python -m para_quest_notes.eval --models granite4.1:30b,qwen3:30b

# Subset of steps.
uv run python -m para_quest_notes.eval --fake --steps classify_para,pick_quest

# Custom fixture set or output dir.
uv run python -m para_quest_notes.eval --fake \
  --fixtures path/to/fixtures \
  --out /tmp/eval-run
```

Exit code: `0` if every cell passed, `1` otherwise, `2` if no
fixtures were found.

## Fixtures

Hand-curated YAML under `eval/fixtures/`. See
[`eval/fixtures/README.md`](../eval/fixtures/README.md) for the
schema and conventions.

Phase 4 lands with ~7 starter fixtures. Plan target is ~30 before
Phase 4 is "done" — grow as eval signal demands.

## Future work

- LLM-as-judge fallback for ambiguous Quest picks (PLAN.md mentions
  this as a "soft-match" option). Set-equality with acceptable-sets
  is enough for a starter signal.
- Hosted inference + parallel matrix execution.
- Auto-running `--fake` eval in CI as a smoke test.
