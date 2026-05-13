from __future__ import annotations

import json
from pathlib import Path

from para_quest_notes.adapter.fake_llm import FakeLLM
from para_quest_notes.adapter.prompts import PromptLoader
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.workflows.archive.contract import ArchiveInputs
from para_quest_notes.workflows.archive.pipeline import PROMPTS_DIR, archive_note


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def _generate_prompt_id() -> str:
    return PromptLoader(PROMPTS_DIR).get("generate_outcome").id


def test_generate_outcome_dry_run_defers_llm_call_and_writes_nothing(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "Train for 5K.md"
    src.write_text(
        "---\ntype: project\nquest: none\nsupports: ['[[Health]]']\n---\n"
        "# Train for 5K\n\n"
        "Built a simple schedule and kept notes after each run.\n"
        "- [x] Finished week 8\n"
        "- [x] Ran for 30 minutes without walking\n"
    )
    llm = FakeLLM()

    result = archive_note(
        ArchiveInputs(target="Train for 5K", generate_outcome=True),
        vault=vault,
        apply=False,
        llm=llm,
        model="fake-model",
        today="2026-05-12",
    )

    assert result.ok, result.escalation or result.error
    assert result.plan.outcome_action == "will_generate"
    assert result.plan.outcome_text is None
    assert result.moved is False
    assert llm.calls == []
    assert src.exists()
    assert not (vault / "archive" / "projects" / "Train for 5K.md").exists()


def test_generate_outcome_apply_generates_writes_and_records_text(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "Train for 5K.md"
    src.write_text(
        "---\ntype: project\nquest: none\nsupports: ['[[Health]]']\n---\n"
        "# Train for 5K\n\n"
        "Built a simple schedule and kept notes after each run.\n"
        "- [x] Finished week 8\n"
        "- [x] Ran for 30 minutes without walking\n"
    )
    (vault / "areas" / "Health.md").write_text(
        "# Health\n\n- [[Train for 5K]] turned into a steady habit.\n"
    )
    outcome = (
        "Finished the training block and made running feel routine again. "
        "By the end of the project, 30-minute runs were consistent and the notes made "
        "the habit easier to keep."
    )
    llm = FakeLLM()
    llm.add_text_response(_generate_prompt_id(), outcome)
    trace_path = tmp_path / "trace.jsonl"

    with TraceWriter(trace_path) as trace:
        result = archive_note(
            ArchiveInputs(target="Train for 5K", generate_outcome=True),
            vault=vault,
            apply=True,
            llm=llm,
            model="fake-model",
            today="2026-05-12",
            trace=trace,
        )

    assert result.ok, result.escalation or result.error
    assert result.plan.outcome_action == "generated"
    assert result.plan.outcome_text == outcome
    assert result.moved is True
    assert not src.exists()
    dest = vault / "archive" / "projects" / "Train for 5K.md"
    assert dest.exists()
    assert f"## Outcome\n\n{outcome}\n" in dest.read_text(encoding="utf-8")

    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    llm_events = [record for record in records if record.get("event") == "llm.complete"]
    assert llm_events
    event = llm_events[0]
    assert event["step"] == "generate_outcome"
    assert event["prompt_id"].startswith("generate_outcome@")
    assert event["prompt_hash"]
    assert event["raw_output"] == result.plan.outcome_text


def test_generate_outcome_insufficient_context_escalates_without_writing(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "Sparse.md"
    src.write_text("---\ntype: project\nquest: none\n---\n# Sparse\n")
    llm = FakeLLM()
    llm.add_text_response(_generate_prompt_id(), "INSUFFICIENT_CONTEXT")

    result = archive_note(
        ArchiveInputs(target="Sparse", generate_outcome=True),
        vault=vault,
        apply=True,
        llm=llm,
        model="fake-model",
        today="2026-05-12",
    )

    assert not result.ok
    assert result.escalation is not None
    assert result.escalation["step"] == "generate_outcome"
    assert src.exists()
    assert not (vault / "archive" / "projects" / "Sparse.md").exists()


def test_generate_outcome_empty_response_escalates_without_writing(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "Empty.md"
    src.write_text(
        "---\ntype: project\nquest: none\n---\n# Empty\n\n- [x] One concrete thing happened\n"
    )
    llm = FakeLLM()
    llm.add_text_response(_generate_prompt_id(), "   ")

    result = archive_note(
        ArchiveInputs(target="Empty", generate_outcome=True),
        vault=vault,
        apply=True,
        llm=llm,
        model="fake-model",
        today="2026-05-12",
    )

    assert not result.ok
    assert result.escalation is not None
    assert result.escalation["step"] == "generate_outcome"
    assert src.exists()
    assert not (vault / "archive" / "projects" / "Empty.md").exists()


def test_without_generate_flag_behavior_stays_outcome_required(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "X.md"
    src.write_text("---\ntype: project\nquest: none\n---\n# X\n")

    result = archive_note(
        ArchiveInputs(target="X"),
        vault=vault,
        apply=False,
        today="2026-05-12",
    )

    assert not result.ok
    assert result.escalation is not None
    assert result.escalation["step"] == "prepare_outcome"
    assert result.plan.outcome_action == "required"
    assert src.exists()


def test_generate_outcome_keeps_existing_outcome_and_never_calls_llm(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "Done.md"
    src.write_text("---\ntype: project\nquest: none\n---\n## Outcome\nDone already.\n")
    llm = FakeLLM()

    result = archive_note(
        ArchiveInputs(target="Done", generate_outcome=True),
        vault=vault,
        apply=False,
        llm=llm,
        model="fake-model",
        today="2026-05-12",
    )

    assert result.ok
    assert result.plan.outcome_action == "kept"
    assert llm.calls == []
    assert src.exists()
