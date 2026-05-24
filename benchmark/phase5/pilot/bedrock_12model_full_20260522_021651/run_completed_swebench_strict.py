"""Run official SWE-bench harness for completed swebench_workspace rows."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ATTACK_MODES = (
    "no_attacker",
    "collaboration",
    "security",
    "privacy",
    "governance",
)

PAUSED_MODELS = {
    "deepseek_r1",
    "minimax_m2",
    "minimax_m25",
    "oss_120b",
    "oss_20b",
}


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    work = (root / "_swebench_harness_strict").resolve()
    work.mkdir(parents=True, exist_ok=True)
    completed = completed_result_files(root, models=args.models)
    update_live_results(root)
    print(f"completed_files={len(completed)}", flush=True)
    modes = tuple(args.modes or ATTACK_MODES)
    for result_path in completed:
        model = result_path.parts[-3]
        print(f"model={model} result={result_path}", flush=True)
        strict_path = work / model / "strict_accumulator.jsonl"
        strict_path.parent.mkdir(parents=True, exist_ok=True)
        if not strict_path.exists():
            shutil.copy2(result_path, strict_path)
        for mode in modes:
            run_mode(
                root=root,
                work=work,
                model=model,
                mode=mode,
                strict_path=strict_path,
                max_workers=args.max_workers,
                timeout=args.timeout,
                skip_existing=args.skip_existing,
            )
        shutil.copy2(strict_path, result_path)
        report_path = work / model / "strict_report.json"
        run(
            [
                sys.executable,
                str(Path("scripts/merge_swebench_harness_results.py")),
                str(result_path),
                "--summarize-only",
                "--out-results",
                str(work / model / "strict_summary_copy.jsonl"),
                "--out-report",
                str(report_path),
            ]
        )
        print(f"merged_strict model={model} report={report_path}", flush=True)
        update_live_results(root)
    print("done", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("benchmark/phase5/pilot/bedrock_12model_full_20260522_021651"),
    )
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument(
        "--models",
        nargs="*",
        help="Optional model directory names to evaluate, in the order given.",
    )
    parser.add_argument(
        "--modes",
        nargs="*",
        choices=ATTACK_MODES,
        help="Optional attack modes to evaluate, in the order given.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip mode directories that already have a strict_report.json.",
    )
    return parser.parse_args()


def completed_result_files(root: Path, models: list[str] | None = None) -> list[Path]:
    requested = list(models or [])
    allowed = set(requested)
    paths: list[Path] = []
    for path in sorted(root.glob("*/swebench_workspace/BATCH_02_standard_RESULTS.jsonl")):
        model = path.parts[-3]
        if allowed and model not in allowed:
            continue
        if not allowed and model in PAUSED_MODELS:
            continue
        rows = read_jsonl(path)
        swebench_rows = [row for row in rows if row.get("family_id") == "swebench_workspace"]
        if len(swebench_rows) == 250:
            paths.append(path)
    if requested:
        order = {model: index for index, model in enumerate(requested)}
        paths.sort(key=lambda path: order.get(path.parts[-3], len(order)))
    return paths


def run_mode(
    *,
    root: Path,
    work: Path,
    model: str,
    mode: str,
    strict_path: Path,
    max_workers: int,
    timeout: int,
    skip_existing: bool,
) -> None:
    mode_dir = work / model / mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    mode_report = mode_dir / "strict_report.json"
    if skip_existing and mode_report.exists():
        print(f"mode={model}/{mode} skip_existing={mode_report}", flush=True)
        return
    predictions = mode_dir / "predictions.jsonl"
    mapping = mode_dir / "predictions.jsonl.map.jsonl"
    report_dir = mode_dir / "reports"
    run_id = f"weclaw_strict_{model}_{mode}"
    result_path = root / model / "swebench_workspace" / "BATCH_02_standard_RESULTS.jsonl"
    run(
        [
            sys.executable,
            str(Path("scripts/export_swebench_workspace_predictions.py")),
            str(result_path),
            "--store",
            "benchmark/scenarios/v2.0.0",
            "--mode",
            mode,
            "--model-name",
            model,
            "--out",
            str(predictions),
            "--map-out",
            str(mapping),
            "--on-duplicate",
            "error",
        ]
    )
    n_predictions = count_jsonl(predictions)
    print(f"mode={model}/{mode} predictions={n_predictions}", flush=True)
    harness_input: Path
    if n_predictions:
        harness_report = mode_dir / f"{model}.{run_id}.json"
        if harness_report.exists():
            harness_report.unlink()
        run(
            [
                sys.executable,
                "-m",
                "swebench.harness.run_evaluation",
                "--dataset_name",
                "SWE-bench/SWE-bench_Lite",
                "--predictions_path",
                str(predictions),
                "--max_workers",
                str(max_workers),
                "--timeout",
                str(timeout),
                "--cache_level",
                "env",
                "--clean",
                "False",
                "--run_id",
                run_id,
                "--report_dir",
                str(report_dir),
            ],
            cwd=mode_dir,
        )
        harness_input = find_harness_results(
            report_dir=report_dir,
            fallback_report=harness_report,
        )
    else:
        harness_input = mode_dir / "empty_instance_results.jsonl"
        harness_input.write_text("", encoding="utf-8")
    next_strict = mode_dir / "strict_merged.jsonl"
    run(
        [
            sys.executable,
            str(Path("scripts/merge_swebench_harness_results.py")),
            str(strict_path),
            "--harness-results",
            str(harness_input),
            "--predictions-map",
            str(mapping),
            "--mode",
            mode,
            "--out-results",
            str(next_strict),
            "--out-report",
            str(mode_report),
        ]
    )
    shutil.copy2(next_strict, strict_path)
    update_live_results(root)


def update_live_results(root: Path) -> None:
    script = root / "update_live_results.py"
    if not script.exists():
        return
    run([sys.executable, str(script), "--root", str(root)])


def find_harness_results(*, report_dir: Path, fallback_report: Path) -> Path:
    if fallback_report.exists():
        return fallback_report
    candidates = sorted(report_dir.rglob("instance_results.jsonl"))
    if candidates:
        return candidates[-1]
    candidates = sorted(report_dir.rglob("results.json"))
    if candidates:
        return candidates[-1]
    raise FileNotFoundError(f"no harness result found under {report_dir}")


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run(argv: list[str], *, cwd: Path | None = None) -> None:
    print("+ " + " ".join(argv), flush=True)
    subprocess.run(argv, check=True, cwd=cwd)


if __name__ == "__main__":
    raise SystemExit(main())
