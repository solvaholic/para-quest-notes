"""Smoke tests for ``pqn-daily`` CLI."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from para_quest_notes.workflows.daily import cli as daily_cli
from para_quest_notes.workflows.daily.cli import build_parser, main


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def _config(tmp_path: Path, daily: str = "") -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"run_log_dir: {tmp_path / 'runs'}\n{daily}", encoding="utf-8")
    return cfg


def test_cli_dry_run_text(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "inbox" / "2026-05-12.md").write_text("body\n")
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(["--vault", str(vault), "--config", str(cfg), "2026-05-12"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY-RUN" in out
    assert "would move inbox/2026-05-12.md -> resources/daily_notes/2026/05/2026-05-12.md" in out


def test_cli_apply_json(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "inbox" / "2026-05-12.md").write_text("body\n")
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "2026-05-12",
            "--apply",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["moved"] is True
    assert payload["plan"]["destination"] == "resources/daily_notes/2026/05/2026-05-12.md"
    assert payload["plan"]["h1_inserted"] is True


def test_cli_escalation_returns_one(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "inbox" / "not-a-date.md").write_text("body\n")
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "inbox/not-a-date.md",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["ok"] is False
    assert payload["escalation"]["step"] == "detect_shape"


def test_cli_vault_missing(tmp_path: Path, capsys, monkeypatch):
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(
        [
            "--vault",
            str(tmp_path / "no-such-vault"),
            "--config",
            str(cfg),
            "2026-05-12",
        ]
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "error:" in err


def test_bare_and_today_select_injected_current_date(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    canonical = vault / "resources/daily_notes/2026/09"
    canonical.mkdir(parents=True)
    (canonical / "2026-09-02.md").write_text("# 2026-09-02\n\n", encoding="utf-8")
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    for selector in ([], ["--today"]):
        rc = main(
            ["--vault", str(vault), "--config", str(cfg), "--format", "json", *selector],
            today=date(2026, 9, 2),
        )
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["plan"]["date"] == "2026-09-02"
        assert payload["plan"]["already_at_destination"] is True


def test_date_selects_requested_date_and_rejects_invalid_calendar_date(
    tmp_path: Path, capsys, monkeypatch
):
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--date",
            "2026-09-02",
            "--create-missing",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["date"] == "2026-09-02"

    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--date", "2026-02-31"])
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    "selector", [["2026-09-02", "--today"], ["2026-09-02", "--date", "2026-09-03"]]
)
def test_positional_target_rejects_date_selector(selector: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(selector)
    assert excinfo.value.code == 2


def test_positional_cron_apply_remains_non_opening_by_default(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "inbox/2026-09-02.md").write_text("body\n", encoding="utf-8")
    cfg = _config(tmp_path)

    def unexpected_launch(*args, **kwargs):
        raise AssertionError("positional invocation opened an editor by default")

    monkeypatch.setattr(daily_cli.subprocess, "run", unexpected_launch)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "2026-09-02",
            "--apply",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["moved"] is True
    assert payload["opened"] is False


def test_config_defaults_and_negative_flags_override_enabled_config(
    tmp_path: Path, capsys, monkeypatch
):
    vault = _seed_vault(tmp_path)
    cfg = _config(
        tmp_path,
        "workflows:\n"
        "  daily:\n"
        "    create_missing: true\n"
        "    open_existing: true\n"
        "    editor: [editor]\n",
    )
    launched = False

    def run(*args, **kwargs):
        nonlocal launched
        launched = True

    monkeypatch.setattr(daily_cli.subprocess, "run", run)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--date",
            "2026-09-02",
            "--no-create-missing",
            "--no-open",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert payload["escalation"]["step"] == "resolve_target"
    assert launched is False


def test_positive_flags_override_disabled_config_and_open_created_note(
    tmp_path: Path, capsys, monkeypatch
):
    vault = _seed_vault(tmp_path)
    cfg = _config(
        tmp_path,
        "workflows:\n"
        "  daily:\n"
        "    create_missing: false\n"
        "    open_existing: false\n"
        "    editor: [editor, --wait]\n",
    )
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(daily_cli.subprocess, "run", run)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--date",
            "2026-09-02",
            "--create-missing",
            "--apply",
            "--open",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    destination = vault / "resources/daily_notes/2026/09/2026-09-02.md"

    assert rc == 0
    assert payload["created"] is True
    assert payload["opened"] is True
    assert payload["open_path"] == "resources/daily_notes/2026/09/2026-09-02.md"
    assert calls == [(["editor", "--wait", str(destination)], {"check": True, "shell": False})]


@pytest.mark.parametrize(
    ("apply", "existing_rel", "expected_rel"),
    [
        (False, "inbox/2026-09-02.md", "inbox/2026-09-02.md"),
        (True, "inbox/2026-09-02.md", "resources/daily_notes/2026/09/2026-09-02.md"),
        (
            False,
            "resources/daily_notes/2026/09/2026-09-02.md",
            "resources/daily_notes/2026/09/2026-09-02.md",
        ),
    ],
)
def test_open_uses_real_source_or_destination_path(
    tmp_path: Path,
    capsys,
    monkeypatch,
    apply: bool,
    existing_rel: str,
    expected_rel: str,
):
    vault = _seed_vault(tmp_path)
    existing = vault / existing_rel
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("# 2026-09-02\n\n", encoding="utf-8")
    cfg = _config(tmp_path, "workflows:\n  daily:\n    editor: [editor]\n")
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(daily_cli.subprocess, "run", run)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    argv = [
        "--vault",
        str(vault),
        "--config",
        str(cfg),
        "--format",
        "json",
        "2026-09-02",
        "--open",
    ]
    if apply:
        argv.append("--apply")

    rc = main(argv)
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["opened"] is True
    assert payload["open_path"] == expected_rel
    assert calls == [["editor", str(vault / expected_rel)]]


def test_missing_dry_run_is_planned_but_never_opened(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path, "workflows:\n  daily:\n    editor: [editor]\n")
    launched = False

    def run(*args, **kwargs):
        nonlocal launched
        launched = True

    monkeypatch.setattr(daily_cli.subprocess, "run", run)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--date",
            "2026-09-02",
            "--create-missing",
            "--open",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["plan"]["would_create"] is True
    assert payload["created"] is False
    assert payload["opened"] is False
    assert payload["open_path"] is None
    assert launched is False


def test_missing_editor_fails_clearly(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--date",
            "2026-09-02",
            "--create-missing",
            "--apply",
            "--open",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert payload["ok"] is False
    assert payload["created"] is True
    assert "workflows.daily.editor" in payload["open_error"]
    assert (vault / "resources/daily_notes/2026/09/2026-09-02.md").exists()


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (FileNotFoundError("editor-not-found"), "editor executable not found"),
        (subprocess.CalledProcessError(7, ["editor"]), "exit code 7"),
    ],
)
def test_open_failure_does_not_undo_successful_creation(
    tmp_path: Path, capsys, monkeypatch, failure: BaseException, message: str
):
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path, "workflows:\n  daily:\n    editor: [editor]\n")

    def run(*args, **kwargs):
        raise failure

    monkeypatch.setattr(daily_cli.subprocess, "run", run)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--date",
            "2026-09-02",
            "--create-missing",
            "--apply",
            "--open",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert payload["created"] is True
    assert payload["opened"] is False
    assert message in payload["open_error"]
    assert (vault / "resources/daily_notes/2026/09/2026-09-02.md").exists()


def test_text_output_distinguishes_creation_and_open_failure(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path, "workflows:\n  daily:\n    editor: [missing-editor]\n")

    def run(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(daily_cli.subprocess, "run", run)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--date",
            "2026-09-02",
            "--create-missing",
            "--apply",
            "--open",
        ]
    )
    out = capsys.readouterr().out

    assert rc == 1
    assert "created resources/daily_notes/2026/09/2026-09-02.md" in out
    assert "could not open" in out


def test_config_enables_creation_and_opening_without_cli_policy_flags(
    tmp_path: Path, capsys, monkeypatch
):
    vault = _seed_vault(tmp_path)
    cfg = _config(
        tmp_path,
        "workflows:\n"
        "  daily:\n"
        "    create_missing: true\n"
        "    open_existing: true\n"
        "    editor: [editor]\n",
    )
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(daily_cli.subprocess, "run", run)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--date",
            "2026-09-02",
            "--apply",
        ]
    )
    out = capsys.readouterr().out
    destination = vault / "resources/daily_notes/2026/09/2026-09-02.md"

    assert rc == 0
    assert f"created {destination.relative_to(vault).as_posix()}" in out
    assert f"opened {destination.relative_to(vault).as_posix()}" in out
    assert calls == [["editor", str(destination)]]


def test_text_dry_run_reports_planned_creation_without_claiming_open(
    tmp_path: Path, capsys, monkeypatch
):
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path, "workflows:\n  daily:\n    editor: [editor]\n")

    def unexpected_launch(*args, **kwargs):
        raise AssertionError("dry-run attempted to open a planned path")

    monkeypatch.setattr(daily_cli.subprocess, "run", unexpected_launch)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--date",
            "2026-09-02",
            "--create-missing",
            "--open",
        ]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "would create resources/daily_notes/2026/09/2026-09-02.md" in out
    assert "opened" not in out


def test_malformed_daily_config_exits_two_with_exact_key(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    cfg = _config(
        tmp_path,
        "workflows:\n  daily:\n    open_existing: yes-please\n",
    )
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    rc = main(["--vault", str(vault), "--config", str(cfg)])
    err = capsys.readouterr().err

    assert rc == 2
    assert "workflows.daily.open_existing" in err
