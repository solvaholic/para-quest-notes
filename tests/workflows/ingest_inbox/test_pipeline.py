"""End-to-end pipeline tests with FakeLLM."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from para_quest_notes.adapter.fake_llm import FakeLLM, RecordedCall
from para_quest_notes.workflows.ingest_inbox.pipeline import ingest_inbox, ingest_one


def _build_responder(plans: dict[str, dict]):
    """Returns a responder that picks the right canned response per step.

    Keyed by prompt_id prefix (the prompt name). Falls back to a low-conf
    response so unhandled prompts surface as escalations rather than test
    crashes.
    """

    def _responder(call: RecordedCall) -> str:
        pid = call.prompt_id or ""
        for name, payload in plans.items():
            if pid.startswith(f"{name}@"):
                return json.dumps(payload)
        return json.dumps({})

    return _responder


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "inbox").mkdir(parents=True)
    (vault / "areas").mkdir()
    (vault / "projects").mkdir()
    (vault / "resources").mkdir()
    (vault / "areas/Health.md").write_text(
        "---\ntype: area\nquest: main\nsupports: ['[[Health]]']\n---\n"
    )
    (vault / "areas/Connect.md").write_text(
        "---\ntype: area\nquest: main\nsupports: ['[[Connect]]']\n---\n"
    )
    return vault


def test_ingest_one_dry_run(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "inbox/Train Plan.md"
    src.write_text("# Train Plan\nrun a 5k\n")
    (vault / "areas/Health.md").write_text(
        (vault / "areas/Health.md").read_text() + "\nsee [[Train Plan]]\n"
    )

    llm = FakeLLM(
        responder=_build_responder(
            {
                "classify_para": {"type": "project", "confidence": 0.9, "reason": "ok"},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
                "propose_filename": {"filename": "Run a 5K.md", "reason": "concise"},
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=False)
    assert fr.ok
    assert fr.decisions.para_type == "project"
    assert fr.decisions.quests == ["Health"]
    assert fr.decisions.destination == "projects/Run a 5K.md"
    assert fr.applied is False
    assert src.exists()
    assert any(h["file"] == "areas/Health.md" for h in fr.change.wikilinks_rewritten)


def test_ingest_inbox_processes_all_files(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "inbox/Note A.md").write_text("# A\n")
    (vault / "inbox/Note B.md").write_text("# B\n")

    plans = iter(
        [
            {
                "classify_para": {"type": "project", "confidence": 0.9},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9},
                "propose_filename": {"filename": "Alpha.md"},
            },
            {
                "classify_para": {"type": "resource", "confidence": 0.9},
                "pick_quest": {},  # skipped for resource
                "propose_filename": {"filename": "Bravo.md"},
            },
        ]
    )
    current: dict = {}
    file_seen = {"v": None}

    def responder(call: RecordedCall) -> str:
        # Advance plan when we see a new scan (classify_para is the first
        # LLM call per file).
        nonlocal current
        if call.prompt_id and call.prompt_id.startswith("classify_para@"):
            current = next(plans)
        for name, payload in current.items():
            if call.prompt_id and call.prompt_id.startswith(f"{name}@"):
                return json.dumps(payload)
        return json.dumps({})

    llm = FakeLLM(responder=responder)
    result = ingest_inbox(vault, llm=llm, apply=False)
    assert len(result.files) == 2
    assert all(f.ok for f in result.files)
    dests = sorted(f.decisions.destination for f in result.files)
    assert dests == ["projects/Alpha.md", "resources/Bravo.md"]
    # Resource file should have empty quests.
    by_dest = {f.decisions.destination: f for f in result.files}
    assert by_dest["resources/Bravo.md"].decisions.quests == []
    # Suppress unused-var warning.
    del file_seen


def test_apply_mode_moves_files(tmp_path: Path):
    """Integration: --apply against a copy of the bundled sample vault.

    Copies samples/vault/ into tmp, picks one inbox file, and runs the
    pipeline with apply=True. Verifies the file moves out of inbox/ and
    lands at the planned destination.
    """
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    vault = tmp_path / "vault"
    shutil.copytree(sample, vault)
    inbox_files = sorted((vault / "inbox").glob("*.md"))
    assert inbox_files, "sample vault should have inbox notes"
    src = inbox_files[0]

    llm = FakeLLM(
        responder=_build_responder(
            {
                "classify_para": {"type": "project", "confidence": 0.9, "reason": "ok"},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
                "propose_filename": {
                    "filename": "Phase 3 Smoke.md",
                    "reason": "test name",
                },
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=True)
    assert fr.ok, fr.escalation or fr.error
    assert fr.applied is True
    assert not src.exists()
    moved = vault / "projects/Phase 3 Smoke.md"
    assert moved.exists()
    text = moved.read_text(encoding="utf-8")
    assert "type: project" in text
    assert "[[Health]]" in text
