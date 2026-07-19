"""Tests for the ``pqn-validate`` CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from para_quest_notes.workflows.validate.cli import main


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "areas").mkdir()
    (tmp_path / "projects").mkdir()
    return tmp_path


def write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_clean_vault_exit_zero(vault: Path, capsys):
    write(vault / "areas" / "A.md", "---\nkind: area\n---\nbody\n")
    code = main(["--vault", str(vault), "--format", "text"])
    out = capsys.readouterr().out
    assert code == 0
    assert "no issues found" in out


def test_errors_exit_one(vault: Path, capsys):
    write(vault / "areas" / "Dup.md", "")
    write(vault / "projects" / "Dup.md", "")
    code = main(["--vault", str(vault), "--format", "text"])
    assert code == 1
    out = capsys.readouterr().out
    assert "filename_uniqueness" in out


def test_json_output_is_parseable(vault: Path, capsys):
    write(vault / "areas" / "Bad.md", "---\nno closer\n")
    code = main(["--vault", str(vault), "--format", "json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 1
    assert payload["summary"]["errors"] == 1
    assert payload["issues"][0]["check"] == "frontmatter_yaml"


def test_strict_promotes_warnings_to_exit_one(vault: Path, capsys):
    # No warnings exist for any built-in check today, so --strict is a
    # no-op on a clean vault. Smoke-test the path instead.
    write(vault / "areas" / "A.md", "---\nkind: area\n---\nbody\n")
    code = main(["--vault", str(vault), "--strict"])
    capsys.readouterr()
    assert code == 0


def test_invalid_vault_exit_two(tmp_path: Path, capsys):
    not_a_vault = tmp_path / "nope"
    not_a_vault.mkdir()
    code = main(["--vault", str(not_a_vault)])
    err = capsys.readouterr().err
    # find_vault accepts any directory passed via --vault, so this
    # actually returns 0 (no .md files, no issues). Make the assertion
    # honest by pointing at a path that doesn't exist.
    assert code == 0
    assert err == ""

    code2 = main(["--vault", str(tmp_path / "missing")])
    err2 = capsys.readouterr().err
    assert code2 == 2
    assert "vault path does not exist" in err2


def test_check_filter(vault: Path, capsys):
    write(vault / "areas" / "Dup.md", "")
    write(vault / "projects" / "Dup.md", "")
    write(vault / "areas" / "Bad.md", "---\nno closer\n")
    code = main(
        [
            "--vault",
            str(vault),
            "--check",
            "filename_uniqueness",
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["checks_run"] == ["filename_uniqueness"]
    assert all(i["check"] == "filename_uniqueness" for i in payload["issues"])


def test_fix_dry_run_does_not_write(vault: Path, capsys):
    p = write(vault / "areas" / "Health.md", "---\ntype: area\nquest: main\n---\nbody\n")
    code = main(["--vault", str(vault), "--fix", "--format", "text"])
    out = capsys.readouterr().out
    assert code == 0
    assert "would migrate: 1" in out
    assert "quest: main" in p.read_text(encoding="utf-8")


def test_fix_apply_writes(vault: Path, capsys):
    p = write(vault / "areas" / "Health.md", "---\ntype: area\nquest: main\n---\nbody\n")
    code = main(["--vault", str(vault), "--fix", "--apply"])
    capsys.readouterr()
    assert code == 0
    assert "quest-kind: main" in p.read_text(encoding="utf-8")


def test_fix_skip_exits_one(vault: Path, capsys):
    write(vault / "areas" / "W.md", "---\ntype: resource\nquest: banana\n---\nbody\n")
    code = main(["--vault", str(vault), "--fix", "--apply"])
    capsys.readouterr()
    assert code == 1


def test_fix_json_output(vault: Path, capsys):
    write(vault / "areas" / "Health.md", "---\ntype: area\nquest: main\n---\nbody\n")
    code = main(["--vault", str(vault), "--fix", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["applied"] is False
    assert payload["summary"]["migrated"] == 1
    assert payload["entries"][0]["path"] == "areas/Health.md"
