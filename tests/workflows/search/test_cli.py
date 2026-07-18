"""Tests for the ``pqn-search`` CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from para_quest_notes.workflows.search.cli import main


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
        "---\ntype: project\nsupports:\n- '[[Health]]'\n---\nTraining plan for the race.\n",
    )
    write(
        tmp_path / "resources" / "Running Shoes.md",
        "---\ntype: resource\n---\nNotes on running shoes.\n",
    )
    return tmp_path


def test_text_is_default(vault: Path, capsys):
    code = main(["--vault", str(vault), "running"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith('# Search results for "running"')
    assert "resources/Running Shoes.md" in out


def test_json_output_is_parseable(vault: Path, capsys):
    code = main(["--vault", str(vault), "--format", "json", "running"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["query"] == ["running"]
    assert data["summary"]["results"] >= 1
    top = data["results"][0]
    assert set(top) >= {"path", "type", "supports", "match_context", "incoming_links"}
    assert set(top["match_context"]) == {"where", "snippet"}


def test_type_filter_flag(vault: Path, capsys):
    code = main(["--vault", str(vault), "--type", "resource", "--format", "json", "running"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert {r["type"] for r in data["results"]} == {"resource"}
    assert data["scope"]["types"] == ["resource"]


def test_content_only_scope(vault: Path, capsys):
    code = main(["--vault", str(vault), "--content", "--format", "json", "training"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert [r["path"] for r in data["results"]] == ["projects/Run a 5K.md"]
    assert data["scope"]["title"] is False
    assert data["scope"]["content"] is True


def test_limit_flag(vault: Path, capsys):
    code = main(["--vault", str(vault), "--limit", "1", "--format", "json", "running"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert len(data["results"]) == 1


def test_snippet_radius_flag(vault: Path, capsys):
    code = main(["--vault", str(vault), "--snippet-radius", "0", "--format", "json", "running"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["scope"]["snippet_radius"] == 0
    assert all(r["match_context"]["snippet"] == "" for r in data["results"])


def test_snippet_radius_zero_omits_snippet_in_text(vault: Path, capsys):
    code = main(["--vault", str(vault), "--snippet-radius", "0", "running"])
    out = capsys.readouterr().out
    assert code == 0
    # No quoted snippet, but the match location is still shown.
    assert '"' not in out.split("\n", 2)[-1]
    assert "- title" in out


def test_snippet_radius_negative_flag_rejected(vault: Path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--vault", str(vault), "--snippet-radius", "-3", "running"])
    assert exc.value.code == 2
    assert "must be >= 0" in capsys.readouterr().err


def test_snippet_radius_from_config(vault: Path, tmp_path: Path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text("workflows:\n  search:\n    snippet_radius: 0\n", encoding="utf-8")
    code = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(config),
            "--format",
            "json",
            "running",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out)["scope"]["snippet_radius"] == 0


def test_snippet_radius_flag_overrides_config(vault: Path, tmp_path: Path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text("workflows:\n  search:\n    snippet_radius: 0\n", encoding="utf-8")
    code = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(config),
            "--snippet-radius",
            "50",
            "--format",
            "json",
            "running",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out)["scope"]["snippet_radius"] == 50


def test_bad_config_snippet_radius_exits_two(vault: Path, tmp_path: Path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text("workflows:\n  search:\n    snippet_radius: -5\n", encoding="utf-8")
    code = main(["--vault", str(vault), "--config", str(config), "running"])
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err


def test_no_matches_exits_zero(vault: Path, capsys):
    code = main(["--vault", str(vault), "zzzznotfound"])
    out = capsys.readouterr().out
    assert code == 0
    assert "No matches." in out


def test_missing_vault_exits_two(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    empty = tmp_path / "nowhere"
    code = main(["--vault", str(empty), "running"])
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err
