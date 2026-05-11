"""Per-step eval harness for ``pqn-ingest``.

See ``docs/PLAN.md`` Phase 4. Runs each LLM step against hand-labeled
fixtures across a model matrix and emits a markdown report.

Maintainer tool — no console-script entry point. Invoke via
``python -m para_quest_notes.eval``.
"""
