"""Non-interactive orchestration for benchmark readiness and generation."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from clawsocialarena.scenario.validate import validate_bundle  # noqa: E402
from scripts import generate_benchmark_scaffold  # noqa: E402


_PYTHON = Path(sys.executable)
_EXPECTED_SCENARIO_COUNT = 680
_EXPECTED_STRATA = {
    "main": 630,
    "hard": 25,
    "episode_graph": 20,
    "audit_challenges": 5,
}
_EXPECTED_RESOURCE_COUNT = 675
_EXPECTED_RESOURCE_STRATA = {
    "main": 630,
    "hard": 25,
    "episode_graph": 20,
}
_EXPECTED_RESOURCE_CELLS = {
    ("main", "CU", "scheduling"): 45,
    ("main", "MC", "scheduling"): 45,
    ("main", "AM", "scheduling"): 45,
    ("main", "CD", "consensus"): 45,
    ("main", "MG", "consensus"): 45,
    ("main", "HS", "consensus"): 45,
    ("main", "CM", "consensus"): 45,
    ("main", "CD", "inference"): 45,
    ("main", "MC", "inference"): 45,
    ("main", "AM", "inference"): 45,
    ("main", "CU", "coalition"): 45,
    ("main", "MG", "coalition"): 45,
    ("main", "HS", "coalition"): 45,
    ("main", "CM", "coalition"): 45,
    ("hard", "CU", "code_review"): 12,
    ("hard", "MC", "doc_editing"): 13,
    ("episode_graph", "CD", "inference"): 4,
    ("episode_graph", "CU", "scheduling"): 4,
    ("episode_graph", "MG", "consensus"): 4,
    ("episode_graph", "HS", "coalition"): 4,
    ("episode_graph", "AM", "inference"): 4,
}


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    cwd: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ConstructionSummary:
    mode: str
    profile_source: str
    asb_dataset_version: list[str]
    naturalization_mode: str
    naturalization_model: str | None
    realism_status: str
    missing_resource_construction: list[str]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or generate the canonical ClawSocialArena benchmark."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare",
        help="Run readiness gates into a temporary dataset and write report.json.",
    )
    _add_common_args(prepare)
    prepare.add_argument(
        "--report-dir",
        type=Path,
        default=Path("benchmark/orchestration/latest"),
    )
    prepare.add_argument("--run-full-suite", action="store_true")

    generate = subparsers.add_parser(
        "generate",
        help="Regenerate canonical scaffold data after explicit --yes.",
    )
    _add_common_args(generate)
    generate.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory. Defaults to benchmark/scenarios/<version>.",
    )
    generate.add_argument("--yes", action="store_true")
    generate.add_argument("--run-full-suite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.command == "prepare":
        return _prepare(args)
    if args.command == "generate":
        return _generate(args)
    raise AssertionError(f"unhandled command: {args.command}")


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", type=int, default=1200)
    parser.add_argument("--version", default="v1.0.0")


def _prepare(args: argparse.Namespace) -> int:
    report_dir: Path = args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.json"

    with tempfile.TemporaryDirectory(prefix="clawsocialarena-benchmark-") as tmp:
        out = Path(tmp) / args.version
        report = _run_workflow(
            out=out,
            seed=args.seed,
            version=args.version,
            run_full_suite=args.run_full_suite,
            success_status="READY_TO_GENERATE",
        )
        report["report_path"] = str(report_path)
        _write_report(report_path, report)

    print(report["status"])
    return 0 if report["status"] == "READY_TO_GENERATE" else 1


def _generate(args: argparse.Namespace) -> int:
    out = args.out if args.out is not None else Path("benchmark/scenarios") / args.version
    if not args.yes:
        print(
            "--yes is required for canonical scaffold generation",
            file=sys.stderr,
        )
        return 2

    report = _run_workflow(
        out=out,
        seed=args.seed,
        version=args.version,
        run_full_suite=args.run_full_suite,
        success_status="SCAFFOLD_GENERATED",
    )
    report["report_path"] = str(out / "build_report.json")
    _write_report(out / "build_report.json", report)
    print(report["status"])
    return 0 if report["status"] == "SCAFFOLD_GENERATED" else 1


def _run_workflow(
    *,
    out: Path,
    seed: int,
    version: str,
    run_full_suite: bool,
    success_status: str,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "FAILED",
        "generation_status": "FAILED",
        "seed": seed,
        "version": version,
        "output_path": str(out),
        "dataset": {},
        "validation": {},
        "commands": [],
        "failed_checks": [],
        "errors": [],
        "dataset_role": "scaffold",
        "construction_mode": "unknown",
        "profile_source": "unknown",
        "asb_dataset_version": [],
        "naturalization_mode": "unknown",
        "naturalization_model": None,
        "realism_status": "unknown",
        "release_ready": False,
    }

    try:
        _prepare_generated_output(out)
    except ValueError as exc:
        report["errors"].append(str(exc))
        return report
    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "all",
        "--seed",
        str(seed),
        "--out",
        str(out),
    ])
    if rc != 0:
        report["errors"].append(f"materialization failed with return code {rc}")
        return report

    try:
        dataset, construction_summary = _summarize_dataset(out)
        validation = _validate_indexed_bundles(out)
        _assert_dataset_contract(dataset)
        _assert_construction_contract(construction_summary)
    except ValueError as exc:
        report["dataset"] = locals().get("dataset", {})
        report["validation"] = locals().get("validation", {})
        report["errors"].append(str(exc))
        return report

    report["dataset"] = dataset
    report["validation"] = validation
    _apply_construction_summary(report, construction_summary)

    for command in _check_commands(run_full_suite=run_full_suite):
        result = _run_command(command, cwd=_REPO_ROOT)
        report["commands"].append(asdict(result))
        if result.returncode != 0:
            report["failed_checks"].append(" ".join(command))
            report["errors"].append(
                f"check failed ({result.returncode}): {' '.join(command)}"
            )
            return report

    report["status"] = success_status
    report["generation_status"] = success_status
    report["release_ready"] = (
        success_status == "GENERATED"
        and construction_summary.realism_status == "human_reviewed"
        and not report["failed_checks"]
    )
    return report


def _prepare_generated_output(out: Path) -> None:
    """Remove only known scaffold children before a fresh materialization."""

    if not out.exists():
        out.mkdir(parents=True, exist_ok=True)
        return
    if not _is_safe_generated_output_root(out):
        raise ValueError(
            "refusing to clean existing output without benchmark containment "
            f"or generated build marker: {out}"
        )
    for name in (
        "main",
        "hard",
        "episode_graphs",
        "audit_challenges",
        "index.json",
        "build_report.json",
    ):
        child = out / name
        if child.is_dir():
            shutil.rmtree(child)
        elif child.exists():
            child.unlink()
    out.mkdir(parents=True, exist_ok=True)


def _is_safe_generated_output_root(out: Path) -> bool:
    out_resolved = out.resolve()
    canonical_root = (_REPO_ROOT / "benchmark" / "scenarios").resolve()
    if out_resolved == canonical_root or out_resolved.is_relative_to(canonical_root):
        return True
    return (out / "build_report.json").exists()


def _summarize_dataset(root: Path) -> tuple[dict[str, Any], ConstructionSummary]:
    index_path = root / "index.json"
    if not index_path.exists():
        raise ValueError(f"missing index.json: {index_path}")

    index = json.loads(index_path.read_text())
    rows = list(index.get("rows", []))
    resource_rows: list[dict[str, Any]] = []
    resource_strata: dict[str, int] = {}
    resource_cells: dict[str, int] = {}
    task_schema_v0_count = 0
    main_designed_difficulty_tiers: dict[str, int] = {}
    construction_summary = _summarize_construction(root, rows)

    for row in rows:
        gt_path = root / str(row["bundle_path"]) / "scenario.gt.json"
        gt = json.loads(gt_path.read_text())
        construction = gt.get("construction_manifest")
        if (
            isinstance(construction, dict)
            and construction.get("task_schema_version")
            == "clawsocialarena-task-v0"
        ):
            task_schema_v0_count += 1
        if row.get("stratum") == "main":
            tier = str(row.get("designed_difficulty_tier") or "unknown")
            main_designed_difficulty_tiers[tier] = (
                main_designed_difficulty_tiers.get(tier, 0) + 1
            )
        if not gt.get("resource_manifest"):
            continue
        resource_rows.append(row)
        stratum = str(row["stratum"])
        resource_strata[stratum] = resource_strata.get(stratum, 0) + 1
        cell_key = _cell_key(row)
        resource_cells[cell_key] = resource_cells.get(cell_key, 0) + 1

    return (
        {
            "scenario_count": index.get("scenario_count"),
            "strata": index.get("strata"),
            "resource_count": len(resource_rows),
            "resource_strata": resource_strata,
            "resource_cells": resource_cells,
            "task_schema_v0_count": task_schema_v0_count,
            "main_designed_difficulty_tiers": main_designed_difficulty_tiers,
        },
        construction_summary,
    )


def _summarize_construction(root: Path, rows: list[dict[str, Any]]) -> ConstructionSummary:
    modes: set[str] = set()
    profile_sources: set[str] = set()
    asb_versions: set[str] = set()
    naturalization_modes: set[str] = set()
    naturalization_models: set[str] = set()
    realism_statuses: set[str] = set()
    missing_resource_construction: list[str] = []

    for row in rows:
        gt_path = root / str(row["bundle_path"]) / "scenario.gt.json"
        gt = json.loads(gt_path.read_text())
        construction = gt.get("construction_manifest")
        if not isinstance(construction, dict):
            if gt.get("resource_manifest"):
                missing_resource_construction.append(str(row["scenario_id"]))
            if row.get("stratum") == "audit_challenges":
                profile_sources.add("synthetic_audit_challenge")
            continue

        modes.add(str(construction.get("construction_mode", "unknown")))
        realism_statuses.add(str(construction.get("realism_status", "worldpack_draft")))

        naturalization = construction.get("naturalization")
        if isinstance(naturalization, dict):
            naturalization_modes.add(_naturalization_mode(naturalization))
            model = naturalization.get("llm_model") or naturalization.get("model")
            if model:
                naturalization_models.add(str(model))

        for source in construction.get("profile_sources", []):
            if not isinstance(source, dict):
                continue
            dataset = str(source.get("dataset", "unknown"))
            if dataset == "AgentSocialBench":
                profile_sources.add("agentsocialbench")
                version = source.get("dataset_version")
                if version:
                    asb_versions.add(str(version))
            else:
                profile_sources.add(dataset.lower())

    return ConstructionSummary(
        mode=_collapse_modes(modes),
        profile_source=_collapse_modes(profile_sources),
        asb_dataset_version=sorted(asb_versions),
        naturalization_mode=_collapse_modes(naturalization_modes),
        naturalization_model=_collapse_optional(naturalization_models),
        realism_status=_lowest_realism_status(realism_statuses),
        missing_resource_construction=missing_resource_construction,
    )


def _naturalization_mode(naturalization: dict[str, Any]) -> str:
    method = str(naturalization.get("method") or naturalization.get("mode") or "unknown")
    if method in {
        "structural_world_pack",
        "deterministic",
        "hand_authored_audit_challenge",
    }:
        return "deterministic"
    if naturalization.get("llm_model") or naturalization.get("model"):
        return "llm"
    return method


def _collapse_modes(values: set[str]) -> str:
    if not values:
        return "unknown"
    if len(values) == 1:
        return next(iter(values))
    return "mixed"


def _collapse_optional(values: set[str]) -> str | None:
    if not values:
        return None
    if len(values) == 1:
        return next(iter(values))
    return "mixed"


def _lowest_realism_status(values: set[str]) -> str:
    if not values:
        return "structural_draft"
    order = {
        "structural_draft": 0,
        "worldpack_draft": 1,
        "llm_naturalized": 2,
        "human_reviewed": 3,
    }
    return min(values, key=lambda value: order.get(value, -1))


def _apply_construction_summary(
    report: dict[str, Any],
    summary: ConstructionSummary,
) -> None:
    report["construction_mode"] = summary.mode
    report["profile_source"] = summary.profile_source
    report["asb_dataset_version"] = summary.asb_dataset_version
    report["naturalization_mode"] = summary.naturalization_mode
    report["naturalization_model"] = summary.naturalization_model
    report["realism_status"] = summary.realism_status


def _validate_indexed_bundles(root: Path) -> dict[str, Any]:
    index = json.loads((root / "index.json").read_text())
    errors: list[dict[str, Any]] = []
    for row in index["rows"]:
        report = validate_bundle(root / row["bundle_path"])
        if not report.ok:
            errors.append({
                "scenario_id": row["scenario_id"],
                "errors": report.errors,
            })
    if errors:
        raise ValueError(f"bundle validation failed for {len(errors)} scenario(s)")
    return {
        "validated_count": len(index["rows"]),
        "errors": errors,
    }


def _assert_dataset_contract(dataset: dict[str, Any]) -> None:
    if dataset["scenario_count"] != _EXPECTED_SCENARIO_COUNT:
        raise ValueError(
            f"scenario_count mismatch: {dataset['scenario_count']} "
            f"!= {_EXPECTED_SCENARIO_COUNT}"
        )
    if dataset["strata"] != _EXPECTED_STRATA:
        raise ValueError(f"strata mismatch: {dataset['strata']} != {_EXPECTED_STRATA}")
    if dataset["resource_count"] != _EXPECTED_RESOURCE_COUNT:
        raise ValueError(
            f"resource_count mismatch: {dataset['resource_count']} "
            f"!= {_EXPECTED_RESOURCE_COUNT}"
        )
    if dataset["resource_strata"] != _EXPECTED_RESOURCE_STRATA:
        raise ValueError(
            f"resource_strata mismatch: {dataset['resource_strata']} "
            f"!= {_EXPECTED_RESOURCE_STRATA}"
        )
    expected_cells = {
        "|".join(key): value
        for key, value in _EXPECTED_RESOURCE_CELLS.items()
    }
    if dataset["resource_cells"] != expected_cells:
        raise ValueError(
            f"resource_cells mismatch: {dataset['resource_cells']} "
            f"!= {expected_cells}"
        )
    if dataset["task_schema_v0_count"] != _EXPECTED_SCENARIO_COUNT:
        raise ValueError(
            f"task_schema_v0_count mismatch: {dataset['task_schema_v0_count']} "
            f"!= {_EXPECTED_SCENARIO_COUNT}"
        )
    expected_tiers = {"easy": 210, "realistic": 210, "stress": 210}
    if dataset["main_designed_difficulty_tiers"] != expected_tiers:
        raise ValueError(
            "main_designed_difficulty_tiers mismatch: "
            f"{dataset['main_designed_difficulty_tiers']} != {expected_tiers}"
        )


def _assert_construction_contract(summary: ConstructionSummary) -> None:
    if summary.missing_resource_construction:
        raise ValueError(
            "resource-enabled scenarios missing construction_manifest: "
            + ", ".join(summary.missing_resource_construction[:5])
        )


def _check_commands(*, run_full_suite: bool) -> list[list[str]]:
    benchmark_contract_files = [
        "scripts/generate_benchmark_scaffold.py",
        "scripts/orchestrate_benchmark.py",
        "scripts/task_success_calibration.py",
        "tests/test_scripts/test_generate_benchmark_scaffold.py",
        "tests/test_scripts/test_orchestrate_benchmark.py",
        "tests/test_scripts/test_task_success_calibration.py",
        "tests/test_worlds",
        "tests/test_generator/test_world_pack_instantiation.py",
        "tests/test_generator/test_task_difficulty.py",
        "tests/test_scenario/test_construction_manifest.py",
        "tests/test_scenario/test_validate.py",
        "tests/test_eval/test_eval_runner_v2.py",
        "clawsocialarena/worlds",
        "clawsocialarena/generator/world_pack_instantiation.py",
        "clawsocialarena/generator/task_success_specs.py",
        "clawsocialarena/generator/task_difficulty.py",
        "clawsocialarena/generator/task_patterns.py",
        "clawsocialarena/scenario/models.py",
        "clawsocialarena/scenario/validate.py",
        "clawsocialarena/eval/runner.py",
        "clawsocialarena/eval/tool_evidence.py",
    ]
    commands = [
        [
            str(_PYTHON),
            "-m",
            "pytest",
            *benchmark_contract_files[:12],
            "tests/audit_challenges",
            "-q",
            "-k",
            "not canonical_benchmark_index_matches_current_plan",
        ],
        [
            str(_PYTHON),
            "-m",
            "ruff",
            "check",
            *benchmark_contract_files,
        ],
        [
            str(_PYTHON),
            "-m",
            "mypy",
            *benchmark_contract_files,
        ],
    ]
    if run_full_suite:
        commands.append([str(_PYTHON), "-m", "pytest", "-q"])
    return commands


def _run_command(command: list[str], *, cwd: Path) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandResult(
        command=command,
        cwd=str(cwd),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _cell_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row["stratum"]),
            str(row["category"]),
            str(row["family"]),
        ]
    )


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
