"""Contract tests for template-backed ``pqn-daily`` creation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from para_quest_notes.adapter.completion import complete_templates
from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext
from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.pipeline import create_note
from para_quest_notes.workflows.daily.cli import build_parser, main
from para_quest_notes.workflows.daily.contract import DailyInputs
from para_quest_notes.workflows.daily.pipeline import file_daily_note
from para_quest_notes.workflows.daily.steps import move_file as move_file_step


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for directory in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / directory).mkdir(parents=True)
    return vault


def _write_template(
    vault: Path,
    name: str,
    content: str,
    *,
    directory: str = "resources/templates",
) -> Path:
    template = vault / directory / f"{name}.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text(content, encoding="utf-8")
    return template


def _config(tmp_path: Path, content: str = "") -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(f"run_log_dir: {tmp_path / 'runs'}\n{content}", encoding="utf-8")
    return config


def test_parser_documents_template_flags_and_rejects_both() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    template_action = next(
        action for action in parser._actions if "--template" in action.option_strings
    )

    assert "--template" in help_text
    assert "--no-template" in help_text
    assert template_action.completer is complete_templates
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--template", "daily", "--no-template"])
    assert excinfo.value.code == 2


def test_daily_uses_shared_creation_without_create_internals_or_cli_subprocess() -> None:
    repo = Path(__file__).resolve().parents[3]
    daily_root = repo / "src/para_quest_notes/workflows/daily"

    for path in daily_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "para_quest_notes.workflows.create" not in source
        assert "pqn-create" not in source

    pipeline_paths = [daily_root / "pipeline.py", *(daily_root / "steps").rglob("*.py")]
    for path in pipeline_paths:
        assert "subprocess" not in path.read_text(encoding="utf-8")


def test_no_template_keeps_exact_h1_only_default(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)

    result = file_daily_note(
        DailyInputs(target="2026-09-02", create_missing=True),
        vault=vault,
        apply=True,
    )

    destination = vault / "resources/daily_notes/2026/09/2026-09-02.md"
    assert result.ok is True
    assert result.plan.body_source == "skeleton"
    assert destination.read_bytes() == b"# 2026-09-02\n\n"


@pytest.mark.parametrize(
    ("extra_args", "expected_source", "expected_marker"),
    [
        ([], "template:configured", "configured body"),
        (["--template", "explicit"], "template:explicit", "explicit body"),
        (["--no-template"], "skeleton", None),
    ],
)
def test_explicit_config_override_and_no_template_precedence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    extra_args: list[str],
    expected_source: str,
    expected_marker: str | None,
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, "configured", "# Configured\n\nconfigured body\n")
    _write_template(vault, "explicit", "# Explicit\n\nexplicit body\n")
    config = _config(
        tmp_path,
        "workflows:\n  daily:\n    template: configured\n",
    )
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    code = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(config),
            "--format",
            "json",
            "--date",
            "2026-09-02",
            "--create-missing",
            "--apply",
            *extra_args,
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    written = (vault / "resources/daily_notes/2026/09/2026-09-02.md").read_text(encoding="utf-8")
    assert code == 0
    assert payload["plan"]["body_source"] == expected_source
    if expected_marker is None:
        assert written == "# 2026-09-02\n\n"
    else:
        assert expected_marker in written


def test_template_does_not_enable_creation_or_apply(tmp_path: Path, capsys, monkeypatch) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, "daily", "# $date\n\nRendered.\n")
    config = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    destination = vault / "resources/daily_notes/2026/09/2026-09-02.md"

    disabled_code = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(config),
            "--format",
            "json",
            "--date",
            "2026-09-02",
            "--template",
            "daily",
        ]
    )
    disabled = json.loads(capsys.readouterr().out)
    dry_run_code = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(config),
            "--format",
            "json",
            "--date",
            "2026-09-02",
            "--create-missing",
            "--template",
            "daily",
        ]
    )
    dry_run = json.loads(capsys.readouterr().out)

    assert disabled_code == 1
    assert disabled["escalation"]["step"] == "resolve_target"
    assert dry_run_code == 0
    assert dry_run["created"] is False
    assert dry_run["plan"]["body_source"] == "template:daily"
    assert not destination.exists()


def test_text_output_reports_creation_body_source_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, "daily", "# $date\n\nRendered.\n")
    config = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    code = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(config),
            "--date",
            "2026-09-02",
            "--create-missing",
            "--template",
            "daily",
        ]
    )
    output = capsys.readouterr().out

    assert code == 0
    assert "would create resources/daily_notes/2026/09/2026-09-02.md" in output
    assert "body source: template:daily" in output


def test_dry_run_loads_and_renders_before_any_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, "invalid", "# $date\n\nBody.\n")
    before = sorted(path.relative_to(vault) for path in vault.rglob("*"))

    def fail_render(template_text: str, variables: dict[str, str]) -> str:
        raise ValueError("render failed")

    monkeypatch.setattr("para_quest_notes.workflows.creation.render_template", fail_render)

    with pytest.raises(ValueError, match="render failed"):
        file_daily_note(
            DailyInputs(target="2026-09-02", create_missing=True, template="invalid"),
            vault=vault,
            apply=False,
        )

    assert sorted(path.relative_to(vault) for path in vault.rglob("*")) == before


def test_apply_publishes_once_through_shared_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, "daily", "# $date\n\nBody.\n")
    calls: list[Path] = []
    real_publish = move_file_step.publish_new_note

    def publish(destination: Path, content: str) -> None:
        calls.append(destination)
        real_publish(destination, content)

    monkeypatch.setattr(move_file_step, "publish_new_note", publish)

    result = file_daily_note(
        DailyInputs(target="2026-09-02", create_missing=True, template="daily"),
        vault=vault,
        apply=True,
    )

    assert result.ok is True
    assert len(calls) == 1


def test_selected_templates_are_non_applicable_to_existing_notes(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    destination = vault / "resources/daily_notes/2026/09/2026-09-02.md"
    destination.parent.mkdir(parents=True)
    original = b"# My Existing Daily\n\nUser-owned bytes.\n"
    destination.write_bytes(original)

    result = file_daily_note(
        DailyInputs(
            target="2026-09-02",
            create_missing=True,
            template="missing-template",
        ),
        vault=vault,
        apply=True,
    )

    assert result.ok is True
    assert result.plan.already_at_destination is True
    assert result.plan.body_source is None
    assert destination.read_bytes() == original


def test_whole_note_template_uses_selected_date_and_keeps_metadata_isolated(
    tmp_path: Path,
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(
        vault,
        "daily",
        "---\n"
        "status: $date\n"
        "review_cycle: daily\n"
        "---\n"
        "# Log for $date\n\n"
        "title=$title created=$created year=$year month=$month day=$day\n"
        "literal=$$date unknown=$supports\n",
    )

    result = file_daily_note(
        DailyInputs(target="2031-02-03", create_missing=True, template="daily"),
        vault=vault,
        apply=True,
    )

    destination = vault / "resources/daily_notes/2031/02/2031-02-03.md"
    written = destination.read_text(encoding="utf-8")
    assert result.ok is True
    assert result.plan.h1_inserted is False
    assert result.plan.body_source == "template:daily"
    assert "status: $date" in written
    assert "review_cycle: daily" in written
    assert "type:" not in written
    assert "quest-kind:" not in written
    assert "supports:" not in written
    assert "source_url:" not in written
    assert "created:" not in written
    assert "# Log for 2031-02-03" in written
    assert "title=2031-02-03 created=2031-02-03 year=2031 month=02 day=03" in written
    assert "literal=$date unknown=$supports" in written


def test_legacy_backmatter_migrates_and_frontmatter_wins(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(
        vault,
        "daily",
        "---\nstatus: front\n---\n# $date\n\nBody.\n\n---\nstatus: back\nmood: focused\n---\n",
    )

    result = file_daily_note(
        DailyInputs(target="2026-09-02", create_missing=True, template="daily"),
        vault=vault,
        apply=True,
    )

    written = (vault / "resources/daily_notes/2026/09/2026-09-02.md").read_text(encoding="utf-8")
    assert result.ok is True
    assert "status: front" in written
    assert "mood: focused" in written
    assert written.count("---\n") == 2
    assert written.endswith("# 2026-09-02\n\nBody.\n\n")


def test_malformed_template_metadata_remains_rendered_body(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, "malformed", "---\nstatus: [\n---\n## Notes for $date\n")

    result = file_daily_note(
        DailyInputs(target="2026-09-02", create_missing=True, template="malformed"),
        vault=vault,
        apply=True,
    )

    written = (vault / "resources/daily_notes/2026/09/2026-09-02.md").read_text(encoding="utf-8")
    assert result.ok is True
    assert result.plan.h1_inserted is True
    assert written == "# 2026-09-02\n\n---\nstatus: [\n---\n## Notes for 2026-09-02\n"


def test_missing_h1_is_inserted_but_custom_h1_is_preserved(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, "missing-h1", "## Notes for $date\n")
    _write_template(vault, "custom-h1", "# Journal $date\n\nBody.\n")

    missing = file_daily_note(
        DailyInputs(target="2026-09-02", create_missing=True, template="missing-h1"),
        vault=vault,
        apply=True,
    )
    custom = file_daily_note(
        DailyInputs(target="2026-09-03", create_missing=True, template="custom-h1"),
        vault=vault,
        apply=True,
    )

    assert missing.plan.h1_inserted is True
    assert (
        vault / "resources/daily_notes/2026/09/2026-09-02.md"
    ).read_text() == "# 2026-09-02\n\n## Notes for 2026-09-02\n"
    assert custom.plan.h1_inserted is False
    assert (
        vault / "resources/daily_notes/2026/09/2026-09-03.md"
    ).read_text() == "# Journal 2026-09-03\n\nBody.\n"


def test_missing_template_body_source_matches_create(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)

    daily = file_daily_note(
        DailyInputs(target="2026-09-02", create_missing=True, template="missing"),
        vault=vault,
        apply=True,
    )
    created = create_note(
        CreateInputs(
            title="Create Fallback",
            type="resource",
            template="missing",
        ),
        vault=vault,
        apply=False,
        today="2026-09-02",
    )

    destination = vault / "resources/daily_notes/2026/09/2026-09-02.md"
    assert daily.plan.body_source == created.plan.body_source == "skeleton (template not found)"
    assert destination.read_bytes() == b"# 2026-09-02\n\n"


def test_collision_stops_before_template_loading_or_mutation(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    (vault / "areas/2026-09-02.md").write_text("collision\n", encoding="utf-8")
    before = sorted(path.relative_to(vault) for path in vault.rglob("*"))

    result = file_daily_note(
        DailyInputs(
            target="2026-09-02",
            create_missing=True,
            template="missing-template",
        ),
        vault=vault,
        apply=True,
    )

    assert result.escalation is not None
    assert result.escalation["step"] == "check_collision"
    assert sorted(path.relative_to(vault) for path in vault.rglob("*")) == before


def test_publication_race_preserves_winner_and_reports_no_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _seed_vault(tmp_path)
    _write_template(vault, "daily", "# $date\n\nBody.\n")
    destination = vault / "resources/daily_notes/2026/09/2026-09-02.md"

    def raced_publish(path: Path, content: str) -> None:
        path.write_text("concurrent winner\n", encoding="utf-8")
        raise FileExistsError(path)

    monkeypatch.setattr(move_file_step, "publish_new_note", raced_publish)

    with pytest.raises(EscalateToUser, match="destination already exists"):
        move_file_step.MoveFile(apply=True).run(
            StepContext(
                workflow="daily",
                run_id="test",
                vault=vault,
                scratchpad={
                    "source_abs": None,
                    "destination_abs": destination,
                    "destination_rel": "resources/daily_notes/2026/09/2026-09-02.md",
                    "content": "# 2026-09-02\n\nBody.\n",
                    "content_changed": True,
                    "already_at_destination": False,
                    "creating_missing": True,
                },
            )
        )

    assert destination.read_text(encoding="utf-8") == "concurrent winner\n"


def test_copied_sample_vault_template_cli_smoke(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    vault = tmp_path / "vault"
    shutil.copytree(sample, vault)
    _write_template(
        vault,
        "daily-smoke",
        "---\nstatus: draft\n---\n# Daily $date\n\nMonth $month, literal $$date.\n",
    )
    config = _config(
        tmp_path,
        "workflows:\n"
        "  create:\n"
        "    template_dir: resources/templates\n"
        "  daily:\n"
        "    open_existing: false\n"
        "    template: daily-smoke\n",
    )
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    destination = vault / "resources/daily_notes/2026/09/2026-09-02.md"
    args = [
        "--vault",
        str(vault),
        "--config",
        str(config),
        "--format",
        "json",
        "--date",
        "2026-09-02",
        "--create-missing",
        "--no-open",
    ]

    dry_code = main(args)
    dry_payload = json.loads(capsys.readouterr().out)
    apply_code = main([*args, "--apply"])
    apply_payload = json.loads(capsys.readouterr().out)

    assert dry_code == 0
    assert dry_payload["created"] is False
    assert dry_payload["plan"]["body_source"] == "template:daily-smoke"
    assert apply_code == 0
    assert apply_payload["created"] is True
    assert destination.read_text(encoding="utf-8") == (
        "---\nstatus: draft\n---\n# Daily 2026-09-02\n\nMonth 09, literal $date.\n"
    )
