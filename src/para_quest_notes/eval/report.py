"""Markdown report emitter for an eval run.

Produces a single ``report.md`` plus a CSV of per-cell rows. The
report is the human/agent-facing artifact; the CSV is for ad-hoc
analysis.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from para_quest_notes.eval.registry import DEFAULT_WORKFLOW
from para_quest_notes.eval.runner import CellResult, RunSummary


def _accuracy(cells: list[CellResult]) -> tuple[int, int]:
    passes = sum(1 for c in cells if c.verdict.ok)
    return passes, len(cells)


def _responds_rate(cells: list[CellResult]) -> tuple[int, int]:
    rel = [c for c in cells if c.responds is not None]
    passes = sum(1 for c in rel if c.responds and c.responds.ok)
    return passes, len(rel)


def _step_labels(cells: list[CellResult]) -> tuple[dict[tuple[str, str], str], list[str]]:
    workflows_by_name: dict[str, set[str]] = defaultdict(set)
    for cell in cells:
        workflows_by_name[cell.step].add(cell.workflow)

    by_ref: dict[tuple[str, str], str] = {}
    ordered: list[str] = []
    for cell in cells:
        ref = (cell.workflow, cell.step)
        label = cell.step
        if cell.workflow != DEFAULT_WORKFLOW or len(workflows_by_name[cell.step]) > 1:
            label = f"{cell.workflow}:{cell.step}"
        by_ref[ref] = label
        if label not in ordered:
            ordered.append(label)
    return by_ref, ordered


def render_markdown(summary: RunSummary) -> str:
    """Build the markdown report string."""
    buf: list[str] = []
    started = datetime.fromtimestamp(summary.started_at, tz=UTC)
    duration = max(0.0, summary.finished_at - summary.started_at)
    buf.append("# Eval report")
    buf.append("")
    buf.append(f"- Run start: `{started.isoformat()}`")
    buf.append(f"- Duration: `{duration:.2f}s`")
    buf.append(f"- Fixtures: `{summary.fixture_count}`")
    buf.append(f"- Models: {', '.join(f'`{m}`' for m in summary.models) or '_none_'}")
    buf.append("")

    labels_by_ref, steps_present = _step_labels(summary.cells)
    bucket: dict[tuple[str, str], list[CellResult]] = defaultdict(list)
    for cell in summary.cells:
        bucket[(cell.model, labels_by_ref[(cell.workflow, cell.step)])].append(cell)

    buf.append("## Responds-at-all baseline")
    buf.append("")
    buf.append("Cheap gate: did the model emit parseable JSON for an LLM step?")
    buf.append("")
    if not summary.models:
        buf.append("_No models in run._")
    else:
        buf.append("| Model | Responds rate |")
        buf.append("|---|---|")
        for model in summary.models:
            mc = [c for c in summary.cells if c.model == model]
            p, n = _responds_rate(mc)
            rate = f"{p}/{n} ({_pct(p, n)})" if n else "_n/a_"
            buf.append(f"| `{model}` | {rate} |")
    buf.append("")

    buf.append("## Performance")
    buf.append("")
    buf.append("Per-model wall time and latency, computed from per-cell `latency_ms`")
    buf.append("(LLM steps only; pure-code steps like `plan_destination` are excluded).")
    buf.append("")
    if not summary.models:
        buf.append("_No models in run._")
    else:
        buf.append("| Model | LLM cells | Total | Mean | p50 | p95 | Max |")
        buf.append("|---|---:|---:|---:|---:|---:|---:|")
        for model in summary.models:
            lats = [
                c.run.latency_ms for c in summary.cells if c.model == model and c.run.latency_ms > 0
            ]
            buf.append(
                "| `{m}` | {n} | {tot} | {mean} | {p50} | {p95} | {mx} |".format(
                    m=model,
                    n=len(lats),
                    tot=_fmt_duration_ms(sum(lats)) if lats else "_n/a_",
                    mean=_fmt_duration_ms(sum(lats) / len(lats)) if lats else "_n/a_",
                    p50=_fmt_duration_ms(_percentile(lats, 50)) if lats else "_n/a_",
                    p95=_fmt_duration_ms(_percentile(lats, 95)) if lats else "_n/a_",
                    mx=_fmt_duration_ms(max(lats)) if lats else "_n/a_",
                )
            )
    buf.append("")

    buf.append("## Accuracy by step")
    buf.append("")
    if not steps_present or not summary.models:
        buf.append("_No cells._")
    else:
        header = "| Model | " + " | ".join(steps_present) + " | Overall |"
        sep = "|" + "---|" * (len(steps_present) + 2)
        buf.append(header)
        buf.append(sep)
        for model in summary.models:
            row = [f"`{model}`"]
            total_p = total_n = 0
            for step in steps_present:
                p, n = _accuracy(bucket.get((model, step), []))
                total_p += p
                total_n += n
                row.append(f"{p}/{n} ({_pct(p, n)})" if n else "_n/a_")
            row.append(f"{total_p}/{total_n} ({_pct(total_p, total_n)})" if total_n else "_n/a_")
            buf.append("| " + " | ".join(row) + " |")
    buf.append("")

    buf.append("## Per-step detail")
    buf.append("")
    for step in steps_present:
        buf.append(f"### {step}")
        buf.append("")
        buf.append("| Fixture | Model | Verdict | Reason |")
        buf.append("|---|---|---|---|")
        rows = sorted(
            (c for c in summary.cells if labels_by_ref[(c.workflow, c.step)] == step),
            key=lambda c: (c.fixture_id, c.model),
        )
        for c in rows:
            mark = "✅" if c.verdict.ok else "❌"
            reason = c.verdict.reason or ""
            if c.run.escalation:
                reason = f"escalated: {c.run.escalation.get('reason', '')}"
            elif c.run.error:
                reason = f"error: {c.run.error}"
            buf.append(f"| `{c.fixture_id}` | `{c.model}` | {mark} | {_escape(reason)} |")
        buf.append("")

    return "\n".join(buf).rstrip() + "\n"


def render_csv(summary: RunSummary) -> str:
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "model",
            "temperature",
            "fixture_id",
            "step",
            "verdict_ok",
            "verdict_reason",
            "responds_ok",
            "raw_text",
            "prompt_id",
            "latency_ms",
            "escalation",
            "error",
        ]
    )
    for c in summary.cells:
        writer.writerow(
            [
                c.model,
                c.temperature,
                c.fixture_id,
                c.step,
                int(c.verdict.ok),
                c.verdict.reason,
                "" if c.responds is None else int(c.responds.ok),
                c.run.raw_text or "",
                c.run.prompt_id or "",
                c.run.latency_ms,
                "" if not c.run.escalation else c.run.escalation.get("reason", ""),
                c.run.error or "",
            ]
        )
    return out.getvalue()


def write_report(summary: RunSummary, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "report.md"
    csv_path = out_dir / "rows.csv"
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    csv_path.write_text(render_csv(summary), encoding="utf-8")
    return md_path


def _pct(num: int, den: int) -> str:
    if den == 0:
        return "0%"
    return f"{(100 * num / den):.0f}%"


def _percentile(values: list[int], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _fmt_duration_ms(ms: float) -> str:
    """Human-friendly duration. Picks unit so a reviewer can eyeball ratios."""
    if ms < 1000:
        return f"{ms:.0f} ms"
    secs = ms / 1000.0
    if secs < 60:
        return f"{secs:.2f} s"
    mins, secs = divmod(secs, 60)
    return f"{int(mins)}m {secs:0.1f}s"


def _escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


__all__ = [
    "render_csv",
    "render_markdown",
    "write_report",
]
