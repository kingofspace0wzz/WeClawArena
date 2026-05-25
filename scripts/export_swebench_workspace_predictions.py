"""Export SWE-bench predictions from swebench_workspace run artifacts."""

from __future__ import annotations

import argparse
import difflib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    rows = _read_jsonl(args.results_jsonl)
    selected = [
        row
        for row in rows
        if row.get("family_id") == "swebench_workspace"
        and (args.mode is None or row.get("attack_mode") == args.mode)
        and (
            args.include_workflow_failures
            or _workflow_task_success(row) is True
        )
    ]
    predictions, mapping = export_predictions(
        rows=selected,
        store=args.store,
        model_name=args.model_name,
        on_duplicate=args.on_duplicate,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.out, predictions)
    map_out = args.map_out or args.out.with_suffix(args.out.suffix + ".map.jsonl")
    _write_jsonl(map_out, mapping)
    print(
        json.dumps(
            {
                "predictions": len(predictions),
                "map_rows": len(mapping),
                "predictions_path": str(args.out),
                "map_path": str(map_out),
            },
            sort_keys=True,
        )
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export official SWE-bench prediction JSONL from "
            "swebench_workspace Phase 5 run artifacts."
        )
    )
    parser.add_argument("results_jsonl", type=Path)
    parser.add_argument("--store", type=Path, default=Path("benchmark/scenarios/v2.0.0"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--map-out", type=Path)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--mode", help="Optional attack_mode filter, e.g. no_attacker")
    parser.add_argument(
        "--include-workflow-failures",
        action="store_true",
        help="Also export rows whose workspace workflow task_success is not true.",
    )
    parser.add_argument(
        "--on-duplicate",
        choices=("error", "first", "last"),
        default="error",
        help=(
            "How to handle duplicate SWE-bench instance_id values. Use one "
            "mode per export for official harness runs."
        ),
    )
    return parser


def export_predictions(
    *,
    rows: Iterable[dict[str, Any]],
    store: Path,
    model_name: str,
    on_duplicate: str = "error",
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    by_instance: dict[str, tuple[dict[str, str], dict[str, Any]]] = {}
    for row in rows:
        variant_dir = _variant_dir(row)
        base_dir = _base_bundle_dir(store=store, row=row)
        instance_id = _instance_id(variant_dir=variant_dir, base_dir=base_dir)
        patch = _model_patch(variant_dir=variant_dir, base_dir=base_dir)
        prediction = {
            "instance_id": instance_id,
            "model_name_or_path": model_name,
            "model_patch": patch,
        }
        map_row = {
            "variant_id": row.get("variant_id"),
            "base_scenario_id": row.get("base_scenario_id"),
            "attack_mode": row.get("attack_mode"),
            "instance_id": instance_id,
            "workflow_task_success": _workflow_task_success(row),
            "prediction_exported": bool(patch.strip()),
        }
        if instance_id in by_instance:
            if on_duplicate == "error":
                raise ValueError(
                    f"duplicate instance_id {instance_id!r}; export one mode "
                    "at a time or set --on-duplicate"
                )
            if on_duplicate == "first":
                continue
        by_instance[instance_id] = (prediction, map_row)
    predictions = [item[0] for item in by_instance.values()]
    mapping = [item[1] for item in by_instance.values()]
    return predictions, mapping


def _workflow_task_success(row: dict[str, Any]) -> bool | None:
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    if isinstance(extra.get("workflow_task_success"), bool):
        return extra["workflow_task_success"]
    value = row.get("task_success")
    return value if isinstance(value, bool) else None


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


def _variant_dir(row: dict[str, Any]) -> Path:
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    bundle_dir = extra.get("bundle_dir")
    if not bundle_dir:
        raise ValueError(f"row {row.get('variant_id')!r} has no extra.bundle_dir")
    path = Path(str(bundle_dir))
    return path if path.is_absolute() else Path.cwd() / path


def _base_bundle_dir(*, store: Path, row: dict[str, Any]) -> Path:
    base_id = str(row.get("base_scenario_id") or "")
    family = str(row.get("family_id") or "")
    direct = store / family / base_id
    if direct.is_dir():
        return direct
    matches = [path for path in store.rglob(base_id) if path.is_dir()]
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"could not locate base bundle for {base_id!r}")


def _instance_id(*, variant_dir: Path, base_dir: Path) -> str:
    for root in (variant_dir, base_dir):
        metadata = _read_json(root / "phase5_metadata.json")
        source = metadata.get("source") if isinstance(metadata.get("source"), dict) else {}
        instance_id = source.get("instance_id")
        if instance_id:
            return str(instance_id)
        task_variant = metadata.get("task_variant")
        if isinstance(task_variant, dict):
            loader = task_variant.get("loader_kwargs")
            if isinstance(loader, dict) and loader.get("instance_id"):
                return str(loader["instance_id"])
    repo_metadata = _read_json(base_dir / "resources" / "repo" / "metadata.json")
    if repo_metadata.get("instance_id"):
        return str(repo_metadata["instance_id"])
    raise ValueError(f"missing SWE-bench instance_id for {variant_dir}")


def _model_patch(*, variant_dir: Path, base_dir: Path) -> str:
    changed_files = _changed_files(variant_dir)
    if not changed_files:
        changed_files = _changed_files_by_tree_diff(variant_dir=variant_dir, base_dir=base_dir)
    hunks: list[str] = []
    for rel_path in changed_files:
        hunk = _file_diff(
            rel_path=rel_path,
            before=base_dir / "resources" / "repo" / "worktree" / rel_path,
            after=variant_dir / "resources" / "repo" / "worktree" / rel_path,
        )
        if hunk:
            hunks.append(hunk)
    return "\n".join(hunks)


def _changed_files(variant_dir: Path) -> list[str]:
    owners_dir = variant_dir / "resources" / "owners"
    if not owners_dir.is_dir():
        return []
    for db_path in sorted(owners_dir.glob("*/db/personal.sqlite")):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT changed_files FROM workspace_runs LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            continue
        if row is None:
            continue
        try:
            values = json.loads(row["changed_files"] or "[]")
        except json.JSONDecodeError:
            values = []
        return [str(path) for path in values if path]
    return []


def _changed_files_by_tree_diff(*, variant_dir: Path, base_dir: Path) -> list[str]:
    before_root = base_dir / "resources" / "repo" / "worktree"
    after_root = variant_dir / "resources" / "repo" / "worktree"
    if not before_root.is_dir():
        raise FileNotFoundError(f"missing base worktree: {before_root}")
    if not after_root.is_dir():
        raise FileNotFoundError(f"missing variant worktree: {after_root}")
    before = {
        path.relative_to(before_root).as_posix()
        for path in before_root.rglob("*")
        if path.is_file()
    }
    after = {
        path.relative_to(after_root).as_posix()
        for path in after_root.rglob("*")
        if path.is_file()
    }
    changed: list[str] = []
    for rel_path in sorted(before | after):
        if _read_text(before_root / rel_path) != _read_text(after_root / rel_path):
            changed.append(rel_path)
    return changed


def _file_diff(*, rel_path: str, before: Path, after: Path) -> str:
    before_text = _read_text(before)
    after_text = _read_text(after)
    if before_text == after_text:
        return ""
    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()
    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
        lineterm="",
    )
    body = "\n".join(diff)
    if body:
        body += "\n"
    return f"diff --git a/{rel_path} b/{rel_path}\n{body}"


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
