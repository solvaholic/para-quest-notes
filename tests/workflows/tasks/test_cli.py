"""Tests for the pqn-tasks CLI (text + json rendering, exit codes)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    assert data["types"] is None
    assert data["quest"] is None


def test_type_filter_repeats_and_composes_with_quest(tmp_path: Path, capsys):
    v = _vault(tmp_path)
    _write(v / "areas" / "Garden Area.md", f"# Garden Area\n- [ ] Weed beds 📅 {_PAST}\n")
    _write(v / "resources" / "Garden Notes.md", f"# Garden Notes\n- [ ] Review notes 📅 {_PAST}\n")
    _write(v / "inbox" / "Garden Capture.md", f"# Garden Capture\n- [ ] Sort capture 📅 {_PAST}\n")

    rc = main(
        [
            "--vault",
            str(v),
            "--overdue",
            "--type",
            "area",
            "--type",
            "project",
            "--quest",
            "health",
            "--format",
            "json",
        ]
    )

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["types"] == ["area", "project"]
    assert data["quest"] == "health"
    assert [task["description"] for task in data["tasks"]] == ["Pay taxes"]


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


def test_date_fields_config_filters_when_flag_omitted(tmp_path: Path, capsys):
    v = tmp_path / "mix"
    _write(v / "areas" / "Health.md", "---\ntype: area\nquest-kind: main\n---\n# Health\n")
    _write(v / "projects" / "D.md", f"# D\n- [ ] Deadline task 📅 {_PAST}\n")
    _write(v / "projects" / "S.md", f"# S\n- [ ] Do-date task ⏳ {_PAST}\n")
    config = tmp_path / "config.yaml"
    _write(config, "workflows:\n  tasks:\n    date_fields: [scheduled]\n")

    rc = main(["--vault", str(v), "--overdue", "--config", str(config), "--format", "json"])

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["date_fields"] == ["scheduled"]
    assert [task["description"] for task in data["tasks"]] == ["Do-date task"]


def test_date_field_flag_overrides_config(tmp_path: Path, capsys):
    config = tmp_path / "config.yaml"
    _write(config, "workflows:\n  tasks:\n    date_fields: [scheduled]\n")

    rc = main(
        [
            "--vault",
            str(_vault(tmp_path)),
            "--overdue",
            "--config",
            str(config),
            "--date-field",
            "due",
            "--format",
            "json",
        ]
    )

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["date_fields"] == ["due"]
    assert [task["description"] for task in data["tasks"]] == ["Pay taxes"]


@pytest.mark.parametrize(
    "date_fields",
    [
        "scheduled",
        "null",
        "[]",
        "[scheduled, deadline]",
        "[scheduled, 3]",
    ],
)
def test_invalid_date_fields_config_exits_two(tmp_path: Path, capsys, date_fields: str):
    config = tmp_path / "config.yaml"
    _write(config, f"workflows:\n  tasks:\n    date_fields: {date_fields}\n")

    rc = main(["--vault", str(_vault(tmp_path)), "--config", str(config)])

    assert rc == 2
    assert "workflows.tasks.date_fields" in capsys.readouterr().err


def test_null_tasks_config_exits_two(tmp_path: Path, capsys):
    config = tmp_path / "config.yaml"
    _write(config, "workflows:\n  tasks: null\n")

    rc = main(["--vault", str(_vault(tmp_path)), "--config", str(config)])

    assert rc == 2
    assert "workflows.tasks must be a mapping" in capsys.readouterr().err


def test_date_field_flag_does_not_mask_invalid_config(tmp_path: Path, capsys):
    config = tmp_path / "config.yaml"
    _write(config, "workflows:\n  tasks:\n    date_fields: [deadline]\n")

    rc = main(
        [
            "--vault",
            str(_vault(tmp_path)),
            "--config",
            str(config),
            "--date-field",
            "due",
        ]
    )

    assert rc == 2
    assert "workflows.tasks.date_fields" in capsys.readouterr().err


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
