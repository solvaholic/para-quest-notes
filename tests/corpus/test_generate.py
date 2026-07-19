"""Tests for ``generate_vault`` end-to-end behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from para_quest_notes.adapter.vault import is_vault
from para_quest_notes.corpus.generate import (
    GenerateOptions,
    GenerateResult,
    generate_vault,
)


def _gen(tmp_path: Path, **overrides: object) -> GenerateResult:
    opts = GenerateOptions(**{"seed": 7, **overrides})  # type: ignore[arg-type]
    return generate_vault(tmp_path / "vault", opts)


def test_generated_vault_passes_is_vault(tmp_path: Path) -> None:
    res = _gen(tmp_path)
    assert is_vault(res.out)


def test_main_and_side_quest_notes_always_emitted(tmp_path: Path) -> None:
    res = _gen(tmp_path, projects=0, areas=0, resources=0, inbox=0, daily=0)
    titles = {f.title for f in res.files}
    # every Main Quest and Side Quest from seeds.yaml shows up
    assert "Health" in titles
    assert "Maintain Home" in titles


def test_counts_match_request(tmp_path: Path) -> None:
    res = _gen(tmp_path, projects=4, areas=3, resources=2, inbox=5, daily=3)
    counts: dict[str, int] = {}
    for f in res.files:
        counts[f.location_kind.value] = counts.get(f.location_kind.value, 0) + 1
    assert counts.get("inbox", 0) == 5
    assert counts.get("daily", 0) == 3
    # projects/areas/resources are placed under PARA / TOPIC / QUEST,
    # so summing by type_ is the right invariant:
    by_type: dict[str, int] = {}
    for f in res.files:
        by_type[f.type_] = by_type.get(f.type_, 0) + 1
    # Areas count: every Main + Side Quest note (always emitted) plus 3 sampled.
    # Three Main Quests + two Side Quests + 3 areas = 8.
    assert by_type["area"] == 3 + 3 + 2
    assert by_type["project"] == 4
    # Resources: 2 sampled + (inbox notes are typed 'resource' too) +
    # daily notes also 'resource' in our schema.
    assert by_type["resource"] == 2 + 5 + 3


def test_same_seed_produces_identical_bytes(tmp_path: Path) -> None:
    a = generate_vault(tmp_path / "a", GenerateOptions(seed=99))
    b = generate_vault(tmp_path / "b", GenerateOptions(seed=99))
    a_files = sorted(p.relative_to(a.out).as_posix() for p in a.out.rglob("*") if p.is_file())
    b_files = sorted(p.relative_to(b.out).as_posix() for p in b.out.rglob("*") if p.is_file())
    assert a_files == b_files
    for rel in a_files:
        assert (a.out / rel).read_bytes() == (b.out / rel).read_bytes(), rel


def test_different_seed_produces_different_output(tmp_path: Path) -> None:
    a = generate_vault(tmp_path / "a", GenerateOptions(seed=1))
    b = generate_vault(tmp_path / "b", GenerateOptions(seed=2))
    # At minimum the inbox-note titles should differ.
    a_inbox = {f.title for f in a.files if f.location_kind.value == "inbox"}
    b_inbox = {f.title for f in b.files if f.location_kind.value == "inbox"}
    assert a_inbox != b_inbox


def test_quirk_rate_zero_produces_no_quirks(tmp_path: Path) -> None:
    res = _gen(tmp_path, quirk_rate=0.0)
    # Generator can still force HAS_TASKS on Projects (most have tasks
    # in real life), so exclude it from the no-quirk assertion.
    forced = {"has_tasks", "duplicate_title"}
    bad = [f for f in res.files if any(q.value not in forced for q in f.quirks)]
    assert not bad, [(f.path, [q.value for q in f.quirks]) for f in bad]


def test_quirk_rate_high_produces_many_quirks(tmp_path: Path) -> None:
    res = _gen(tmp_path, quirk_rate=0.9, projects=10, inbox=10)
    notes_with_quirks = [f for f in res.files if f.quirks]
    assert len(notes_with_quirks) >= len(res.files) // 2


def test_manifest_written_and_well_formed(tmp_path: Path) -> None:
    res = _gen(tmp_path)
    assert res.manifest_path.exists()
    raw = json.loads(res.manifest_path.read_text(encoding="utf-8"))
    assert raw["generator_version"] == 1
    assert raw["options"]["seed"] == 7
    assert len(raw["files"]) == len(res.files)
    # manifest entries are sorted by path
    paths = [f["path"] for f in raw["files"]]
    assert paths == sorted(paths)


def test_no_manifest_option(tmp_path: Path) -> None:
    res = _gen(tmp_path, write_manifest=False)
    assert not res.manifest_path.exists()


def test_refuses_non_empty_dir_without_clean(tmp_path: Path) -> None:
    out = tmp_path / "vault"
    out.mkdir()
    (out / "leftover.txt").write_text("hi", encoding="utf-8")
    with pytest.raises(FileExistsError):
        generate_vault(out, GenerateOptions(seed=0))


def test_clean_wipes_existing_dir(tmp_path: Path) -> None:
    out = tmp_path / "vault"
    out.mkdir()
    (out / "leftover.txt").write_text("hi", encoding="utf-8")
    generate_vault(out, GenerateOptions(seed=0, clean=True))
    assert not (out / "leftover.txt").exists()


def test_empty_existing_dir_is_ok(tmp_path: Path) -> None:
    out = tmp_path / "vault"
    out.mkdir()
    res = generate_vault(out, GenerateOptions(seed=0))
    assert res.files


def test_projects_above_pool_size_uses_replacement(tmp_path: Path) -> None:
    # seeds.yaml has 6 projects; ask for 10 — should not raise.
    res = _gen(tmp_path, projects=10)
    project_files = [f for f in res.files if f.type_ == "project"]
    assert len(project_files) == 10


def test_full_frontmatter_notes_have_quest_field(tmp_path: Path) -> None:
    res = _gen(tmp_path)
    for gf in res.files:
        if gf.frontmatter_kind.value != "full":
            continue
        body = (res.out / gf.path).read_text(encoding="utf-8")
        assert body.startswith("---\n"), gf.path
        # split frontmatter cheaply
        end = body.index("\n---\n", 4)
        front = body[4:end]
        assert "type:" in front
        assert "quest-kind:" in front
