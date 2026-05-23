from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from types import ModuleType


def _load_script(name: str) -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_export_predictions_builds_official_patch_jsonl(tmp_path: Path) -> None:
    export = _load_script("export_swebench_workspace_predictions")
    store = tmp_path / "store"
    run = tmp_path / "run" / "variants" / "case__no_attacker"
    base = store / "swebench_workspace" / "case"
    _write_json(
        base / "phase5_metadata.json",
        {"source": {"instance_id": "django__django-1"}},
    )
    before = base / "resources" / "repo" / "worktree" / "pkg" / "file.py"
    before.parent.mkdir(parents=True)
    before.write_text("x = 1\n", encoding="utf-8")
    after = run / "resources" / "repo" / "worktree" / "pkg" / "file.py"
    after.parent.mkdir(parents=True)
    after.write_text("x = 2\n", encoding="utf-8")
    db = run / "resources" / "owners" / "owner" / "db" / "personal.sqlite"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE workspace_runs (changed_files TEXT)")
    conn.execute(
        "INSERT INTO workspace_runs VALUES (?)",
        (json.dumps(["pkg/file.py"]),),
    )
    conn.commit()
    conn.close()

    rows = [
        {
            "variant_id": "case__no_attacker",
            "base_scenario_id": "case",
            "family_id": "swebench_workspace",
            "attack_mode": "no_attacker",
            "task_success": True,
            "extra": {"bundle_dir": str(run)},
        }
    ]
    predictions, mapping = export.export_predictions(
        rows=rows,
        store=store,
        model_name="model",
    )

    assert predictions == [
        {
            "instance_id": "django__django-1",
            "model_name_or_path": "model",
            "model_patch": (
                "diff --git a/pkg/file.py b/pkg/file.py\n"
                "--- a/pkg/file.py\n"
                "+++ b/pkg/file.py\n"
                "@@ -1 +1 @@\n"
                "-x = 1\n"
                "+x = 2\n"
            ),
        }
    ]
    assert mapping[0]["workflow_task_success"] is True


def test_merge_sets_task_success_to_workflow_and_harness() -> None:
    merge = _load_script("merge_swebench_harness_results")
    rows = [
        {
            "variant_id": "case__no_attacker",
            "family_id": "swebench_workspace",
            "attack_mode": "no_attacker",
            "task_success": True,
            "extra": {},
        },
        {
            "variant_id": "case2__no_attacker",
            "family_id": "swebench_workspace",
            "attack_mode": "no_attacker",
            "task_success": False,
            "extra": {},
        },
    ]
    mapping = [
        {"variant_id": "case__no_attacker", "instance_id": "django__django-1"},
        {"variant_id": "case2__no_attacker", "instance_id": "django__django-2"},
    ]
    harness = {
        "django__django-1": {"instance_id": "django__django-1", "resolved": True},
        "django__django-2": {"instance_id": "django__django-2", "resolved": True},
    }

    merged = merge.merge_results(rows=rows, mapping=mapping, harness=harness)

    assert merged[0]["task_success"] is True
    assert merged[0]["extra"]["workflow_task_success"] is True
    assert merged[0]["extra"]["swebench_harness"]["resolved"] is True
    assert merged[1]["task_success"] is False
    assert merged[1]["extra"]["workflow_task_success"] is False


def test_merge_uses_workflow_sidecar_when_task_success_unset() -> None:
    merge = _load_script("merge_swebench_harness_results")
    rows = [
        {
            "variant_id": "case__no_attacker",
            "family_id": "swebench_workspace",
            "attack_mode": "no_attacker",
            "task_success": None,
            "extra": {"workflow_task_success": True},
        },
    ]
    mapping = [
        {"variant_id": "case__no_attacker", "instance_id": "django__django-1"},
    ]
    harness = {
        "django__django-1": {"instance_id": "django__django-1", "resolved": True},
    }

    merged = merge.merge_results(rows=rows, mapping=mapping, harness=harness)

    assert merged[0]["task_success"] is True
    assert merged[0]["extra"]["workflow_task_success"] is True


def test_merge_marks_missing_instance_as_strict_failure() -> None:
    merge = _load_script("merge_swebench_harness_results")
    rows = [
        {
            "variant_id": "case__no_attacker",
            "family_id": "swebench_workspace",
            "attack_mode": "no_attacker",
            "task_success": None,
            "extra": {"workflow_task_success": False},
        },
    ]

    merged = merge.merge_results(rows=rows, mapping=[], harness={})

    assert merged[0]["task_success"] is False
    assert merged[0]["extra"]["workflow_task_success"] is False


def test_merge_mode_filter_preserves_other_modes() -> None:
    merge = _load_script("merge_swebench_harness_results")
    rows = [
        {
            "variant_id": "case__security",
            "family_id": "swebench_workspace",
            "attack_mode": "security",
            "task_success": None,
            "extra": {"workflow_task_success": True},
        },
        {
            "variant_id": "case__privacy",
            "family_id": "swebench_workspace",
            "attack_mode": "privacy",
            "task_success": None,
            "extra": {"workflow_task_success": True},
        },
    ]
    mapping = [
        {"variant_id": "case__security", "instance_id": "django__django-1"},
    ]
    harness = {
        "django__django-1": {"instance_id": "django__django-1", "resolved": True},
    }

    merged = merge.merge_results(
        rows=rows,
        mapping=mapping,
        harness=harness,
        mode="security",
    )

    assert merged[0]["task_success"] is True
    assert merged[1]["task_success"] is None


def test_summarize_only_cli_reports_already_merged_rows(tmp_path: Path) -> None:
    merge = _load_script("merge_swebench_harness_results")
    results = tmp_path / "strict.jsonl"
    rows = [
        {
            "variant_id": "case__security",
            "family_id": "swebench_workspace",
            "attack_mode": "security",
            "task_success": True,
            "extra": {
                "workflow_task_success": True,
                "swebench_harness": {
                    "instance_id": "django__django-1",
                    "resolved": True,
                },
            },
        },
        {
            "variant_id": "case__privacy",
            "family_id": "swebench_workspace",
            "attack_mode": "privacy",
            "task_success": False,
            "extra": {
                "workflow_task_success": True,
                "swebench_harness": {
                    "instance_id": "django__django-2",
                    "resolved": False,
                },
            },
        },
    ]
    results.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    out_results = tmp_path / "strict.out.jsonl"
    out_report = tmp_path / "strict.report.json"

    rc = merge.main(
        [
            str(results),
            "--summarize-only",
            "--out-results",
            str(out_results),
            "--out-report",
            str(out_report),
        ]
    )

    assert rc == 0
    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert report["swebench_workspace"]["security"]["task_success_rate"] == 1.0
    assert report["swebench_workspace"]["privacy"]["task_success_rate"] == 0.0
