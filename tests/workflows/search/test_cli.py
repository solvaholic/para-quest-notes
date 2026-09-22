"""Tests for the ``pqn-search`` CLI entry point."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from para_quest_notes.workflows.search.cli import build_parser, main


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    write(
        tmp_path / "areas" / "Health.md",
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Health]]'\n---\n# Health\n",
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


def test_help_documents_link_mode():
    help_text = build_parser().format_help()
    assert "--links" in help_text
    assert "direct" in help_text.lower()


def test_exactly_one_search_mode_is_required(vault: Path, capsys):
    with pytest.raises(SystemExit) as missing:
        main(["--vault", str(vault)])
    assert missing.value.code == 2
    assert "exactly one" in capsys.readouterr().err

    with pytest.raises(SystemExit) as combined:
        main(["--vault", str(vault), "--links", "Running Shoes", "running"])
    assert combined.value.code == 2
    assert "cannot be combined" in capsys.readouterr().err


@pytest.mark.parametrize("keyword_flag", ["--title", "--content", "--snippet-radius"])
def test_keyword_only_flags_are_rejected_in_link_mode(vault: Path, capsys, keyword_flag: str):
    argv = ["--vault", str(vault), "--links", "Running Shoes", keyword_flag]
    if keyword_flag == "--snippet-radius":
        argv.append("10")

    with pytest.raises(SystemExit) as exc:
        main(argv)

    assert exc.value.code == 2
    assert "keyword mode" in capsys.readouterr().err


def test_link_mode_json_and_text_output(vault: Path, capsys):
    write(
        vault / "projects" / "Use Shoes.md",
        "---\ntype: project\n---\n[[Running Shoes]]\n",
    )

    code = main(["--vault", str(vault), "--links", "running shoes", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["mode"] == "links"
    assert data["target"]["path"] == "resources/Running Shoes.md"
    assert [item["path"] for item in data["results"]] == ["projects/Use Shoes.md"]

    code = main(["--vault", str(vault), "--links", "Running Shoes"])
    out = capsys.readouterr().out
    assert code == 0
    assert '# Link neighbors for "resources/Running Shoes.md"' in out
    assert "incoming: outgoing 0, incoming 1" in out


def test_link_mode_target_error_exits_two(vault: Path, capsys):
    code = main(["--vault", str(vault), "--links", "Missing"])
    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_json_output_is_parseable(vault: Path, capsys):
    code = main(["--vault", str(vault), "--format", "json", "running"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["query"] == ["running"]
    assert data["summary"]["results"] >= 1
    top = data["results"][0]
    assert set(top) >= {"path", "type", "supports", "match_context", "matches", "incoming_links"}
    assert set(top["match_context"]) == {"where", "snippet"}
    assert top["matches"] == [{"keyword": "running", "where": "title", "snippet": "Running Shoes"}]


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


def test_negative_limit_is_rejected(vault: Path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--vault", str(vault), "--links", "Running Shoes", "--limit", "-1"])
    assert exc.value.code == 2
    assert "must be >= 0" in capsys.readouterr().err


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


def test_json_sample_vault_copy_keeps_match_context_and_matches_in_sync(tmp_path: Path, capsys):
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    copied_vault = tmp_path / "vault"
    shutil.copytree(sample, copied_vault)
    write(
        copied_vault / "projects" / "Sample Evidence Title.md",
        "---\ntype: project\n---\nSample evidence body appears here.\n",
    )

    code = main(["--vault", str(copied_vault), "--format", "json", "title", "body"])
    data = json.loads(capsys.readouterr().out)

    assert code == 0
    hit = next(
        result
        for result in data["results"]
        if result["path"] == "projects/Sample Evidence Title.md"
    )
    assert hit["match_context"] == {"where": "title", "snippet": "Sample Evidence Title"}
    assert hit["matches"] == [
        {"keyword": "title", "where": "title", "snippet": "Sample Evidence Title"},
        {"keyword": "body", "where": "body", "snippet": "Sample evidence body appears here."},
    ]


def test_link_mode_sample_vault_copy_text_and_json_smoke(tmp_path: Path, capsys):
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    copied_vault = tmp_path / "vault"
    shutil.copytree(sample, copied_vault)
    write(
        copied_vault / "projects" / "Link Smoke Neighbor.md",
        "---\ntype: project\nsupports:\n- '[[Health]]'\n---\n[[Workshop]] [[Workshop]]\n",
    )

    code = main(["--vault", str(copied_vault), "--links", "Workshop"])
    text = capsys.readouterr().out
    assert code == 0
    assert "projects/Link Smoke Neighbor.md" in text
    assert "incoming 2" in text
    assert "Nonexistent Us" in text

    code = main(
        [
            "--vault",
            str(copied_vault),
            "--links",
            "areas/Workshop.md",
            "--type",
            "project",
            "--quest",
            "Health",
            "--format",
            "json",
        ]
    )
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["mode"] == "links"
    assert data["target"]["path"] == "areas/Workshop.md"
    assert [item["path"] for item in data["results"]] == ["projects/Link Smoke Neighbor.md"]
    assert data["unresolved_links"] == [
        {
            "target": "Nonexistent Us",
            "occurrences": 1,
            "reason": "missing",
            "candidates": [],
        }
    ]


def test_missing_vault_exits_two(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    empty = tmp_path / "nowhere"
    code = main(["--vault", str(empty), "running"])
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err
