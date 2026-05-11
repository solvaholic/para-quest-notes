"""Report rendering tests."""

from __future__ import annotations

import time
from pathlib import Path

from para_quest_notes.eval.judges import Verdict
from para_quest_notes.eval.report import render_csv, render_markdown, write_report
from para_quest_notes.eval.runner import CellResult, RunSummary, StepRunResult


def _summary() -> RunSummary:
    now = time.time()
    s = RunSummary(
        started_at=now - 1,
        finished_at=now,
        fixture_count=2,
        models=["model-a", "model-b"],
    )
    s.cells = [
        CellResult(
            model="model-a",
            temperature=0.0,
            fixture_id="fx1",
            step="classify_para",
            run=StepRunResult(
                step="classify_para", output={"type": "project"}, raw_text='{"type":"project"}'
            ),
            verdict=Verdict(step="classify_para", ok=True),
            responds=Verdict(step="responds", ok=True),
        ),
        CellResult(
            model="model-a",
            temperature=0.0,
            fixture_id="fx2",
            step="classify_para",
            run=StepRunResult(
                step="classify_para", output={"type": "area"}, raw_text='{"type":"area"}'
            ),
            verdict=Verdict(
                step="classify_para", ok=False, reason="expected 'project', got 'area'"
            ),
            responds=Verdict(step="responds", ok=True),
        ),
        CellResult(
            model="model-b",
            temperature=0.0,
            fixture_id="fx1",
            step="classify_para",
            run=StepRunResult(step="classify_para", raw_text=""),
            verdict=Verdict(step="classify_para", ok=False, reason="step did not produce output"),
            responds=Verdict(step="responds", ok=False, reason="empty response"),
        ),
    ]
    return s


def test_markdown_includes_models_and_steps() -> None:
    md = render_markdown(_summary())
    assert "model-a" in md and "model-b" in md
    assert "classify_para" in md
    assert "Responds-at-all baseline" in md
    assert "Accuracy by step" in md
    assert "Per-step detail" in md
    # model-a: 1/2; model-b: 0/1 → check at least one accuracy cell renders
    assert "1/2" in md
    assert "0/1" in md


def test_csv_has_header_and_rows() -> None:
    csv_text = render_csv(_summary())
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("model,temperature,fixture_id,step,verdict_ok")
    assert len(lines) == 1 + 3  # header + 3 cells


def test_write_report_creates_files(tmp_path: Path) -> None:
    write_report(_summary(), tmp_path)
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "rows.csv").exists()


def test_markdown_handles_empty_summary() -> None:
    s = RunSummary(started_at=time.time(), finished_at=time.time())
    md = render_markdown(s)
    assert "_No models in run._" in md
    assert "_No cells._" in md
