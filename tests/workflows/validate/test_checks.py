"""Tests for individual ``pqn-validate`` checks.

Each test builds a tiny vault on disk (with the ``areas/`` and
``projects/`` marker dirs so it looks like a vault) and asserts that the
right issues fire — and only those.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.workflows.validate.api import validate_paths, validate_vault


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "areas").mkdir()
    (tmp_path / "projects").mkdir()
    (tmp_path / "resources").mkdir()
    return tmp_path


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------- filename_uniqueness ----------


def test_filename_uniqueness_clean(vault: Path):
    write(vault / "areas" / "Health.md", "---\nkind: area\n---\nbody\n")
    write(vault / "projects" / "Roof.md", "---\nkind: project\n---\nbody\n")
    report = validate_vault(vault)
    assert report.issues == []


def test_filename_uniqueness_collision(vault: Path):
    write(vault / "areas" / "Notes.md", "---\nkind: area\n---\n")
    write(vault / "projects" / "Notes.md", "---\nkind: project\n---\n")
    report = validate_vault(vault, checks=["filename_uniqueness"])
    assert len(report.issues) == 2
    rels = sorted(i.path for i in report.issues)
    assert rels == ["areas/Notes.md", "projects/Notes.md"]
    for issue in report.issues:
        assert issue.severity == "error"
        assert issue.detail["basename"] == "Notes.md"
        assert issue.detail["count"] == 2
        assert len(issue.related) == 1


def test_filename_uniqueness_three_way(vault: Path):
    write(vault / "areas" / "Index.md", "")
    write(vault / "projects" / "Index.md", "")
    write(vault / "resources" / "Index.md", "")
    report = validate_vault(vault, checks=["filename_uniqueness"])
    assert len(report.issues) == 3
    for issue in report.issues:
        assert issue.detail["count"] == 3
        assert len(issue.related) == 2


def test_filename_uniqueness_excludes_archive_by_default(vault: Path):
    (vault / "archive").mkdir()
    write(vault / "areas" / "Notes.md", "")
    write(vault / "archive" / "Notes.md", "")
    report = validate_vault(vault, checks=["filename_uniqueness"])
    assert report.issues == []
    report2 = validate_vault(vault, checks=["filename_uniqueness"], include_archive=True)
    assert len(report2.issues) == 2


def test_filename_uniqueness_focus_filters_report(vault: Path):
    write(vault / "areas" / "Notes.md", "")
    write(vault / "projects" / "Notes.md", "")
    write(vault / "resources" / "Other.md", "")
    # Pretend we only care about a separate file; the collision exists
    # but doesn't touch our focus path.
    report = validate_paths(
        vault,
        [vault / "resources" / "Other.md"],
        checks=["filename_uniqueness"],
    )
    assert report.issues == []


def test_inbox_project_without_supports_is_clean(vault: Path):
    write(vault / "inbox" / "Draft.md", "---\ntype: project\nquest-kind: none\n---\nbody\n")
    report = validate_vault(vault)
    assert report.issues == []


# ---------- frontmatter_yaml ----------


def test_frontmatter_yaml_clean(vault: Path):
    write(vault / "areas" / "A.md", "---\nkind: area\ntags: [x, y]\n---\nbody\n")
    report = validate_vault(vault, checks=["frontmatter_yaml"])
    assert report.issues == []


def test_frontmatter_yaml_unterminated(vault: Path):
    write(vault / "areas" / "Bad.md", "---\nkind: area\nno closer here\n")
    report = validate_vault(vault, checks=["frontmatter_yaml"])
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.check == "frontmatter_yaml"
    assert issue.severity == "error"
    assert issue.line == 1
    assert "no closing" in issue.message


def test_frontmatter_yaml_invalid(vault: Path):
    # Tab indentation in a block value is invalid YAML.
    bad = "---\nkind: area\ntags:\n\t- bad\n---\nbody\n"
    write(vault / "areas" / "Bad.md", bad)
    report = validate_vault(vault, checks=["frontmatter_yaml"])
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.check == "frontmatter_yaml"
    assert issue.severity == "error"
    assert "invalid YAML" in issue.message
    assert issue.line is not None and issue.line >= 1


def test_frontmatter_yaml_not_a_mapping(vault: Path):
    write(vault / "areas" / "List.md", "---\n- one\n- two\n---\nbody\n")
    report = validate_vault(vault, checks=["frontmatter_yaml"])
    assert len(report.issues) == 1
    assert "must parse to a mapping" in report.issues[0].message


def test_frontmatter_yaml_no_frontmatter_is_ok(vault: Path):
    write(vault / "areas" / "Plain.md", "Just a body, no frontmatter.\n")
    report = validate_vault(vault, checks=["frontmatter_yaml"])
    assert report.issues == []


def test_frontmatter_yaml_skips_templates(vault: Path):
    bad = "---\nkind: {{kind}}\n---\nbody\n"
    write(vault / "templates" / "T.md", bad)
    write(vault / "Templates" / "U.md", bad)
    report = validate_vault(vault, checks=["frontmatter_yaml"])
    assert report.issues == []


# ---------- backmatter_yaml ----------


def test_backmatter_yaml_clean(vault: Path):
    text = "---\nkind: project\n---\nbody\n---\noutcome: shipped\n---\n"
    write(vault / "projects" / "Done.md", text)
    report = validate_vault(vault, checks=["backmatter_yaml"])
    assert report.issues == []


def test_backmatter_yaml_invalid(vault: Path):
    text = "body line\n---\noutcome:\n\tbad indent\n---\n"
    write(vault / "projects" / "Bad.md", text)
    report = validate_vault(vault, checks=["backmatter_yaml"])
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.check == "backmatter_yaml"
    assert issue.severity == "error"
    assert "invalid YAML" in issue.message


def test_backmatter_absent_is_ok(vault: Path):
    write(vault / "projects" / "P.md", "---\nkind: project\n---\nbody only\n")
    report = validate_vault(vault, checks=["backmatter_yaml"])
    assert report.issues == []


# ---------- metadata_in_backmatter ----------


def test_metadata_in_backmatter_warns(vault: Path):
    text = (
        "# Sustain\n\nBody copy.\n\n---\ntype: area\nquest-kind: main\n"
        "supports:\n- '[[Sustain]]'\n---\n"
    )
    write(vault / "areas" / "Sustain.md", text)
    report = validate_vault(vault, checks=["metadata_in_backmatter"])
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.check == "metadata_in_backmatter"
    assert issue.severity == "warning"
    assert issue.detail["keys"] == ["quest-kind", "supports", "type"]


def test_metadata_in_backmatter_flags_legacy_quest_key(vault: Path):
    """A legacy ``quest:`` classifier in backmatter is still flagged (#98)."""
    text = "# Sustain\n\nBody.\n\n---\ntype: area\nquest: main\n---\n"
    write(vault / "areas" / "Sustain.md", text)
    report = validate_vault(vault, checks=["metadata_in_backmatter"])
    assert len(report.issues) == 1
    assert report.issues[0].detail["keys"] == ["quest", "type"]


def test_metadata_in_backmatter_non_canonical_ignored(vault: Path):
    """Non-canonical keys (e.g. archive's `outcome`) are fine in backmatter."""
    text = "---\ntype: project\n---\nbody\n---\noutcome: shipped\n---\n"
    write(vault / "projects" / "P.md", text)
    report = validate_vault(vault, checks=["metadata_in_backmatter"])
    assert report.issues == []


def test_metadata_in_backmatter_absent_is_ok(vault: Path):
    write(vault / "areas" / "Health.md", "---\ntype: area\nquest-kind: main\n---\nbody\n")
    report = validate_vault(vault, checks=["metadata_in_backmatter"])
    assert report.issues == []


# ---------- legacy_quest_key ----------


def test_legacy_quest_key_flags_frontmatter(vault: Path):
    write(vault / "areas" / "Health.md", "---\ntype: area\nquest: main\n---\nbody\n")
    report = validate_vault(vault, checks=["legacy_quest_key"])
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.check == "legacy_quest_key"
    assert issue.severity == "warning"
    assert issue.detail["value"] == "main"
    assert "--fix" in issue.message


def test_legacy_quest_key_canonical_only_is_clean(vault: Path):
    write(vault / "areas" / "Health.md", "---\ntype: area\nquest-kind: main\n---\nbody\n")
    report = validate_vault(vault, checks=["legacy_quest_key"])
    assert report.issues == []


def test_legacy_quest_key_ignores_backmatter(vault: Path):
    # A legacy quest: in *backmatter* is metadata_in_backmatter's job, not ours.
    text = "---\ntype: area\n---\nbody\n---\nquest: side\n---\n"
    write(vault / "areas" / "Tail.md", text)
    report = validate_vault(vault, checks=["legacy_quest_key"])
    assert report.issues == []


def test_legacy_quest_key_flags_any_para_type(vault: Path):
    # Spec puts quest-kind on projects/resources too, so legacy quest: on a
    # project is still a finding (not gated to areas).
    write(vault / "projects" / "Roof.md", "---\ntype: project\nquest: none\n---\nbody\n")
    report = validate_vault(vault, checks=["legacy_quest_key"])
    assert len(report.issues) == 1
    assert report.issues[0].path == "projects/Roof.md"
