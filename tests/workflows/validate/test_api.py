"""Tests for ``validate_vault`` and ``validate_paths`` library entry points."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.workflows.validate.api import validate_paths, validate_vault


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "areas").mkdir()
    (tmp_path / "projects").mkdir()
    return tmp_path


def write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_to_dict_shape(vault: Path):
    write(vault / "areas" / "A.md", "---\nkind: area\n---\nbody\n")
    report = validate_vault(vault)
    d = report.to_dict()
    assert d["vault"] == str(vault)
    assert set(d) >= {"vault", "files_scanned", "checks_run", "summary", "issues"}
    assert d["summary"] == {"total_issues": 0, "errors": 0, "warnings": 0}
    assert sorted(d["checks_run"]) == [
        "backmatter_yaml",
        "filename_uniqueness",
        "frontmatter_yaml",
        "legacy_quest_key",
        "metadata_in_backmatter",
    ]


def test_unknown_check_raises(vault: Path):
    with pytest.raises(ValueError, match="unknown check"):
        validate_vault(vault, checks=["nonsense"])


def test_validate_paths_focus(vault: Path):
    write(vault / "areas" / "Notes.md", "")
    write(vault / "projects" / "Notes.md", "")
    write(vault / "areas" / "Other.md", "---\ntags: [bad: yaml: here\n---\n")
    report = validate_paths(vault, [vault / "areas" / "Other.md"])
    # Filename collision touches a different file; only the YAML error
    # for our focus path should be reported.
    assert all(i.path == "areas/Other.md" for i in report.issues)
    assert any(i.check == "frontmatter_yaml" for i in report.issues)


def test_validate_paths_collision_via_focus_member(vault: Path):
    write(vault / "areas" / "Dup.md", "")
    write(vault / "projects" / "Dup.md", "")
    report = validate_paths(vault, [vault / "areas" / "Dup.md"])
    # Filename uniqueness emits one issue per colliding file. Both fire
    # because the collision involves the focus path.
    rels = sorted(i.path for i in report.issues if i.check == "filename_uniqueness")
    assert rels == ["areas/Dup.md", "projects/Dup.md"]


def test_min_severity_filters(vault: Path):
    write(vault / "areas" / "Bad.md", "---\nno closer\n")
    report = validate_vault(vault, min_severity="error")
    assert len(report.issues) == 1
    report2 = validate_vault(vault, min_severity="warning")
    # No warnings exist; result should be the same set.
    assert len(report2.issues) == 1
