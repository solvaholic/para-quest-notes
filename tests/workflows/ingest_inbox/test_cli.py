"""Smoke test for the pqn-ingest CLI argparse + dispatch."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from para_quest_notes.workflows.ingest_inbox import cli


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources"):
        (vault / d).mkdir(parents=True)
    (vault / "areas/Health.md").write_text(
        "---\ntype: area\nquest: main\nsupports: ['[[Health]]']\n---\n"
    )
    return vault


def test_cli_dry_run_json(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "inbox/Note.md").write_text("# Note\n")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    fake_responses = iter(
        [
            json.dumps({"type": "project", "confidence": 0.9, "reason": "ok"}),
            json.dumps({"quests": ["Health"], "confidence": 0.9, "reason": "ok"}),
            json.dumps({"filename": "Note.md", "reason": "ok"}),
        ]
    )

    class FakeOllama:
        def __init__(self, *a, **kw):
            pass

        def generate(self, *a, prompt_id=None, **kw):
            from para_quest_notes.adapter.llm import LLMResponse

            return LLMResponse(
                text=next(fake_responses), model="fake", latency_ms=0, prompt_id=prompt_id
            )

    with patch.object(cli, "OllamaClient", FakeOllama):
        rc = cli.main(
            ["--vault", str(vault), "--format", "json", "--config", str(tmp_path / "noconf.yaml")]
        )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["apply"] is False
    assert len(out["files"]) == 1
    assert out["files"][0]["decisions"]["destination"] == "projects/Note.md"


def test_cli_text_dry_run(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "inbox/Note.md").write_text("# Note\n")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    fake_responses = iter(
        [
            json.dumps({"type": "area", "confidence": 0.9}),
            json.dumps({"quests": ["Health"], "confidence": 0.9}),
            json.dumps({"filename": "Note.md"}),
        ]
    )

    class FakeOllama:
        def __init__(self, *a, **kw):
            pass

        def generate(self, *a, prompt_id=None, **kw):
            from para_quest_notes.adapter.llm import LLMResponse

            return LLMResponse(
                text=next(fake_responses), model="fake", latency_ms=0, prompt_id=prompt_id
            )

    with patch.object(cli, "OllamaClient", FakeOllama):
        rc = cli.main(["--vault", str(vault), "--config", str(tmp_path / "noconf.yaml")])
    assert rc == 0
    text = capsys.readouterr().out
    assert "DRY-RUN" in text
    assert "areas/Note.md" in text


def test_cli_returns_nonzero_on_escalation(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "inbox/Note.md").write_text("# Note\n")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    class FakeOllama:
        def __init__(self, *a, **kw):
            pass

        def generate(self, *a, prompt_id=None, **kw):
            from para_quest_notes.adapter.llm import LLMResponse

            return LLMResponse(text="", model="fake", latency_ms=0, prompt_id=prompt_id)

    with patch.object(cli, "OllamaClient", FakeOllama):
        rc = cli.main(["--vault", str(vault), "--config", str(tmp_path / "noconf.yaml")])
    assert rc == 1


def test_cli_skip_rename_flag(tmp_path: Path, capsys, monkeypatch):
    """#33: --skip-rename is accepted and keeps the original filename."""
    vault = _seed_vault(tmp_path)
    (vault / "inbox/train plan.md").write_text("# Train Plan\n")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    fake_responses = iter(
        [
            json.dumps({"type": "project", "confidence": 0.9, "reason": "ok"}),
            json.dumps({"quests": ["Health"], "confidence": 0.9, "reason": "ok"}),
            # No propose_filename response needed - skip_rename bypasses LLM.
        ]
    )

    class FakeOllama:
        def __init__(self, *a, **kw):
            pass

        def generate(self, *a, prompt_id=None, **kw):
            from para_quest_notes.adapter.llm import LLMResponse

            return LLMResponse(
                text=next(fake_responses), model="fake", latency_ms=0, prompt_id=prompt_id
            )

    with patch.object(cli, "OllamaClient", FakeOllama):
        rc = cli.main(
            [
                "--vault",
                str(vault),
                "--format",
                "json",
                "--skip-rename",
                "--config",
                str(tmp_path / "noconf.yaml"),
            ]
        )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["files"][0]["decisions"]["filename"] == "train plan.md"
    assert out["files"][0]["decisions"]["destination"] == "projects/train plan.md"
