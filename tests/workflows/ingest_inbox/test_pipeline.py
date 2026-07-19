"""End-to-end pipeline tests with FakeLLM."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from para_quest_notes.adapter.fake_llm import FakeLLM, RecordedCall
from para_quest_notes.workflows.ingest_inbox.contract import IngestResult
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
        "---\ntype: area\nquest-kind: main\nsupports: ['[[Health]]']\n---\n"
    )
    (vault / "areas/Connect.md").write_text(
        "---\ntype: area\nquest-kind: main\nsupports: ['[[Connect]]']\n---\n"
    )
    return vault


def test_ingest_one_dry_run(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "inbox/train plan.md"
    src.write_text("# Train Plan\nrun a 5k\n")
    (vault / "areas/Health.md").write_text(
        (vault / "areas/Health.md").read_text() + "\nsee [[train plan]]\n"
    )

    llm = FakeLLM(
        responder=_build_responder(
            {
                "classify_para": {"type": "project", "confidence": 0.9, "reason": "ok"},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
                "propose_filename": {
                    "choice": "generate",
                    "filename": "Run A 5K.md",
                    "reason": "concise",
                },
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=False)
    assert fr.ok
    assert fr.decisions.para_type == "project"
    assert fr.decisions.quests == ["Health"]
    assert fr.decisions.destination == "projects/Run A 5K.md"
    assert fr.applied is False
    assert src.exists()
    assert any(h["file"] == "areas/Health.md" for h in fr.change.wikilinks_rewritten)


def test_apply_migrates_legacy_quest_key(tmp_path: Path):
    """An inbox note with a legacy ``quest:`` key is migrated to ``quest-kind:``
    on apply (migrate-on-touch, issue #98)."""
    vault = _seed_vault(tmp_path)
    src = vault / "inbox/legacy note.md"
    src.write_text("---\ntype: project\nquest: side\n---\n# Legacy\nplan a 5k\n")

    llm = FakeLLM(
        responder=_build_responder(
            {
                "classify_para": {"type": "project", "confidence": 0.9, "reason": "ok"},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
                "propose_filename": {
                    "choice": "generate",
                    "filename": "Legacy Note.md",
                    "reason": "test name",
                },
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=True)
    assert fr.ok, fr.escalation or fr.error
    text = (vault / "projects/Legacy Note.md").read_text(encoding="utf-8")
    assert "quest-kind: none" in text
    assert "\nquest:" not in text and not text.startswith("quest:")


def test_ingest_one_keeps_identifier_filename(tmp_path: Path):
    # An identifier-style source basename passes the structural check, so
    # propose_filename auto-skips the LLM and keeps the name verbatim.
    vault = _seed_vault(tmp_path)
    src = vault / "inbox/sklearn.linear_model.SGDClassifier.md"
    src.write_text("# SGDClassifier\nestimator notes\n")

    llm = FakeLLM(
        responder=_build_responder(
            {
                "classify_para": {"type": "resource", "confidence": 0.9, "reason": "ok"},
                # pick_quest is skipped for resources; propose_filename
                # auto-skips, so neither prompt should be consulted.
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=True)
    assert fr.ok
    assert fr.decisions.para_type == "resource"
    assert fr.decisions.destination == "resources/sklearn.linear_model.SGDClassifier.md"
    assert (vault / "resources/sklearn.linear_model.SGDClassifier.md").exists()
    assert not src.exists()
    # propose_filename never called the LLM for this source.
    assert not any((call.prompt_id or "").startswith("propose_filename@") for call in llm.calls)


def test_ingest_inbox_processes_all_files(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "inbox/note a.md").write_text("# A\nI want to plan a garden project.\n")
    (vault / "inbox/note b.md").write_text("# B\nI want to research composting methods.\n")

    plans = iter(
        [
            {
                "classify_para": {"type": "project", "confidence": 0.9},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9},
                "propose_filename": {"choice": "generate", "filename": "Alpha.md"},
            },
            {
                "classify_para": {"type": "resource", "confidence": 0.9},
                "pick_quest": {},  # skipped for resource
                "propose_filename": {"choice": "generate", "filename": "Bravo.md"},
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


def test_ingest_one_uses_preset_frontmatter_type(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "inbox/train plan.md"
    src.write_text("---\ntype: project\n---\n# Train Plan\nrun a 5k\n")

    llm = FakeLLM(
        responder=_build_responder(
            {
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
                "propose_filename": {
                    "choice": "generate",
                    "filename": "Run A 5K.md",
                    "reason": "concise",
                },
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=False)

    assert fr.ok
    assert fr.decisions.para_type == "project"
    assert fr.decisions.destination == "projects/Run A 5K.md"
    assert not any((call.prompt_id or "").startswith("classify_para@") for call in llm.calls)


def test_ingest_one_keeps_good_source_filename(tmp_path: Path):
    """When the inbox source basename already passes the structural check,
    propose_filename skips the LLM and reuses the source name.
    """
    vault = _seed_vault(tmp_path)
    src = vault / "inbox/Chat With DeepWiki About Goose 2026-05-15.md"
    src.write_text("# Chat\nDiscussed recipe execution.\n")

    llm = FakeLLM(
        responder=_build_responder(
            {
                "classify_para": {"type": "resource", "confidence": 0.9, "reason": "ok"},
                # propose_filename intentionally absent — must not be invoked.
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=False)

    assert fr.ok, fr.escalation or fr.error
    assert fr.decisions.filename == "Chat With DeepWiki About Goose 2026-05-15.md"
    assert fr.decisions.destination == ("resources/Chat With DeepWiki About Goose 2026-05-15.md")
    assert not any((call.prompt_id or "").startswith("propose_filename@") for call in llm.calls)


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
                    "choice": "generate",
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


def test_apply_mode_sample_vault_invariants(tmp_path: Path):
    """Smoke the whole inbox of the bundled sample vault with ``--apply``.

    This is the CI regression fence for issue #21 (motivated by #18,
    where a same-basename move spuriously rewrote wikilinks). ``pytest``
    and ``pqn-eval --fake`` are green-but-insufficient for workflow
    changes because no test asserts on the *production* output shape;
    this one does, against a real copy of ``samples/vault/``.

    Every file is classified as ``resource`` so ``pick_quest`` is skipped
    (the test isn't coupled to the vault's quest names) and each note
    lands at ``resources/<name>.md``. The sample's sentence-case inbox
    basenames fail ``propose_filename``'s structural check, so the fake
    LLM returns the mechanically-repaired Title Case name parsed back out
    of the rendered prompt -- a real move that exercises the apply path.

    On top of the real corpus the test seeds one same-stem case: a
    Title Case inbox note (which ``propose_filename`` keeps verbatim) plus
    a separate note that wikilinks to it. That reproduces #18 directly --
    on the pre-fix code the same-stem move would still "rewrite" that
    link.

    Invariants asserted (issue #21):

    1. Every file processes cleanly: ``ok`` is True, no ``error``, no
       ``escalation``.
    2. Regression fence: for every applied change whose ``moved_from``
       and ``moved_to`` share a basename stem, ``wikilinks_rewritten``
       is empty.
    3. Every ``moved_to`` resolves to an existing file post-apply.
    4. Every ``moved_from`` no longer exists post-apply.
    5. Every ``attachments_moved`` destination references an existing
       file.
    6. At least one file was processed and the inbox is drained.
    """
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    vault = tmp_path / "vault"
    shutil.copytree(sample, vault)

    # Seed the #18 same-stem case: a Title Case inbox note (kept verbatim
    # by propose_filename) plus a note that wikilinks to it. Post-apply the
    # link must survive untouched and wikilinks_rewritten must be empty.
    same_stem = "Linked Title Note"
    (vault / "inbox" / f"{same_stem}.md").write_text(f"# {same_stem}\nbody\n")
    backlink = vault / "resources" / "Backlink Source.md"
    backlink.write_text(f"# Backlink Source\nsee [[{same_stem}]] for context\n")

    repaired_re = re.compile(r"repaired basename:\s*(.+\.md)\s*$", re.MULTILINE)

    def responder(call: RecordedCall) -> str:
        pid = call.prompt_id or ""
        if pid.startswith("classify_para@"):
            return json.dumps({"type": "resource", "confidence": 0.95, "reason": "smoke"})
        if pid.startswith("propose_filename@"):
            m = repaired_re.search(call.prompt)
            assert m, "propose_filename prompt should expose the repaired basename"
            return json.dumps({"choice": "repair", "filename": m.group(1), "reason": "smoke"})
        # pick_quest is skipped for resources; nothing else should be asked.
        return json.dumps({})

    llm = FakeLLM(responder=responder)
    result: IngestResult = ingest_inbox(vault, llm=llm, apply=True)

    # Invariant 6: at least one file processed; inbox drained.
    assert result.files, "sample vault should have inbox notes"
    assert not list((vault / "inbox").glob("*.md")), "inbox should be drained after --apply"

    saw_same_stem = False
    for f in result.files:
        # Invariant 1: clean processing on the happy-path corpus.
        assert f.ok, f.escalation or f.error
        assert f.error is None
        assert f.escalation is None
        assert f.applied is True
        assert f.change is not None
        change = f.change

        moved_from = vault / change.moved_from
        moved_to = vault / change.moved_to
        from_stem = Path(change.moved_from).stem
        to_stem = Path(change.moved_to).stem

        # Invariant 2: same basename => no wikilink rewrites (the #18 fence).
        if from_stem == to_stem:
            saw_same_stem = True
            assert change.wikilinks_rewritten == [], (
                f"{change.moved_from} -> {change.moved_to} kept its basename "
                f"but rewrote wikilinks: {change.wikilinks_rewritten}"
            )

        # Invariants 3 & 4: destination exists, source is gone.
        assert moved_to.exists(), f"moved_to does not exist: {change.moved_to}"
        assert not moved_from.exists(), f"moved_from still exists: {change.moved_from}"

        # Invariant 5: every recorded attachment destination exists.
        for _src, dst in change.attachments_moved:
            assert (vault / dst).exists(), f"attachment destination missing: {dst}"

    # The seeded same-stem note must have actually been processed, and its
    # incoming wikilink must survive the move byte-for-byte.
    assert saw_same_stem, "seeded same-basename move was not exercised"
    assert (vault / "resources" / f"{same_stem}.md").exists()
    assert f"[[{same_stem}]]" in backlink.read_text(encoding="utf-8")


def test_skip_rename_keeps_original_filename(tmp_path: Path):
    """#33: --skip-rename keeps the original filename without LLM or structural check."""
    vault = _seed_vault(tmp_path)
    src = vault / "inbox/train plan.md"
    src.write_text("# Train Plan\nrun a 5k\n")

    llm = FakeLLM(
        responder=_build_responder(
            {
                "classify_para": {"type": "project", "confidence": 0.9, "reason": "ok"},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=True, skip_rename=True)

    assert fr.ok, fr.escalation or fr.error
    assert fr.applied is True
    # Original filename kept even though it fails the structural check.
    assert fr.decisions.filename == "train plan.md"
    assert fr.decisions.destination == "projects/train plan.md"
    assert (vault / "projects/train plan.md").exists()
    assert not src.exists()
    # propose_filename never called the LLM.
    assert not any((call.prompt_id or "").startswith("propose_filename@") for call in llm.calls)


def test_skip_rename_still_checks_collisions(tmp_path: Path):
    """#33: --skip-rename still escalates on filename collision."""
    vault = _seed_vault(tmp_path)
    src = vault / "inbox/Health.md"
    src.write_text("# Health\nan inbox note about health\n")
    # areas/Health.md already exists from _seed_vault

    llm = FakeLLM(
        responder=_build_responder(
            {
                "classify_para": {"type": "area", "confidence": 0.9, "reason": "ok"},
                "pick_quest": {"quests": ["Health"], "confidence": 0.9, "reason": "ok"},
            }
        )
    )
    fr = ingest_one(src, vault=vault, llm=llm, apply=True, skip_rename=True)

    assert not fr.ok
    assert fr.escalation is not None
    assert fr.escalation["step"] == "propose_filename"
    assert "collides" in fr.escalation["reason"]
