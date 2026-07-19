"""Tests for the pqn-tasks CLI (text + json rendering, exit codes)."""

from __future__ import annotations

import json
from pathlib import Path

from para_quest_notes.workflows.tasks.cli import main

# A due date far in the past is always overdue regardless of the real
# "today" the CLI reads, so these tests stay deterministic.
_PAST = "2000-01-01"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    _write(
        v / "areas" / "Health.md",
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Health]]'\n---\n# Health\n",
    )
    _write(
        v / "projects" / "Garden.md",
        "---\ntype: project\nquest-kind: none\nsupports:\n- '[[Health]]'\n---\n"
        f"# Garden\n\n- [ ] Pay taxes 📅 {_PAST}\n",
    )
    return v


def test_text_output_is_markdown_bullets(tmp_path: Path, capsys):
    rc = main(["--vault", str(_vault(tmp_path)), "--overdue"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "## Overdue (1)" in out
    assert "- [[Garden]] Pay taxes (due 2000-01-01)" in out
    # Plain bullet, not a live checkbox.
    assert "- [ ]" not in out


def test_json_output_contract(tmp_path: Path, capsys):
    rc = main(["--vault", str(_vault(tmp_path)), "--overdue", "--format", "json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["summary"]["overdue"] == 1
    assert data["tasks"][0]["description"] == "Pay taxes"
    assert data["tasks"][0]["quests"] == ["Health"]


def test_group_by_quest_headers(tmp_path: Path, capsys):
    rc = main(["--vault", str(_vault(tmp_path)), "--overdue", "--group-by", "quest"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "## Health (1)" in out
    assert "overdue)" in out


def test_scheduled_source_labeled_in_output(tmp_path: Path, capsys):
    v = tmp_path / "sched"
    _write(v / "areas" / "Health.md", "---\ntype: area\nquest-kind: main\n---\n# Health\n")
    _write(v / "projects" / "P.md", f"# P\n- [ ] Water plants ⏳ {_PAST}\n")
    rc = main(["--vault", str(v), "--overdue"])
    out = capsys.readouterr().out
    assert rc == 0
    assert f"- [[P]] Water plants (scheduled {_PAST})" in out


def test_date_field_flag_filters(tmp_path: Path, capsys):
    v = tmp_path / "mix"
    _write(v / "areas" / "Health.md", "---\ntype: area\nquest-kind: main\n---\n# Health\n")
    _write(v / "projects" / "D.md", f"# D\n- [ ] Deadline task 📅 {_PAST}\n")
    _write(v / "projects" / "S.md", f"# S\n- [ ] Do-date task ⏳ {_PAST}\n")
    rc = main(["--vault", str(v), "--overdue", "--date-field", "scheduled"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Do-date task" in out
    assert "Deadline task" not in out


def test_empty_vault_reports_nothing(tmp_path: Path, capsys):
    v = tmp_path / "empty"
    _write(v / "projects" / "P.md", "# P\nno tasks here\n")
    rc = main(["--vault", str(v)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No open tasks due." in out


def test_missing_vault_errors(tmp_path: Path, capsys):
    rc = main(["--vault", str(tmp_path / "does-not-exist")])
    assert rc == 2
    assert "error:" in capsys.readouterr().err
