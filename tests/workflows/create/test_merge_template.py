"""Lossless template + stdin merge tests for ``pqn-create`` (#49)."""

from __future__ import annotations

import io
import json
import re
import shutil
from pathlib import Path

import pytest

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.fake_llm import FakeLLM, RecordedCall
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.workflows.create import cli
from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.pipeline import create_note
from para_quest_notes.workflows.validate.api import validate_paths


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for directory in ("inbox", "areas", "projects", "resources/templates", "archive"):
        (vault / directory).mkdir(parents=True)
    return vault


def _write_template(vault: Path, name: str = "structured", body: str | None = None) -> Path:
    path = vault / "resources" / "templates" / f"{name}.md"
    path.write_text(
        body
        or (
            "---\n"
            "status: draft\n"
            "---\n"
            "# $title\n\n"
            "Template introduction stays here.\n\n"
            "## Goals\n\n"
            "- Existing goal\n\n"
            "## Notes\n\n"
            "Existing note.\n"
        ),
        encoding="utf-8",
    )
    return path


def _inputs(
    *,
    body: str | None = "First input block.\n",
    template: str | None = "structured",
) -> CreateInputs:
    return CreateInputs(
        title="Merged Project",
        type="project",
        supports=["[[Health]]"],
        body=body,
        template=template,
        merge_template=True,
    )


def _routing(*section_ids: str) -> str:
    return json.dumps(
        {
            "placements": [
                {"block_id": f"block-{index:03d}", "section_id": section_id}
                for index, section_id in enumerate(section_ids, start=1)
            ]
        }
    )


