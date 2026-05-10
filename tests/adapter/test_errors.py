"""Tests for adapter.errors."""

from __future__ import annotations

from para_quest_notes.adapter.errors import (
    AdapterError,
    ConfigError,
    EscalateToUser,
    LLMError,
    VaultError,
)


def test_subclasses() -> None:
    for cls in (ConfigError, VaultError, LLMError):
        assert issubclass(cls, AdapterError)


def test_escalation_to_dict() -> None:
    esc = EscalateToUser(
        step="pick_quest",
        reason="ambiguous",
        options=[{"id": "q1"}, {"id": "q2"}],
        context={"file": "inbox/x.md"},
    )
    assert esc.to_dict() == {
        "step": "pick_quest",
        "reason": "ambiguous",
        "options": [{"id": "q1"}, {"id": "q2"}],
        "context": {"file": "inbox/x.md"},
    }


def test_escalation_is_an_exception() -> None:
    esc = EscalateToUser(step="x", reason="y")
    assert isinstance(esc, Exception)
    try:
        raise esc
    except EscalateToUser as caught:
        assert caught.step == "x"
