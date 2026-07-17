"""Tests for the ``pqn-quests`` CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from para_quest_notes.workflows.quests.cli import main


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    write(
        tmp_path / "areas" / "Health.md",
        "---\ntype: area\nquest: main\nsupports:\n- '[[Health]]'\n---\n# Health\n",
    )
    write(
        tmp_path / "projects" / "Run a 5K.md",
        "---\ntype: project\nsupports:\n- '[[Health]]'\n---\n# 5K\n",
    )
    return tmp_path


def test_markdown_is_default_and_redirectable(vault: Path, capsys):
    code = main(["--vault", str(vault)])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("# Quest index")
    assert "## [[Health]]" in out
    assert "- [[Run a 5K]] (project)" in out


def test_json_output_is_parseable(vault: Path, capsys):
    code = main(["--vault", str(vault), "--format", "json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["summary"]["quests"] == 1
    assert {n["title"] for n in data["notes"]} == {"Health", "Run a 5K"}


def test_type_filter_flag(vault: Path, capsys):
    code = main(["--vault", str(vault), "--type", "project", "--format", "json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert {n["type"] for n in data["notes"]} == {"project"}
    assert data["scope"]["types"] == ["project"]


def test_missing_vault_exits_two(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    empty = tmp_path / "nowhere"
    code = main(["--vault", str(empty)])
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err
