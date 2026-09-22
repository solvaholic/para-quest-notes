"""Behavioral tests for direct one-hop ``pqn-search --links`` lookup."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.vault.links import LinkTargetError
from para_quest_notes.workflows.search import search_links


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    write(
        tmp_path / "resources" / "Target.md",
        "---\ntype: resource\n---\n"
        "[[Mutual]] [[Mutual#Heading|alias]] "
        "[[Outgoing]] [[High Count]] [[High Count]] [[High Count]] "
        "[[Missing Note]] [[missing note]] [[Duplicate]] [[Target]]\n",
    )
    write(
        tmp_path / "projects" / "Mutual.md",
        "---\ntype: project\nsupports:\n- '[[Health]]'\n---\n[[Target]]\n",
    )
    write(
        tmp_path / "projects" / "Outgoing.md",
        "---\ntype: project\nsupports:\n- '[[Create]]'\n---\n",
    )
    write(
        tmp_path / "areas" / "High Count.md",
        "---\ntype: area\nsupports:\n- '[[Health]]'\n---\n",
    )
    write(
        tmp_path / "resources" / "Incoming.md",
        "---\ntype: resource\n---\n[[target]] [[Target]]\n",
    )
    write(tmp_path / "projects" / "one" / "Duplicate.md", "")
    write(tmp_path / "resources" / "two" / "Duplicate.md", "")
    return tmp_path


def test_search_links_reports_one_neighbor_with_directional_counts(vault: Path):
    results = search_links(vault, "Target")

    assert results.target.path == "resources/Target.md"
    assert [(item.path, item.link_context.relation) for item in results.results] == [
        ("projects/Mutual.md", "mutual"),
        ("areas/High Count.md", "outgoing"),
        ("projects/Outgoing.md", "outgoing"),
        ("resources/Incoming.md", "incoming"),
    ]
    mutual = results.results[0]
    assert mutual.link_context.outgoing_occurrences == 2
    assert mutual.link_context.incoming_occurrences == 1
    incoming = results.results[-1]
    assert incoming.link_context.outgoing_occurrences == 0
    assert incoming.link_context.incoming_occurrences == 2
    assert all(result.path != "resources/Target.md" for result in results.results)


def test_search_links_reports_missing_and_ambiguous_outgoing_links(vault: Path):
    unresolved = search_links(vault, "Target").unresolved_links

    assert [item.to_dict() for item in unresolved] == [
        {
            "target": "Duplicate",
            "occurrences": 1,
            "reason": "ambiguous",
            "candidates": [
                "projects/one/Duplicate.md",
                "resources/two/Duplicate.md",
            ],
        },
        {
            "target": "Missing Note",
            "occurrences": 2,
            "reason": "missing",
            "candidates": [],
        },
    ]


def test_search_links_filters_neighbors_not_target_and_limits_after_ranking(vault: Path):
    results = search_links(
        vault,
        "Target",
        types=["project"],
        quest="[[Health]]",
        limit=1,
    )

    assert results.target.type == "resource"
    assert [item.path for item in results.results] == ["projects/Mutual.md"]
    assert results.scope == {
        "types": ["project"],
        "quest": "health",
        "include_archive": False,
        "limit": 1,
    }
    assert results.to_dict()["summary"] == {
        "results": 1,
        "outgoing": 0,
        "incoming": 0,
        "mutual": 1,
        "unresolved_outgoing": 2,
    }
    assert len(results.unresolved_links) == 2


def test_search_links_ranking_uses_relation_then_occurrences_then_path(vault: Path):
    write(vault / "areas" / "Alpha.md", "---\ntype: area\n---\n")
    target = vault / "resources" / "Target.md"
    target.write_text(
        target.read_text() + "[[Alpha]] [[Alpha]] [[Alpha]]\n",
        encoding="utf-8",
    )

    results = search_links(vault, "Target")
    outgoing_paths = [
        item.path for item in results.results if item.link_context.relation == "outgoing"
    ]
    assert outgoing_paths == [
        "areas/Alpha.md",
        "areas/High Count.md",
        "projects/Outgoing.md",
    ]


def test_search_links_archive_policy_applies_to_target_and_neighbors(vault: Path):
    write(
        vault / "archive" / "projects" / "Old.md",
        "---\ntype: project\n---\n[[Target]]\n",
    )
    target = vault / "resources" / "Target.md"
    target.write_text(target.read_text() + "[[Old]]\n", encoding="utf-8")

    default = search_links(vault, "Target")
    assert all(item.path != "archive/projects/Old.md" for item in default.results)
    assert any(
        item.target == "Old" and item.reason == "missing" for item in default.unresolved_links
    )

    included = search_links(vault, "archive/projects/Old.md", include_archive=True)
    assert included.target.path == "archive/projects/Old.md"
    target_neighbor = next(item for item in included.results if item.path == "resources/Target.md")
    assert target_neighbor.link_context.relation == "mutual"

    with pytest.raises(LinkTargetError) as exc:
        search_links(vault, "archive/projects/Old.md")
    assert exc.value.kind == "missing"


def test_search_links_empty_neighborhood_is_success(tmp_path: Path):
    write(tmp_path / "areas" / "Alone.md", "---\ntype: area\n---\n")

    results = search_links(tmp_path, "alone.md")

    assert results.results == []
    assert results.unresolved_links == []
    assert results.to_dict()["summary"] == {
        "results": 0,
        "outgoing": 0,
        "incoming": 0,
        "mutual": 0,
        "unresolved_outgoing": 0,
    }


def test_search_links_target_resolution_errors_are_typed(vault: Path):
    with pytest.raises(LinkTargetError) as missing:
        search_links(vault, "No Such Note")
    assert missing.value.kind == "missing"

    with pytest.raises(LinkTargetError) as ambiguous:
        search_links(vault, "duplicate.md")
    assert ambiguous.value.kind == "ambiguous"
    assert len(ambiguous.value.candidates) == 2

    with pytest.raises(LinkTargetError) as escaped:
        search_links(vault, "../Target.md")
    assert escaped.value.kind == "outside_vault"

    assert search_links(vault, "TARGET").target.path == "resources/Target.md"
    assert search_links(vault, "resources/Target.md").target.path == ("resources/Target.md")


def test_search_links_accepts_a_relative_vault_path(vault: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(vault.parent)

    results = search_links(Path(vault.name), "Target")

    assert results.target.path == "resources/Target.md"


def test_search_links_rejects_negative_limit(vault: Path):
    with pytest.raises(ValueError, match="limit must be >= 0"):
        search_links(vault, "Target", limit=-1)


def test_search_links_uses_standard_exclusions_and_skips_unreadable_files(
    vault: Path, monkeypatch: pytest.MonkeyPatch
):
    write(vault / ".obsidian" / "Hidden.md", "[[Target]]")
    unreadable = write(vault / "projects" / "Unreadable.md", "[[Target]]")
    real_read = Path.read_text

    def selective_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == unreadable:
            raise PermissionError(path)
        return real_read(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", selective_read)
    results = search_links(vault, "Target")

    assert all("Hidden.md" not in item.path for item in results.results)
    assert all("Unreadable.md" not in item.path for item in results.results)


def test_link_json_contract_is_flat_and_explicit(vault: Path):
    data = search_links(vault, "Target").to_dict()

    assert set(data) == {
        "vault",
        "mode",
        "target",
        "scope",
        "summary",
        "results",
        "unresolved_links",
    }
    assert data["mode"] == "links"
    assert data["summary"] == {
        "results": 4,
        "outgoing": 2,
        "incoming": 1,
        "mutual": 1,
        "unresolved_outgoing": 2,
    }
    assert set(data["results"][0]) == {
        "path",
        "type",
        "supports",
        "link_context",
    }
    assert set(data["results"][0]["link_context"]) == {
        "relation",
        "outgoing_occurrences",
        "incoming_occurrences",
    }
