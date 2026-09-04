"""Tests for the ``pqn-config`` CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from para_quest_notes.workflows.config.cli import main


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "areas").mkdir()
    (tmp_path / "projects").mkdir()
    return tmp_path


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the developer's real vault env var out of the resolution ladder.
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)


def _absent_config(tmp_path: Path) -> str:
    return str(tmp_path / "no-such-config.yaml")


def test_full_json_has_all_sections(vault: Path, tmp_path: Path, capsys) -> None:
    code = main(["--vault", str(vault), "--config", _absent_config(tmp_path), "--format", "json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) == {"vault", "models", "ollama", "daily", "tasks", "templates", "paths"}
    assert data["vault"]["resolved"] is True
    assert data["vault"]["source"] == "flag"


def test_section_json_isolates_one_section(vault: Path, tmp_path: Path, capsys) -> None:
    code = main(
        [
            "--vault",
            str(vault),
            "--config",
            _absent_config(tmp_path),
            "--section",
            "models",
            "--format",
            "json",
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) == {"models"}
    assert data["models"]["default_model"]["source"] == "default"


def test_text_output_shows_inline_provenance(vault: Path, tmp_path: Path, capsys) -> None:
    code = main(["--vault", str(vault), "--config", _absent_config(tmp_path), "--format", "text"])
    assert code == 0
    out = capsys.readouterr().out
    assert "# pqn-config" in out
    assert "(source: flag)" in out
    assert "default_model:" in out


def test_text_section_prints_only_that_section(vault: Path, tmp_path: Path, capsys) -> None:
    code = main(
        [
            "--vault",
            str(vault),
            "--config",
            _absent_config(tmp_path),
            "--section",
            "vault",
            "--format",
            "text",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "## vault" in out
    assert "## models" not in out


def test_unresolved_vault_still_exits_zero(tmp_path: Path, monkeypatch, capsys) -> None:
    # cwd inside an empty dir so the walk-up finds no vault.
    monkeypatch.chdir(tmp_path)
    code = main(["--config", _absent_config(tmp_path), "--format", "json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["vault"]["resolved"] is False
    assert data["vault"]["error"]


def test_malformed_config_exits_two(tmp_path: Path, capsys) -> None:
    bad = tmp_path / "config.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    code = main(["--config", str(bad)])
    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_config_provenance_end_to_end(vault: Path, tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("ollama:\n  default_model: from-file:1\n", encoding="utf-8")
    code = main(
        ["--vault", str(vault), "--config", str(cfg), "--section", "models", "--format", "json"]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["models"]["default_model"] == {"value": "from-file:1", "source": "config"}


def test_tasks_section_reports_honored_date_fields(vault: Path, tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "workflows:\n  tasks:\n    date_fields: [start, scheduled]\n",
        encoding="utf-8",
    )

    code = main(
        ["--vault", str(vault), "--config", str(cfg), "--section", "tasks", "--format", "json"]
    )

    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {
        "tasks": {
            "date_fields": {
                "value": ["start", "scheduled"],
                "source": "config",
                "honored": True,
            }
        }
    }


def test_daily_section_reports_settings_and_provenance(vault: Path, tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "workflows:\n  daily:\n    create_missing: true\n    editor: [code, --reuse-window]\n",
        encoding="utf-8",
    )

    code = main(
        ["--vault", str(vault), "--config", str(cfg), "--section", "daily", "--format", "json"]
    )

    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {
        "daily": {
            "create_missing": {"value": True, "source": "config"},
            "open_existing": {"value": False, "source": "default"},
            "editor": {"value": ["code", "--reuse-window"], "source": "config"},
        }
    }
