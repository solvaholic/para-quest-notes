"""Tests for shape sampling logic."""

from __future__ import annotations

import random

from para_quest_notes.corpus.shapes import (
    FrontmatterKind,
    LocationKind,
    Quirk,
    Shape,
    sample_frontmatter,
    sample_quirks,
    sample_shape,
)


def test_inbox_frontmatter_avoids_full() -> None:
    rng = random.Random(0)
    seen: set[FrontmatterKind] = set()
    for _ in range(200):
        seen.add(sample_frontmatter(rng, LocationKind.INBOX))
    # FULL backmatter on inbox notes would be unrealistic.
    assert FrontmatterKind.FULL not in seen


def test_daily_frontmatter_is_bare_or_obsidian() -> None:
    rng = random.Random(0)
    for _ in range(200):
        fm = sample_frontmatter(rng, LocationKind.DAILY)
        assert fm in {FrontmatterKind.NONE, FrontmatterKind.OBSIDIAN_ONLY}


def test_missing_supports_quirk_skipped_when_no_frontmatter() -> None:
    rng = random.Random(0)
    # quirk_rate=1 would normally always apply MISSING_SUPPORTS, but
    # that's nonsensical when there's no frontmatter to omit it from.
    for _ in range(50):
        q = sample_quirks(rng, FrontmatterKind.NONE, quirk_rate=1.0)
        assert Quirk.MISSING_SUPPORTS not in q


def test_closed_tasks_implies_has_tasks() -> None:
    rng = random.Random(0)
    # Run enough trials that CLOSED_TASKS_ONLY is highly likely to appear.
    found = False
    for _ in range(200):
        q = sample_quirks(rng, FrontmatterKind.FULL, quirk_rate=0.5)
        if Quirk.CLOSED_TASKS_ONLY in q:
            assert Quirk.HAS_TASKS in q
            found = True
    assert found, "test setup didn't trigger CLOSED_TASKS_ONLY at all — bump quirk_rate or trials"


def test_sample_shape_is_deterministic() -> None:
    a = random.Random(123)
    b = random.Random(123)
    shapes_a = [sample_shape(a, LocationKind.PARA, quirk_rate=0.4) for _ in range(20)]
    shapes_b = [sample_shape(b, LocationKind.PARA, quirk_rate=0.4) for _ in range(20)]
    assert shapes_a == shapes_b


def test_shape_dataclass_is_hashable() -> None:
    s = Shape(LocationKind.PARA, FrontmatterKind.FULL, frozenset({Quirk.HAS_TASKS}))
    assert hash(s) == hash(s)
