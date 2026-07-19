"""Tests for ``pqn-validate --fix`` (batch legacy ``quest:`` migration, #97)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from para_quest_notes.workflows.validate.api import validate_vault
from para_quest_notes.workflows.validate.fix import fix_vault, migrate_note_text

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_VAULT = REPO_ROOT / "samples" / "vault"


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


# ---------- migrate_note_text (pure) ----------


def test_migrate_renames_key_preserving_order():
    text = "---\ntype: area\nquest: main\nsupports:\n- '[[X]]'\n---\nbody\n"
    new_text, value, reason = migrate_note_text(text)
    assert value == "main"
    assert reason == ""
    assert new_text is not None
    # quest-kind lands where quest was; everything else keeps its place.
    assert new_text == "---\ntype: area\nquest-kind: main\nsupports:\n- '[[X]]'\n---\nbody\n"


def test_migrate_canonical_present_drops_legacy():
    text = "---\ntype: area\nquest-kind: side\nquest: main\n---\nbody\n"
    new_text, value, reason = migrate_note_text(text)
    assert new_text is not None
    # canonical wins; legacy key removed; canonical value untouched.
    assert "quest: main" not in new_text
    assert "quest-kind: side" in new_text


def test_migrate_invalid_value_is_left_alone():
    text = "---\ntype: resource\nquest: banana\n---\nbody\n"
    new_text, value, reason = migrate_note_text(text)
    assert new_text is None
    assert value == "banana"
    assert "not a valid kind" in reason


def test_migrate_no_legacy_key_is_noop():
    text = "---\ntype: area\nquest-kind: main\n---\nbody\n"
    new_text, _, reason = migrate_note_text(text)
    assert new_text is None
    assert "no legacy" in reason


def test_migrate_preserves_tail_backmatter():
    text = "---\ntype: area\nquest: side\n---\nbody\n\n---\nsource_url: http://x\n---\n"
    new_text, _, _ = migrate_note_text(text)
    assert new_text is not None
    assert new_text.endswith("---\nsource_url: http://x\n---\n")
    assert "quest-kind: side" in new_text


def test_migrate_preserves_frontmatter_comments_and_scalars():
    # A structural YAML round-trip would drop the comment and coerce 0123/yes.
    text = "---\ntype: area\nquest: main  # classifier\ncreated: 0123\npinned: yes\n---\nbody\n"
    new_text, _, reason = migrate_note_text(text)
    assert reason == ""
    assert new_text == (
        "---\ntype: area\nquest-kind: main  # classifier\ncreated: 0123\npinned: yes\n---\nbody\n"
    )


def test_migrate_preserves_crlf_line_endings():
    text = "---\r\ntype: area\r\nquest: side\r\n---\r\nbody\r\n"
    new_text, _, _ = migrate_note_text(text)
    assert new_text == "---\r\ntype: area\r\nquest-kind: side\r\n---\r\nbody\r\n"


def test_migrate_list_value_is_skipped_not_crashed():
    text = "---\ntype: area\nquest:\n- main\n- side\n---\nbody\n"
    new_text, value, reason = migrate_note_text(text)
    assert new_text is None
    assert value == ["main", "side"]
    assert "not a valid kind" in reason


def test_migrate_ignores_nested_quest_key():
    # A quest: under another mapping is not the top-level classifier.
    text = "---\ntype: area\nquest-kind: main\nmeta:\n  quest: something\n---\nbody\n"
    new_text, _, reason = migrate_note_text(text)
    # No top-level legacy key -> nothing to do.
    assert new_text is None
    assert "no legacy" in reason


# ---------- fix_vault (dry-run / apply) ----------


def test_fix_dry_run_reports_without_writing(vault: Path):
    p = write(vault / "areas" / "Health.md", "---\ntype: area\nquest: main\n---\nbody\n")
    report = fix_vault(vault, apply=False)
    assert report.applied is False
    assert [e.path for e in report.migrated] == ["areas/Health.md"]
    # File untouched on dry-run.
    assert "quest: main" in p.read_text(encoding="utf-8")


def test_fix_apply_rewrites_file(vault: Path):
    p = write(vault / "areas" / "Health.md", "---\ntype: area\nquest: main\n---\nbody\n")
    report = fix_vault(vault, apply=True)
    assert report.applied is True
    assert len(report.migrated) == 1
    content = p.read_text(encoding="utf-8")
    assert "quest-kind: main" in content
    assert "quest: main" not in content


def test_fix_skips_invalid_value(vault: Path):
    write(vault / "resources" / "Weird.md", "---\ntype: resource\nquest: banana\n---\nbody\n")
    report = fix_vault(vault, apply=True)
    assert report.migrated == []
    assert len(report.skipped) == 1
    assert report.skipped[0].value == "banana"


def test_fix_is_idempotent(vault: Path):
    write(vault / "areas" / "Health.md", "---\ntype: area\nquest: main\n---\nbody\n")
    fix_vault(vault, apply=True)
    second = fix_vault(vault, apply=True)
    assert second.migrated == []
    assert second.skipped == []


def test_fix_scoped_to_path(vault: Path):
    write(vault / "areas" / "A.md", "---\ntype: area\nquest: main\n---\nbody\n")
    write(vault / "areas" / "B.md", "---\ntype: area\nquest: side\n---\nbody\n")
    report = fix_vault(vault, paths=[vault / "areas" / "A.md"], apply=True)
    assert [e.path for e in report.migrated] == ["areas/A.md"]
    # B untouched.
    assert "quest: side" in (vault / "areas" / "B.md").read_text(encoding="utf-8")


# ---------- sample-vault smoke (#97 verify step) ----------


def test_fix_migrates_sample_vault_and_revalidates_clean(tmp_path: Path):
    """Copy samples/vault, inject legacy quest:, fix --apply, confirm clean."""
    vault = tmp_path / "vault"
    shutil.copytree(SAMPLE_VAULT, vault)

    # Downgrade a couple of canonical notes to the legacy spelling.
    targets = sorted(vault.rglob("*.md"))
    downgraded: list[Path] = []
    for md in targets:
        text = md.read_text(encoding="utf-8")
        if text.startswith("---") and "\nquest-kind:" in text:
            md.write_text(text.replace("quest-kind:", "quest:", 1), encoding="utf-8")
            downgraded.append(md)
        if len(downgraded) == 3:
            break
    assert downgraded, "sample vault had no quest-kind notes to downgrade"

    # validate should now flag them.
    before = validate_vault(vault, checks=["legacy_quest_key"])
    assert len(before.issues) == len(downgraded)

    report = fix_vault(vault, apply=True)
    assert len(report.migrated) == len(downgraded)
    assert report.skipped == []

    # Every downgraded note is canonical again.
    for md in downgraded:
        content = md.read_text(encoding="utf-8")
        assert "quest-kind:" in content
        assert "\nquest:" not in content

    # Whole vault re-validates clean.
    after = validate_vault(vault)
    assert after.issues == []
