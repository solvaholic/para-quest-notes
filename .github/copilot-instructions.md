# Copilot cloud agent instructions

Read [`AGENTS.md`](../AGENTS.md) first. It covers what the repo is,
conventions (Python `>=3.11`, `uv`, `pqn-` CLI prefix, ruff + mypy +
pytest), and where files live.

Then read whichever of these your task touches:

- [`docs/PLAN.md`](../docs/PLAN.md) — current phase status, decisions,
  and what's deferred.
- [`docs/workflows/<name>.md`](../docs/workflows/) — per-workflow spec
  and behavior contract. Update this if you change a workflow's
  observable behavior.
- [`docs/CONTRIBUTING.md`](../docs/CONTRIBUTING.md) — dev setup, daily
  commands, branch flow, eval-fixture conventions.

## Verify before declaring done

Run all of these before declaring done. CI runs every step except
`pqn-eval --fake` (an extra local/agent check that uses the in-repo
`FakeLLM`):

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run pqn-eval --fake
```

`pqn-eval --fake` uses the in-repo `FakeLLM` — no Ollama needed, no
network calls. If a step output's shape or schema changes, the fake
response in [`src/para_quest_notes/workflows/<name>/eval.py`](../src/para_quest_notes/workflows/)
needs the same shape.

## Behavior-changing changes: smoke against the sample vault

`pytest` and `pqn-eval --fake` together are necessary but not
sufficient for workflow changes. They miss production-output details
that aren't asserted on (e.g. report fields like
`wikilinks_rewritten`).

For changes to any `pqn-*` workflow, run the workflow against a copy
of [`samples/vault/`](../samples/vault/) with `--apply` and confirm
the JSON output's invariants hold. The existing pattern is in
`tests/workflows/ingest_inbox/test_pipeline.py::test_apply_mode_moves_files`
— mirror it.

## Commit attribution

Every commit (including merge commits when reasonable) should carry:

```text
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

## Out of scope by default

Don't expand scope without asking:

- Don't add new linters, build tools, or test frameworks.
- Don't change the PARA + Quest spec in `docs/notes-system.md`.
- Don't touch phases marked deferred in `docs/PLAN.md` — those have
  open design questions.
- Don't add network-bound tests; the eval harness must work without
  Ollama (use `FakeLLM`).
