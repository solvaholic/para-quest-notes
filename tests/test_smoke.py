"""Smoke test: package imports and exposes a version."""

import para_quest_notes


def test_version() -> None:
    assert para_quest_notes.__version__
