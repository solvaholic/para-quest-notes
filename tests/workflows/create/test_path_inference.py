"""Tests for ``pqn-create`` path inference (#45)."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.workflows.create.path_inference import (
    PathInferenceError,
    infer_from_path,
)

# ---- Happy paths --------------------------------------------------------


def test_infer_simple_project():
    result = infer_from_path("projects/My Note.md")
    assert result.type == "project"
    assert result.title == "My Note"
    assert result.sub_path is None
    assert result.vault is None


def test_infer_area_with_sub_path():
    result = infer_from_path("areas/home/Water Heater.md")
    assert result.type == "area"
    assert result.title == "Water Heater"
    assert result.sub_path == "home"
    assert result.vault is None


def test_infer_resource_deep_sub_path():
    result = infer_from_path("resources/programming/python/Decorators.md")
    assert result.type == "resource"
    assert result.title == "Decorators"
    assert result.sub_path == "programming/python"


def test_infer_with_vault_prefix():
    result = infer_from_path("samples/vault/projects/para_quest_notes/Improve PQN.md")
    assert result.type == "project"
    assert result.title == "Improve PQN"
    assert result.sub_path == "para_quest_notes"
    assert result.vault == Path("samples/vault")


def test_infer_absolute_path():
    result = infer_from_path("/Users/me/notes/projects/2026/Plan.md")
    assert result.type == "project"
    assert result.title == "Plan"
    assert result.sub_path == "2026"
    assert result.vault == Path("/Users/me/notes")


def test_infer_without_md_extension():
    """Filename without .md still works - title is the bare name."""
    result = infer_from_path("projects/My Note")
    assert result.type == "project"
    assert result.title == "My Note"


def test_infer_singular_dir_name():
    """Singular PARA dir names are accepted as a convenience."""
    result = infer_from_path("project/My Note.md")
    assert result.type == "project"
    assert result.title == "My Note"


def test_infer_case_insensitive_dir():
    """PARA dir matching is case-insensitive."""
    result = infer_from_path("Projects/My Note.md")
    assert result.type == "project"
    assert result.title == "My Note"


# ---- Error cases --------------------------------------------------------


def test_infer_empty_path():
    with pytest.raises(PathInferenceError, match="empty"):
        infer_from_path("")


def test_infer_no_para_dir():
    with pytest.raises(PathInferenceError, match="PARA directory"):
        infer_from_path("random/stuff/Note.md")


def test_infer_para_dir_only_no_filename():
    with pytest.raises(PathInferenceError, match="no filename"):
        infer_from_path("projects/")


def test_infer_empty_title():
    with pytest.raises(PathInferenceError, match="empty filename"):
        infer_from_path("projects/.md")
