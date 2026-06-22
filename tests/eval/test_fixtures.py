"""Loader + schema tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.eval.fixtures import FixtureError, load_fixtures


def write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body, encoding="utf-8")
    return p


def test_loads_single_fixture(tmp_path: Path) -> None:
    write(
        tmp_path,
        "one.yaml",
        """
id: one
title: Hello
body: |
  some body
quest_catalog:
  - { name: Health, kind: main }
expected:
  classify_para: { type: project }
  pick_quest:
    acceptable:
      - [Health]
""",
    )
    fixtures = load_fixtures(tmp_path)
    assert len(fixtures) == 1
    fx = fixtures[0]
    assert fx.workflow == "ingest"
    assert fx.id == "one"
    assert fx.expected.classify_para is not None
    assert fx.expected.classify_para.type == "project"
    assert fx.expected.pick_quest is not None
    assert fx.expected.pick_quest.acceptable == (frozenset({"Health"}),)


def test_loads_list_of_fixtures(tmp_path: Path) -> None:
    write(
        tmp_path,
        "list.yaml",
        """
- id: a
  title: A
  expected:
    classify_para: { type: resource }
    pick_quest: { skipped: true }
- id: b
  title: B
  expected:
    classify_para: { type: area }
    pick_quest:
      acceptable:
        - [Health]
  quest_catalog:
    - { name: Health, kind: main }
""",
    )
    fixtures = load_fixtures(tmp_path)
    assert {f.id for f in fixtures} == {"a", "b"}


def test_explicit_ingest_workflow_is_accepted(tmp_path: Path) -> None:
    write(
        tmp_path,
        "one.yaml",
        """
workflow: ingest
id: one
title: Hello
expected:
  classify_para: { type: resource }
  pick_quest: { skipped: true }
""",
    )
    fixtures = load_fixtures(tmp_path)
    assert fixtures[0].workflow == "ingest"


def test_unknown_workflow_raises(tmp_path: Path) -> None:
    write(
        tmp_path,
        "bad.yaml",
        """
workflow: nope
id: x
title: x
expected: {}
""",
    )
    with pytest.raises(FixtureError, match="unknown workflow"):
        load_fixtures(tmp_path)


def test_duplicate_id_raises(tmp_path: Path) -> None:
    write(tmp_path, "a.yaml", "id: x\ntitle: x\nexpected: {}\n")
    write(tmp_path, "b.yaml", "id: x\ntitle: x\nexpected: {}\n")
    with pytest.raises(FixtureError, match="duplicate fixture id"):
        load_fixtures(tmp_path)


def test_unknown_step_raises(tmp_path: Path) -> None:
    write(
        tmp_path,
        "bad.yaml",
        "id: x\ntitle: x\nexpected:\n  not_a_step: { foo: 1 }\n",
    )
    with pytest.raises(FixtureError, match="unknown step"):
        load_fixtures(tmp_path)


def test_invalid_para_type_raises(tmp_path: Path) -> None:
    write(
        tmp_path,
        "bad.yaml",
        "id: x\ntitle: x\nexpected:\n  classify_para: { type: nope }\n",
    )
    with pytest.raises(FixtureError, match="not in"):
        load_fixtures(tmp_path)


def test_pick_quest_requires_acceptable_or_skipped(tmp_path: Path) -> None:
    write(
        tmp_path,
        "bad.yaml",
        "id: x\ntitle: x\nexpected:\n  pick_quest: {}\n",
    )
    with pytest.raises(FixtureError, match="acceptable"):
        load_fixtures(tmp_path)


def test_pick_quest_without_catalog_raises(tmp_path: Path) -> None:
    write(
        tmp_path,
        "bad.yaml",
        """
id: x
title: x
expected:
  pick_quest:
    acceptable:
      - [Health]
""",
    )
    with pytest.raises(FixtureError, match="quest_catalog is empty"):
        load_fixtures(tmp_path)


def test_empty_file_returns_nothing(tmp_path: Path) -> None:
    write(tmp_path, "empty.yaml", "")
    assert load_fixtures(tmp_path) == []


def test_top_level_must_be_mapping_or_list(tmp_path: Path) -> None:
    write(tmp_path, "bad.yaml", '"just a string"\n')
    with pytest.raises(FixtureError, match="mapping or a list"):
        load_fixtures(tmp_path)


def test_source_filename_defaults_to_none(tmp_path: Path) -> None:
    write(tmp_path, "one.yaml", "id: x\ntitle: x\nexpected: {}\n")
    assert load_fixtures(tmp_path)[0].source_filename is None


def test_source_filename_appends_md_extension(tmp_path: Path) -> None:
    write(
        tmp_path,
        "one.yaml",
        "id: x\ntitle: x\nsource_filename: CVE-2021-44228\nexpected: {}\n",
    )
    assert load_fixtures(tmp_path)[0].source_filename == "CVE-2021-44228.md"


def test_source_filename_keeps_existing_md_extension(tmp_path: Path) -> None:
    write(
        tmp_path,
        "one.yaml",
        "id: x\ntitle: x\nsource_filename: notes.md\nexpected: {}\n",
    )
    assert load_fixtures(tmp_path)[0].source_filename == "notes.md"


def test_source_filename_rejects_path_separators(tmp_path: Path) -> None:
    write(
        tmp_path,
        "bad.yaml",
        "id: x\ntitle: x\nsource_filename: inbox/notes.md\nexpected: {}\n",
    )
    with pytest.raises(FixtureError, match="path separators"):
        load_fixtures(tmp_path)


def test_source_filename_rejects_empty_string(tmp_path: Path) -> None:
    write(
        tmp_path,
        "bad.yaml",
        'id: x\ntitle: x\nsource_filename: "   "\nexpected: {}\n',
    )
    with pytest.raises(FixtureError, match="non-empty string"):
        load_fixtures(tmp_path)