def test_merge_requires_non_empty_stdin_without_calling_llm_or_writing(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault)
    llm = FakeLLM()

    result = create_note(
        _inputs(body=None),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok is False
    assert result.escalation is not None
    assert result.escalation["step"] == "merge_template"
    assert "non-empty stdin" in result.escalation["reason"]
    assert result.plan.template_merge is not None
    assert result.plan.template_merge.status == "failed"
    assert result.written is False
    assert llm.calls == []
    assert not (vault / "projects/Merged Project.md").exists()


def test_merge_requires_a_selected_template_without_calling_llm_or_writing(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    llm = FakeLLM()

    result = create_note(
        _inputs(template=None),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok is False
    assert result.escalation is not None
    assert result.escalation["step"] == "merge_template"
    assert "selected template" in result.escalation["reason"]
    assert result.written is False
    assert llm.calls == []


def test_merge_requires_selected_template_to_exist_without_calling_llm(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    llm = FakeLLM()

    result = create_note(
        _inputs(template="missing"),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok is False
    assert result.escalation is not None
    assert result.escalation["step"] == "merge_template"
    assert "not found" in result.escalation["reason"]
    assert result.written is False
    assert llm.calls == []


def test_merge_routes_to_nested_and_duplicate_headings_by_stable_id(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(
        vault,
        body=(
            "# Merged Project\n\n"
            "Opening stays.\n\n"
            "## Notes\n\n"
            "First notes body.\n\n"
            "### Detail\n\n"
            "Detail body.\n\n"
            "## Notes\n\n"
            "Second notes body.\n"
        ),
    )
    llm = FakeLLM()
    llm.queue(_routing("section-003", "section-004"))

    result = create_note(
        _inputs(body="Nested detail text.\n\nSecond notes text.\n"),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    written = (vault / "projects/Merged Project.md").read_text(encoding="utf-8")
    assert (
        written.index("### Detail")
        < written.index("Nested detail text.")
        < written.index("## Notes", written.index("### Detail"))
    )
    second_notes = written.rindex("## Notes")
    assert second_notes < written.index("Second notes text.")
    assert written.count("Nested detail text.") == 1
    assert written.count("Second notes text.") == 1
    assert "First notes body." in written
    assert "Detail body." in written
    assert "Second notes body." in written

    prompt = llm.calls[0].prompt
    assert '"id": "section-002"' in prompt
    assert '"id": "section-004"' in prompt
    assert re.search(
        r'"path":\s*\[\s*"Merged Project",\s*"Notes",\s*"Detail"\s*\]',
        prompt,
    )


def test_merge_preserves_rendered_blocks_and_accounts_for_unsorted_content(
    tmp_path: Path,
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault)
    llm = FakeLLM()
    llm.queue(_routing("section-002", "unsorted"))
    stdin = "Goal for $title costs $$5.\nSecond line stays.\n\n$UNKNOWN cannot be placed.\n"

    result = create_note(
        _inputs(body=stdin),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    assert result.plan.body_source == "merged-template:structured"
    assert result.plan.template_merge is not None
    assert result.plan.template_merge.status == "merged"
    assert result.plan.template_merge.template == "structured"
    assert result.plan.template_merge.input_blocks == 2
    assert result.plan.template_merge.routed_blocks == 1
    assert result.plan.template_merge.unsorted_blocks == 1

    written = (vault / "projects/Merged Project.md").read_text(encoding="utf-8")
    rendered_goal = "Goal for Merged Project costs $5.\nSecond line stays."
    assert written.count(rendered_goal) == 1
    assert written.count("$UNKNOWN cannot be placed.") == 1
    assert "## Unsorted\n\n$UNKNOWN cannot be placed." in written
    assert "Template introduction stays here." in written
    assert "- Existing goal" in written


def test_merge_uses_existing_unsorted_heading(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, body="# Merged Project\n\n## Unsorted\n\nExisting.\n")
    llm = FakeLLM()
    llm.queue(_routing("unsorted"))

    result = create_note(
        _inputs(),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    written = (vault / "projects/Merged Project.md").read_text(encoding="utf-8")
    assert written.count("## Unsorted") == 1
    assert written.index("Existing.") < written.index("First input block.")


def test_existing_unsorted_heading_keeps_mixed_assignment_source_order(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, body="# Merged Project\n\n## Unsorted\n\nExisting.\n")
    llm = FakeLLM()
    llm.queue(_routing("unsorted", "section-002"))

    result = create_note(
        _inputs(body="First by source order.\n\nSecond by source order.\n"),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    written = (vault / "projects/Merged Project.md").read_text(encoding="utf-8")
    assert written.index("First by source order.") < written.index("Second by source order.")


def test_fenced_stdin_with_blank_lines_stays_one_routable_block(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault)
    llm = FakeLLM()
    llm.queue(_routing("section-003"))
    fenced = "```markdown\n# Code sample\n\n## Not a source heading\n```\n"

    result = create_note(
        _inputs(body=fenced),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    assert result.plan.template_merge is not None
    assert result.plan.template_merge.input_blocks == 1
    written = (vault / "projects/Merged Project.md").read_text(encoding="utf-8")
    assert fenced in written


def test_list_contained_fenced_stdin_with_blank_lines_stays_one_block(
    tmp_path: Path,
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault)
    llm = FakeLLM()
    llm.queue(_routing("section-003", "unsorted"))
    fenced = "- Example:\n    ```markdown\n    first line\n\n    ## Not a source heading\n    ```\n"

    result = create_note(
        _inputs(body=f"{fenced}\nTrailing block.\n"),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    assert result.plan.template_merge is not None
    assert result.plan.template_merge.input_blocks == 2
    written = (vault / "projects/Merged Project.md").read_text(encoding="utf-8")
    assert fenced in written
    assert written.count("Trailing block.") == 1


def test_list_contained_template_fence_does_not_create_phantom_sections(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(
        vault,
        body=("# Merged Project\n\n- ```markdown\n  ## Code Heading\n  ```\n\n## Real Notes\n"),
    )
    llm = FakeLLM()
    llm.queue(_routing("section-002"))

    result = create_note(
        _inputs(),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    prompt = llm.calls[0].prompt
    assert '"heading": "Code Heading"' not in prompt
    assert '"heading": "Real Notes"' in prompt
    written = (vault / "projects/Merged Project.md").read_text(encoding="utf-8")
    assert "  ## Code Heading" in written
    assert written.index("## Real Notes") < written.index("First input block.")


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ("not json", "valid JSON"),
        (json.dumps([]), "not an object"),
        (json.dumps({}), "required key 'placements'"),
        (
            json.dumps(
                {
                    "placements": [
                        {"block_id": "block-001", "section_id": "section-002"},
                    ]
                }
            ),
            "account for every stdin block",
        ),
        (
            json.dumps(
                {
                    "placements": [
                        {"block_id": "block-001", "section_id": "section-002"},
                        {"block_id": "block-001", "section_id": "section-003"},
                    ]
                }
            ),
            "duplicate block_id",
        ),
        (
            json.dumps(
                {
                    "placements": [
                        {"block_id": "block-001", "section_id": "section-999"},
                        {"block_id": "block-002", "section_id": "section-003"},
                    ]
                }
            ),
            "unknown section_id",
        ),
        (
            json.dumps(
                {
                    "placements": [
                        {
                            "block_id": "block-001",
                            "section_id": "section-002",
                            "rewritten_text": "changed",
                        },
                        {"block_id": "block-002", "section_id": "section-003"},
                    ]
                }
            ),
            "unexpected key",
        ),
    ],
)
def test_unusable_model_output_escalates_before_write(
    tmp_path: Path,
    response: str,
    reason: str,
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault)
    llm = FakeLLM()
    llm.queue(response)

    result = create_note(
        _inputs(body="First.\n\nSecond.\n"),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok is False
    assert result.escalation is not None
    assert result.escalation["step"] == "merge_template"
    assert reason in result.escalation["reason"]
    assert result.written is False
    assert len(llm.calls) == 1
    assert not (vault / "projects/Merged Project.md").exists()


def test_merge_dry_run_calls_llm_but_does_not_write(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault)
    llm = FakeLLM()
    llm.queue(_routing("section-003"))

    result = create_note(
        _inputs(),
        vault=vault,
        apply=False,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    assert result.written is False
    assert result.plan.template_merge is not None
    assert result.plan.template_merge.status == "merged"
    assert len(llm.calls) == 1
    assert not (vault / "projects/Merged Project.md").exists()


def test_merge_keeps_frontmatter_deterministic_and_out_of_the_prompt(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(
        vault,
        body=(
            "---\n"
            "type: area\n"
            "quest-kind: side\n"
            "supports: ['[[Wrong]]']\n"
            "created: 1999-01-01\n"
            "status: private-draft-marker\n"
            "---\n"
            "# $title\n\n"
            "## Notes\n\n"
            "Existing.\n"
        ),
    )

    def responder(call: RecordedCall) -> str:
        assert "private-draft-marker" not in call.prompt
        assert "quest-kind: side" not in call.prompt
        return _routing("section-002")

    llm = FakeLLM(responder=responder)
    result = create_note(
        _inputs(),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    assert result.plan.frontmatter == {
        "type": "project",
        "quest-kind": "none",
        "supports": ["[[Health]]"],
        "created": "2026-09-04",
        "status": "private-draft-marker",
    }


def test_merge_uses_configured_default_template(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, name="project-default")
    llm = FakeLLM()
    llm.queue(_routing("section-003"))
    config = Config(
        workflows={
            "create": {
                "defaults": {
                    "project": "project-default",
                }
            }
        }
    )

    result = create_note(
        _inputs(template=None),
        vault=vault,
        apply=False,
        llm=llm,
        config=config,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    assert result.plan.template_merge is not None
    assert result.plan.template_merge.template == "project-default"
    assert result.plan.body_source == "merged-template:project-default"


def test_without_merge_flag_stdin_still_wins_without_loading_template_or_calling_llm(
    tmp_path: Path,
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault)
    llm = FakeLLM()

    result = create_note(
        CreateInputs(
            title="Ordinary Stdin",
            type="project",
            supports=["[[Health]]"],
            body="# Ordinary Stdin\n\n$UNKNOWN and $$5.\n",
            template="structured",
        ),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    assert result.ok, result.escalation or result.error
    assert result.plan.body_source == "stdin"
    assert result.plan.template_merge is None
    assert "status" not in result.plan.frontmatter
    assert llm.calls == []
    written = (vault / "projects/Ordinary Stdin.md").read_text(encoding="utf-8")
    assert written.endswith("# Ordinary Stdin\n\n$UNKNOWN and $5.\n")
    assert "Template introduction" not in written


def test_cli_merge_flag_reads_stdin_and_reports_json_provenance(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault)
    config = tmp_path / "config.yaml"
    config.write_text(f"run_log_dir: {tmp_path / 'runs'}\n", encoding="utf-8")
    llm = FakeLLM()
    llm.queue(_routing("section-003"))
    monkeypatch.setattr(cli, "OllamaClient", lambda **_kwargs: llm)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("CLI block.\n"))

    rc = cli.main(
        [
            "--vault",
            str(vault),
            "--config",
            str(config),
            "--format",
            "json",
            "--type",
            "project",
            "--title",
            "Merged Project",
            "--supports",
            "[[Health]]",
            "--template",
            "structured",
            "--merge-template",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["written"] is False
    assert payload["plan"]["body_source"] == "merged-template:structured"
    assert payload["plan"]["template_merge"] == {
        "status": "merged",
        "template": "structured",
        "input_blocks": 1,
        "routed_blocks": 1,
        "unsorted_blocks": 0,
    }
    assert len(llm.calls) == 1


def test_cli_text_reports_merge_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault)
    config = tmp_path / "config.yaml"
    config.write_text(f"run_log_dir: {tmp_path / 'runs'}\n", encoding="utf-8")
    llm = FakeLLM()
    llm.queue(_routing("section-003"))
    monkeypatch.setattr(cli, "OllamaClient", lambda **_kwargs: llm)

    rc = cli.main(
        [
            "--vault",
            str(vault),
            "--config",
            str(config),
            "--type",
            "project",
            "--title",
            "Merged Project",
            "--supports",
            "[[Health]]",
            "--template",
            "structured",
            "--merge-template",
        ],
        stdin="CLI block.\n",
    )

    output = capsys.readouterr().out
    assert rc == 0
    assert "template merge: merged" in output
    assert "1 routed, 0 unsorted" in output


def test_merge_trace_records_raw_and_parsed_routing_plan(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault)
    response = _routing("section-003")
    llm = FakeLLM()
    llm.queue(response)
    trace_path = tmp_path / "trace.jsonl"

    with TraceWriter(trace_path) as trace:
        result = create_note(
            _inputs(),
            vault=vault,
            apply=False,
            llm=llm,
            trace=trace,
            today="2026-09-04",
        )

    assert result.ok, result.escalation or result.error
    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    event = next(record for record in records if record.get("event") == "llm.complete")
    assert event["step"] == "merge_template"
    assert event["prompt_id"].startswith("merge_template@")
    assert event["prompt_hash"]
    assert event["raw_output"] == response
    assert event["parsed_output"] == json.loads(response)


def test_merge_apply_smoke_on_copied_sample_vault(tmp_path: Path) -> None:
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    vault = tmp_path / "vault"
    shutil.copytree(sample, vault)
    (vault / "resources/templates").mkdir(parents=True, exist_ok=True)
    _write_template(vault)
    llm = FakeLLM()
    llm.queue(_routing("section-002", "unsorted"))

    result = create_note(
        _inputs(body="Keep this exact goal.\n\nKeep this unmatched detail.\n"),
        vault=vault,
        apply=True,
        llm=llm,
        today="2026-09-04",
    )

    destination = vault / "projects/Merged Project.md"
    assert result.ok, result.escalation or result.error
    assert result.written is True
    assert result.plan.destination == "projects/Merged Project.md"
    assert result.plan.frontmatter["type"] == "project"
    assert result.plan.frontmatter["supports"] == ["[[Health]]"]
    assert result.plan.template_merge is not None
    assert result.plan.template_merge.input_blocks == (
        result.plan.template_merge.routed_blocks + result.plan.template_merge.unsorted_blocks
    )
    written = destination.read_text(encoding="utf-8")
    assert written.count("Keep this exact goal.") == 1
    assert written.count("Keep this unmatched detail.") == 1
    assert "Template introduction stays here." in written
    assert validate_paths(vault, [destination]).issues == []
