"""Integration: ``pqn-ingest`` calls ``pqn-validate`` as a library.

Specifically, ``propose_filename`` delegates collision detection to
``validate.api.check_basename_available``, so the same logic that
``pqn-validate`` exposes to users is what blocks an ambiguous-wikilink
ingest. These tests pin that wiring.
"""

from __future__ import annotations

import json
from pathlib import Path

from para_quest_notes.adapter.fake_llm import FakeLLM, RecordedCall
from para_quest_notes.workflows.ingest_inbox.pipeline import ingest_one


def _responder(plans: dict[str, dict]):
    def fn(call: RecordedCall) -> str:
        for name, payload in plans.items():
            if call.prompt_id and call.prompt_id.startswith(f"{name}@"):
                return json.dumps(payload)
        return json.dumps({})

    return fn


def _seed(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "inbox").mkdir(parents=True)
    (vault / "areas").mkdir()
    (vault / "projects").mkdir()
    (vault / "resources").mkdir()
    (vault / "areas/Health.md").write_text(
        "---\ntype: area\nquest: main\nsupports: ['[[Health]]']\n---\n"
    )
    return vault


def test_collision_detected_via_validate_library_call(tmp_path: Path):
    """Pre-existing note with the same basename → ingest must escalate
    at ``propose_filename``, surfacing validate's diagnosis."""
    vault = _seed(tmp_path)
    (vault / "resources" / "Run A 5K.md").write_text(
        "---\ntype: resource\nquest: none\n---\n# Existing\n"
    )
    src = vault / "inbox" / "train plan.md"
    src.write_text("# Train Plan\nrun a 5k\n")

    llm = FakeLLM(
        responder=_responder(
            {
                "classify_para": {"type": "project", "confidence": 0.9, "reason": "ok"},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
                "propose_filename": {
                    "choice": "generate",
                    "filename": "Run A 5K.md",
                    "reason": "test",
                },
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=False)
    assert not fr.ok
    assert fr.escalation is not None
    assert fr.escalation["step"] == "propose_filename"
    assert "collide" in fr.escalation["reason"]
    # validate's wording leaks into context — that's the proof of wiring.
    assert "ambiguous" in fr.escalation["context"]["validate_message"]
    # And the existing collider is surfaced as an option.
    existing = {opt["existing"] for opt in fr.escalation["options"]}
    assert existing == {"resources/Run A 5K.md"}
    # Source must remain in inbox.
    assert src.exists()


def test_collision_blocks_apply(tmp_path: Path):
    vault = _seed(tmp_path)
    (vault / "resources" / "Dup.md").write_text("---\ntype: resource\nquest: none\n---\n")
    src = vault / "inbox" / "source.md"
    src.write_text("# Source\nbody\n")

    llm = FakeLLM(
        responder=_responder(
            {
                "classify_para": {"type": "project", "confidence": 0.9, "reason": "ok"},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
                "propose_filename": {"choice": "generate", "filename": "Dup.md", "reason": "test"},
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=True)
    assert not fr.ok
    assert fr.escalation is not None
    assert fr.escalation["step"] == "propose_filename"
    # Apply path must not have moved anything.
    assert src.exists()
    assert not (vault / "projects" / "Dup.md").exists()


def test_archive_collisions_are_ignored(tmp_path: Path):
    """validate (and therefore propose_filename) excludes archive/ —
    archived notes shouldn't block reuse of a name."""
    vault = _seed(tmp_path)
    (vault / "archive" / "projects").mkdir(parents=True)
    (vault / "archive" / "projects" / "Old Name.md").write_text(
        "---\ntype: project\nquest: none\n---\n"
    )
    src = vault / "inbox" / "source.md"
    src.write_text("# Source\nbody\n")

    llm = FakeLLM(
        responder=_responder(
            {
                "classify_para": {"type": "project", "confidence": 0.9, "reason": "ok"},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
                "propose_filename": {
                    "choice": "generate",
                    "filename": "Old Name.md",
                    "reason": "test",
                },
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=False)
    assert fr.ok, fr.escalation or fr.error
    assert fr.decisions.destination == "projects/Old Name.md"


def test_no_collision_proceeds(tmp_path: Path):
    vault = _seed(tmp_path)
    src = vault / "inbox" / "fresh note.md"
    src.write_text("# Fresh\nI want to plan something new this week.\n")

    llm = FakeLLM(
        responder=_responder(
            {
                "classify_para": {"type": "project", "confidence": 0.9, "reason": "ok"},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
                "propose_filename": {
                    "choice": "generate",
                    "filename": "Brand New.md",
                    "reason": "ok",
                },
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=False)
    assert fr.ok, fr.escalation or fr.error
    assert fr.decisions.destination == "projects/Brand New.md"
