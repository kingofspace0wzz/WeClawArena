"""Merge official SWE-bench harness outcomes into Phase 5 results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    rows = _read_jsonl(args.results_jsonl)
    if args.summarize_only:
        merged = rows
    else:
        if not args.harness_results:
            raise SystemExit("--harness-results is required unless --summarize-only is set")
        mapping = _read_jsonl(args.predictions_map) if args.predictions_map else []
        harness = load_harness_results(args.harness_results)
        merged = merge_results(
            rows=rows,
            mapping=mapping,
            harness=harness,
            mode=args.mode,
        )
    args.out_results.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.out_results, merged)
    report = summarize(merged)
    if args.out_report:
        args.out_report.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    print(json.dumps(report, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Set swebench_workspace task_success to workflow success AND "
            "official SWE-bench harness resolution."
        )
    )
    parser.add_argument("results_jsonl", type=Path)
    parser.add_argument("--harness-results", type=Path)
    parser.add_argument("--predictions-map", type=Path)
    parser.add_argument("--out-results", type=Path, required=True)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument(
        "--mode",
        help="Only merge rows for one attack_mode; other modes are preserved.",
    )
    parser.add_argument(
        "--summarize-only",
        action="store_true",
        help=(
            "Do not merge a new harness result. Write the existing rows back "
            "and emit a summary report over already-merged strict outcomes."
        ),
    )
    return parser


def merge_results(
    *,
    rows: Iterable[dict[str, Any]],
    mapping: Iterable[dict[str, Any]],
    harness: dict[str, dict[str, Any]],
    mode: str | None = None,
) -> list[dict[str, Any]]:
    variant_to_instance = {
        str(row.get("variant_id")): str(row.get("instance_id"))
        for row in mapping
        if row.get("variant_id") and row.get("instance_id")
    }
    merged: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item.get("family_id") != "swebench_workspace":
            merged.append(item)
            continue
        if mode is not None and item.get("attack_mode") != mode:
            merged.append(item)
            continue
        instance_id = variant_to_instance.get(str(item.get("variant_id")))
        if not instance_id and not variant_to_instance:
            instance_id = _instance_id_from_row(item)
        workflow_task_success = _workflow_task_success(item)
        if not instance_id:
            item["task_success"] = False
            extra = dict(item.get("extra") if isinstance(item.get("extra"), dict) else {})
            extra["workflow_task_success"] = workflow_task_success
            item["extra"] = extra
            merged.append(item)
            continue
        harness_row = harness.get(instance_id) or {}
        resolved = _resolved(harness_row)
        item["task_success"] = bool(workflow_task_success is True and resolved is True)
        extra = dict(item.get("extra") if isinstance(item.get("extra"), dict) else {})
        extra["workflow_task_success"] = workflow_task_success
        extra["swebench_harness"] = {
            "instance_id": instance_id,
            "resolved": resolved,
            "raw": harness_row,
        }
        item["extra"] = extra
        merged.append(item)
    return merged


def load_harness_results(path: Path) -> dict[str, dict[str, Any]]:
    files: list[Path]
    if path.is_dir():
        files = sorted(path.rglob("instance_results.jsonl"))
        files.extend(sorted(path.rglob("results.json")))
    else:
        files = [path]
    out: dict[str, dict[str, Any]] = {}
    for file_path in files:
        if file_path.suffix == ".jsonl":
            for row in _read_jsonl(file_path):
                instance_id = row.get("instance_id")
                if instance_id:
                    out[str(instance_id)] = row
            continue
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for key in ("instance_results", "results"):
                values = payload.get(key)
                if isinstance(values, list):
                    for row in values:
                        if isinstance(row, dict) and row.get("instance_id"):
                            out[str(row["instance_id"])] = row
            for key in ("resolved_ids", "resolved"):
                values = payload.get(key)
                if isinstance(values, list):
                    for instance_id in values:
                        out[str(instance_id)] = {
                            "instance_id": str(instance_id),
                            "resolved": True,
                        }
            values = payload.get("unresolved_ids")
            if isinstance(values, list):
                for instance_id in values:
                    out.setdefault(
                        str(instance_id),
                        {"instance_id": str(instance_id), "resolved": False},
                    )
            values = payload.get("error_ids")
            if isinstance(values, list):
                for instance_id in values:
                    out.setdefault(
                        str(instance_id),
                        {
                            "instance_id": str(instance_id),
                            "resolved": None,
                            "error": True,
                        },
                    )
    return out


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("family_id") != "swebench_workspace":
            continue
        mode = str(row.get("attack_mode") or "unknown")
        bucket = buckets.setdefault(
            mode,
            {
                "n": 0,
                "task_success_count": 0,
                "n_task_definite": 0,
                "workflow_task_success_count": 0,
                "harness_resolved_count": 0,
                "harness_missing_count": 0,
            },
        )
        bucket["n"] += 1
        if row.get("task_success") is not None:
            bucket["n_task_definite"] += 1
            if row.get("task_success") is True:
                bucket["task_success_count"] += 1
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        if extra.get("workflow_task_success") is True:
            bucket["workflow_task_success_count"] += 1
        harness = extra.get("swebench_harness")
        if isinstance(harness, dict) and harness.get("resolved") is True:
            bucket["harness_resolved_count"] += 1
        if isinstance(harness, dict) and harness.get("resolved") is None:
            bucket["harness_missing_count"] += 1
    for bucket in buckets.values():
        denom = bucket["n_task_definite"]
        bucket["task_success_rate"] = (
            round(bucket["task_success_count"] / denom, 4) if denom else None
        )
    return {"swebench_workspace": buckets}


def _workflow_task_success(row: dict[str, Any]) -> bool | None:
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    if isinstance(extra.get("workflow_task_success"), bool):
        return extra["workflow_task_success"]
    value = row.get("task_success")
    return value if isinstance(value, bool) else None


def _resolved(row: dict[str, Any]) -> bool | None:
    for key in ("resolved", "is_resolved"):
        if isinstance(row.get(key), bool):
            return row[key]
    nested = row.get("result")
    if isinstance(nested, dict):
        return _resolved(nested)
    return None


def _instance_id_from_row(row: dict[str, Any]) -> str:
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    context = extra.get("workspace_context")
    if isinstance(context, dict) and context.get("instance_id"):
        return str(context["instance_id"])
    harness = extra.get("swebench_harness")
    if isinstance(harness, dict) and harness.get("instance_id"):
        return str(harness["instance_id"])
    return ""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True))
            fh.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
