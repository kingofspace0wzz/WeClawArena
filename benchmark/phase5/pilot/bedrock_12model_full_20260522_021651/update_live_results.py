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
    "sonnet_45_id",
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

REPORT_DOMAINS = {
    "bargaining": 120,
    "swebench_workspace": 250,
    "travel": 100,
    "bidding": 60,
    "clinical": 50,
    "trading": 40,
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

BIDDING_V2_1_ROOT = Path(
    "benchmark/phase5/pilot/bidding_v2_1_0_11model_20260524_105507"
)
CLAW_BEDROCK_ROOT = Path("benchmark/phase5/pilot/claw_bedrock_8model_20260524_140017")
BIDDING_V2_1_MODELS = (
    "deepseek_v32",
    "kimi_k25",
    "kimi_k2_think",
    "opus_41_id",
    "opus_47_id",
    "qwen3_235b",
    "qwen3_32b",
    "sonnet_45_id",
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
    asr = load_llm_asr(root)
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
        "- LLM-ASR is `llm_judge_*_asr.attack_success_aggregate is True / judged attacker-mode rows` where a post-hoc judge exists.",
        "- Clinical and trading attack-success cells use the runner's per-row `attack_success` field because those domains do not yet have a post-hoc LLM judge output in this sweep.",
        "- `oss_20b` is intentionally stopped and excluded from future resume runs.",
        f"- Paused models for new runs: `{', '.join(PAUSED_MODELS)}`.",
        "- `bidding` is MARBLE bidding v2.1.0; `clinical` and `trading` are the CLaw Bedrock sweep.",
        "",
        "## Overall Progress",
        "",
    ]
    lines.extend(progress_table(rows_by_model_domain))
    lines.extend(["", "## TSR By Model And Domain", ""])
    lines.extend(domain_tsr_table(rows_by_model_domain, harness))
    lines.extend(["", "## TSR By Attack Mode", ""])
    for mode in ATTACK_MODES:
        lines.extend([f"### {mode}", ""])
        lines.extend(attack_mode_tsr_table(mode, rows_by_model_domain, harness))
        lines.append("")
    lines.extend(["## LLM-ASR Progress", ""])
    lines.extend(llm_asr_progress_table(asr))
    lines.extend(["", "## LLM-ASR / Attack Success By Attack Mode", ""])
    for mode in ATTACK_MODES[1:]:
        lines.extend([f"### {mode}", ""])
        lines.extend(attack_mode_asr_table(mode, asr))
        lines.append("")
    lines.extend(["## SWE-bench True Harness Progress", ""])
    lines.extend(harness_progress_table(harness))
    lines.extend(["", "## Supplemental gpt-4.1-mini Results", ""])
    lines.extend(gpt41_mini_table(root))
    lines.append("")
    return "\n".join(lines)


def load_all_rows(root: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    repo_root = root.parents[3]
    for model in MODELS:
        for domain in REPORT_DOMAINS:
            by_id: dict[str, dict[str, Any]] = {}
            if domain in DOMAINS:
                filename, _expected = DOMAINS[domain]
                for base in (root, root / "_patch_results"):
                    path = base / model / domain / filename
                    for row in read_jsonl(path):
                        variant_id = row.get("variant_id")
                        if variant_id:
                            by_id[str(variant_id)] = row
            elif domain == "bidding":
                path = repo_root / BIDDING_V2_1_ROOT / model / "BATCH_02_standard_RESULTS.jsonl"
                for row in read_jsonl(path):
                    variant_id = row.get("variant_id")
                    if variant_id:
                        by_id[str(variant_id)] = row
            elif domain in {"clinical", "trading"}:
                family = "claw_clinical" if domain == "clinical" else "claw_trading"
                path = repo_root / CLAW_BEDROCK_ROOT / model / "BATCH_02_standard_RESULTS.jsonl"
                for row in read_jsonl(path):
                    if row.get("family_id") != family:
                        continue
                    variant_id = row.get("variant_id")
                    if variant_id:
                        by_id[str(variant_id)] = row
            out[(model, domain)] = list(by_id.values())
    return out


def load_llm_asr(root: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    repo_root = root.parents[3]
    asr_root = root / "_llm_asr"
    for model in MODELS:
        for domain in REPORT_DOMAINS:
            if domain in DOMAINS:
                path = asr_root / model / f"{domain}_attack_modes_ASR.jsonl"
                out[(model, domain)] = read_jsonl(path)
            elif domain == "bidding":
                path = (
                    repo_root
                    / BIDDING_V2_1_ROOT
                    / model
                    / "BATCH_02_standard_RESULTS.bidding_asr.jsonl"
                )
                out[(model, domain)] = read_jsonl(path)
            elif domain in {"clinical", "trading"}:
                family = "claw_clinical" if domain == "clinical" else "claw_trading"
                path = repo_root / CLAW_BEDROCK_ROOT / model / "BATCH_02_standard_RESULTS.jsonl"
                out[(model, domain)] = [
                    row for row in read_jsonl(path) if row.get("family_id") == family
                ]
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
        "| model | bargaining | swebench_workspace | travel | bidding | clinical | trading | total | left |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    grand = 0
    grand_expected = 0
    for model in MODELS:
        cells: list[str] = []
        total = 0
        expected_total = 0
        for domain, expected in REPORT_DOMAINS.items():
            n = len(rows_by_model_domain[(model, domain)])
            total += n
            expected_total += expected
            cells.append(f"{n}/{expected}")
        grand += total
        grand_expected += expected_total
        lines.append(
            f"| {model} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | "
            f"{cells[4]} | {cells[5]} | "
            f"{total}/{expected_total} | {expected_total - total} |"
        )
    lines.extend(["", f"Total: `{grand}/{grand_expected}`, left `{grand_expected - grand}`."])
    return lines


def domain_tsr_table(
    rows_by_model_domain: dict[tuple[str, str], list[dict[str, Any]]],
    harness: dict[str, dict[str, Any]],
) -> list[str]:
    lines = [
        "| model | bargaining | swebench true | travel | bidding | clinical | trading |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        cells = []
        for domain in REPORT_DOMAINS:
            rows = rows_for_metric(model, domain, rows_by_model_domain, harness)
            cells.append(format_tsr(rows))
        lines.append(
            f"| {model} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{cells[3]} | {cells[4]} | {cells[5]} |"
        )
    return lines


def attack_mode_tsr_table(
    mode: str,
    rows_by_model_domain: dict[tuple[str, str], list[dict[str, Any]]],
    harness: dict[str, dict[str, Any]],
) -> list[str]:
    lines = [
        "| model | bargaining | swebench true | travel | bidding | clinical | trading |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        cells = []
        for domain in REPORT_DOMAINS:
            metric_rows = rows_for_metric(model, domain, rows_by_model_domain, harness)
            mode_rows = [row for row in metric_rows if row.get("attack_mode") == mode]
            cells.append(format_tsr(mode_rows))
        lines.append(
            f"| {model} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{cells[3]} | {cells[4]} | {cells[5]} |"
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


def llm_asr_progress_table(asr: dict[tuple[str, str], list[dict[str, Any]]]) -> list[str]:
    lines = [
        "| model | bargaining | swebench_workspace | travel | bidding | clinical | trading | total judged |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        cells: list[str] = []
        total = 0
        for domain in REPORT_DOMAINS:
            rows = [
                row
                for row in asr[(model, domain)]
                if row.get("attack_mode") in ATTACK_MODES[1:] and asr_row_judged(row)
            ]
            expected = expected_asr_rows(domain)
            total += len(rows)
            cells.append(f"{len(rows)}/{expected}")
        lines.append(
            f"| {model} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | "
            f"{cells[4]} | {cells[5]} | {total} |"
        )
    return lines


def attack_mode_asr_table(
    mode: str,
    asr: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[str]:
    lines = [
        "| model | bargaining | swebench_workspace | travel | bidding | clinical | trading |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        cells: list[str] = []
        for domain in REPORT_DOMAINS:
            rows = asr[(model, domain)]
            mode_rows = [row for row in rows if row.get("attack_mode") == mode]
            cells.append(format_asr(mode_rows))
        lines.append(
            f"| {model} | {cells[0]} | {cells[1]} | {cells[2]} | "
            f"{cells[3]} | {cells[4]} | {cells[5]} |"
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


def expected_asr_rows(domain: str) -> int:
    expected_total = REPORT_DOMAINS[domain]
    return expected_total - (expected_total // len(ATTACK_MODES))


def format_asr(rows: list[dict[str, Any]]) -> str:
    rows = [row for row in rows if asr_row_judged(row)]
    n = len(rows)
    if not n:
        return "0/0 (n/a)"
    ok = sum(1 for row in rows if llm_asr_success(row))
    return f"{ok}/{n} ({ok / n:.1%})"


def asr_row_judged(row: dict[str, Any]) -> bool:
    mode = row.get("attack_mode")
    bidding = row.get("llm_judge_bidding_asr")
    if isinstance(bidding, dict):
        axes = bidding.get("axes")
        if isinstance(axes, dict) and isinstance(mode, str):
            verdict = axes.get(mode)
            if isinstance(verdict, dict):
                return verdict.get("attack_success") is not None
        return bidding.get("attack_success_aggregate") is not None
    for key in (
        "llm_judge_bargaining_asr",
        "llm_judge_workspace_asr",
        "llm_judge_travel_asr",
    ):
        value = row.get(key)
        if isinstance(value, dict):
            return value.get("attack_success_aggregate") is not None
    return isinstance(row.get("attack_success"), bool)


def llm_asr_success(row: dict[str, Any]) -> bool:
    mode = row.get("attack_mode")
    bidding = row.get("llm_judge_bidding_asr")
    if isinstance(bidding, dict):
        axes = bidding.get("axes")
        if isinstance(axes, dict) and isinstance(mode, str):
            verdict = axes.get(mode)
            if isinstance(verdict, dict):
                return verdict.get("attack_success") is True
        return bidding.get("attack_success_aggregate") is True
    for key in (
        "llm_judge_bargaining_asr",
        "llm_judge_workspace_asr",
        "llm_judge_travel_asr",
    ):
        value = row.get(key)
        if isinstance(value, dict):
            return value.get("attack_success_aggregate") is True
    if isinstance(row.get("attack_success"), bool):
        return row.get("attack_success") is True
    return False


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


def bidding_v2_1_section(repo_root: Path) -> list[str]:
    bidding_root = repo_root / BIDDING_V2_1_ROOT
    lines = [
        f"Source root: `{BIDDING_V2_1_ROOT}`.",
        "",
        "The v2.1.0 bidding run completed and was LLM-ASR judged for the keep-list models below. `deepseek_r1` was stopped after partial artifacts and is not included in the final judged table. `minimax_m2`, `minimax_m25`, `oss_120b`, and `oss_20b` were not run for bidding v2.1.0.",
        "",
        "### Bidding Progress",
        "",
        "| model | rows | judged rows | turn-cap outcomes |",
        "|---|---:|---:|---:|",
    ]
    rows_by_model = {
        model: read_jsonl(
            bidding_root / model / "BATCH_02_standard_RESULTS.bidding_asr.jsonl"
        )
        for model in BIDDING_V2_1_MODELS
    }
    for model in BIDDING_V2_1_MODELS:
        rows = rows_by_model[model]
        result_rows = read_jsonl(
            bidding_root / model / "BATCH_02_standard_RESULTS.jsonl"
        )
        turn_caps = sum(1 for row in rows if row.get("hit_turn_cap"))
        lines.append(
            f"| {model} | {len(result_rows)}/60 | {len(rows)}/60 | {turn_caps} |"
        )

    lines.extend(
        [
            "",
            "### Bidding TSR By Mode",
            "",
            "| model | no_attacker | collaboration | security | privacy | governance |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for model in BIDDING_V2_1_MODELS:
        rows = rows_by_model[model]
        cells = [
            format_tsr([row for row in rows if row.get("attack_mode") == mode])
            for mode in ATTACK_MODES
        ]
        lines.append(
            f"| {model} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {cells[4]} |"
        )

    lines.extend(
        [
            "",
            "### Bidding LLM-ASR By Attack Mode",
            "",
            "| model | collaboration | security | privacy | governance |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for model in BIDDING_V2_1_MODELS:
        rows = rows_by_model[model]
        cells = [format_bidding_asr(rows, mode) for mode in ATTACK_MODES[1:]]
        lines.append(f"| {model} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |")
    return lines


def format_bidding_asr(rows: list[dict[str, Any]], mode: str) -> str:
    mode_rows = [row for row in rows if row.get("attack_mode") == mode]
    n = len(mode_rows)
    if not n:
        return "0/0 (n/a)"
    ok = 0
    for row in mode_rows:
        axes = (row.get("llm_judge_bidding_asr") or {}).get("axes") or {}
        verdict = axes.get(mode) or {}
        if verdict.get("attack_success") is True:
            ok += 1
    return f"{ok}/{n} ({ok / n:.1%})"


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
