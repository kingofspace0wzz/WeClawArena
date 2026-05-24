#!/usr/bin/env python3
"""Write a live Markdown progress report for the Bedrock 12-model sweep."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUT = ROOT.parents[3] / "docs" / "phase5" / "bedrock_12model_live_results.md"

MODELS = (
    "opus_41_id",
    "opus_47_id",
    "deepseek_r1",
    "deepseek_v32",
    "kimi_k25",
    "kimi_k2_think",
    "minimax_m2",
    "minimax_m25",
    "oss_120b",
    "oss_20b",
    "qwen3_235b",
    "qwen3_32b",
)

DOMAINS = {
    "bargaining": ("BARGAINING_STRESS_RESULTS.jsonl", 120),
    "swebench_workspace": ("BATCH_02_standard_RESULTS.jsonl", 250),
    "travel": ("BATCH_02_standard_RESULTS.jsonl", 100),
}

ATTACK_MODES = (
    "no_attacker",
    "collaboration",
    "security",
    "privacy",
    "governance",
)

PAUSED_MODELS = (
    "deepseek_r1",
    "minimax_m2",
    "minimax_m25",
    "oss_120b",
    "oss_20b",
)

GPT41_MINI_RESULT_FILES = (
    Path("benchmark/phase5/pilot/claw_no_attacker_gpt41mini_fix_20260524_103703/BATCH_02_standard_RESULTS.jsonl"),
    Path("benchmark/phase5/pilot/claw_trading_no_attacker_gpt41mini_fix_20260524_121543/BATCH_02_standard_RESULTS.jsonl"),
    Path("benchmark/phase5/pilot/claw_no_attacker_gpt41mini_rerun_20260523_1215/BATCH_02_standard_RESULTS.jsonl"),
    Path("benchmark/phase5/pilot/claw_no_attacker_gpt41mini_20260522/NO_ATTACKER_RESULTS.jsonl"),
)


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    out = args.out.resolve()
    out.write_text(render(root), encoding="utf-8")
    print(out)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=OUT)
    return parser.parse_args()


def render(root: Path) -> str:
    rows_by_model_domain = load_all_rows(root)
    harness = load_harness_progress(root)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Bedrock Sweep Live Results",
        "",
        f"Last updated: `{now}`",
        "",
        "Notes:",
        "",
        "- Progress counts use main rows plus `_patch_results`, keyed by `variant_id`.",
        "- Non-SWE TSR is `task_success is True / completed rows`.",
        "- SWE-bench TSR uses true harness results when available. Pending strict harness rows are not counted as true TSR yet.",
        "- `oss_20b` is intentionally stopped and excluded from future resume runs.",
        f"- Paused models for new runs: `{', '.join(PAUSED_MODELS)}`.",
        "",
        "## Overall Progress",
        "",
    ]
    lines.extend(progress_table(rows_by_model_domain))
    lines.extend(["", "## TSR By Model And Domain", ""])
    lines.extend(domain_tsr_table(rows_by_model_domain, harness))
    lines.extend(["", "## TSR By Model, Domain, And Attack Mode", ""])
    for model in MODELS:
        lines.extend([f"### {model}", ""])
        lines.extend(model_attack_mode_table(model, rows_by_model_domain, harness))
        lines.append("")
    lines.extend(["## SWE-bench True Harness Progress", ""])
    lines.extend(harness_progress_table(harness))
    lines.extend(["", "## Supplemental gpt-4.1-mini Results", ""])
    lines.extend(gpt41_mini_table(root))
    lines.append("")
    return "\n".join(lines)


def load_all_rows(root: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for model in MODELS:
        for domain, (filename, _expected) in DOMAINS.items():
            by_id: dict[str, dict[str, Any]] = {}
            for base in (root, root / "_patch_results"):
                path = base / model / domain / filename
                for row in read_jsonl(path):
                    variant_id = row.get("variant_id")
                    if variant_id:
                        by_id[str(variant_id)] = row
            out[(model, domain)] = list(by_id.values())
    return out


def load_harness_progress(root: Path) -> dict[str, dict[str, Any]]:
    strict_root = root / "_swebench_harness_strict"
    out: dict[str, dict[str, Any]] = {}
    for model in MODELS:
        model_info = {
            "strict_rows": [],
            "mode_reports": {},
            "predictions": {},
        }
        strict_path = strict_root / model / "strict_accumulator.jsonl"
        model_info["strict_rows"] = read_jsonl(strict_path)
        for mode in ATTACK_MODES:
            mode_dir = strict_root / model / mode
            pred_path = mode_dir / "predictions.jsonl"
            model_info["predictions"][mode] = count_jsonl(pred_path)
            report_path = mode_dir / "strict_report.json"
            if report_path.exists():
                try:
                    model_info["mode_reports"][mode] = json.loads(
                        report_path.read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError:
                    pass
        out[model] = model_info
    return out


def progress_table(rows_by_model_domain: dict[tuple[str, str], list[dict[str, Any]]]) -> list[str]:
    lines = [
        "| model | bargaining | swebench_workspace | travel | total | left |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    grand = 0
    grand_expected = 0
    for model in MODELS:
        cells: list[str] = []
        total = 0
        expected_total = 0
        for domain, (_filename, expected) in DOMAINS.items():
            n = len(rows_by_model_domain[(model, domain)])
            total += n
            expected_total += expected
            cells.append(f"{n}/{expected}")
        grand += total
        grand_expected += expected_total
        lines.append(
            f"| {model} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{total}/{expected_total} | {expected_total - total} |"
        )
    lines.extend(["", f"Total: `{grand}/{grand_expected}`, left `{grand_expected - grand}`."])
    return lines


def domain_tsr_table(
    rows_by_model_domain: dict[tuple[str, str], list[dict[str, Any]]],
    harness: dict[str, dict[str, Any]],
) -> list[str]:
    lines = [
        "| model | bargaining TSR | swebench_workspace true TSR | travel TSR |",
        "|---|---:|---:|---:|",
    ]
    for model in MODELS:
        cells = []
        for domain in DOMAINS:
            rows = rows_for_metric(model, domain, rows_by_model_domain, harness)
            cells.append(format_tsr(rows))
        lines.append(f"| {model} | {cells[0]} | {cells[1]} | {cells[2]} |")
    return lines


def model_attack_mode_table(
    model: str,
    rows_by_model_domain: dict[tuple[str, str], list[dict[str, Any]]],
    harness: dict[str, dict[str, Any]],
) -> list[str]:
    lines = [
        "| domain | no_attacker | collaboration | security | privacy | governance |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for domain in DOMAINS:
        cells = []
        metric_rows = rows_for_metric(model, domain, rows_by_model_domain, harness)
        for mode in ATTACK_MODES:
            mode_rows = [row for row in metric_rows if row.get("attack_mode") == mode]
            cells.append(format_tsr(mode_rows))
        lines.append(
            f"| {domain} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {cells[4]} |"
        )
    return lines


def harness_progress_table(harness: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| model | completed modes | running/started modes | predictions completed/known | true TSR so far |",
        "|---|---:|---|---:|---:|",
    ]
    for model in MODELS:
        info = harness[model]
        completed = [mode for mode in ATTACK_MODES if mode in info["mode_reports"]]
        started = [
            mode
            for mode in ATTACK_MODES
            if info["predictions"].get(mode, 0) or mode in info["mode_reports"]
        ]
        running = [mode for mode in started if mode not in completed]
        pred_known = sum(int(info["predictions"].get(mode, 0)) for mode in started)
        pred_done = sum(int(info["predictions"].get(mode, 0)) for mode in completed)
        rows = rows_with_definite_task(info["strict_rows"])
        lines.append(
            f"| {model} | {len(completed)}/5 ({', '.join(completed) or '-'}) | "
            f"{', '.join(running) or '-'} | {pred_done}/{pred_known} | {format_tsr(rows)} |"
        )
    return lines


def rows_for_metric(
    model: str,
    domain: str,
    rows_by_model_domain: dict[tuple[str, str], list[dict[str, Any]]],
    harness: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if domain != "swebench_workspace":
        return rows_by_model_domain[(model, domain)]
    strict_rows = harness[model]["strict_rows"]
    if strict_rows:
        return rows_with_definite_task(strict_rows)
    return []


def rows_with_definite_task(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if isinstance(row.get("task_success"), bool)]


def format_tsr(rows: list[dict[str, Any]]) -> str:
    n = len(rows)
    if not n:
        return "0/0 (n/a)"
    ok = sum(1 for row in rows if row.get("task_success") is True)
    return f"{ok}/{n} ({ok / n:.1%})"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())


def gpt41_mini_table(root: Path) -> list[str]:
    repo_root = root.parents[3]
    lines = [
        "These prior rows are not part of the Bedrock 12-model totals. They are no-attacker CLAW clinical/trading runs found under `benchmark/phase5/pilot`.",
        "",
        "| source | families | rows | definite | TSR | errors |",
        "|---|---|---:|---:|---:|---:|",
    ]
    found = False
    for rel_path in GPT41_MINI_RESULT_FILES:
        path = repo_root / rel_path
        rows = read_jsonl(path)
        if not rows:
            continue
        found = True
        families = ", ".join(sorted({str(row.get("family_id")) for row in rows}))
        definite = rows_with_definite_task(rows)
        errors = sum(1 for row in rows if row.get("error"))
        source = rel_path.parent.name
        lines.append(
            f"| {source} | {families} | {len(rows)} | {len(definite)} | "
            f"{format_tsr(definite)} | {errors} |"
        )
    if not found:
        lines.append("| - | - | 0 | 0 | 0/0 (n/a) | 0 |")
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
