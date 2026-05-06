"""Tests for the non-interactive benchmark orchestration runner."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import orchestrate_benchmark


def _successful_command(
    command: list[str],
    *,
    cwd: Path,
) -> orchestrate_benchmark.CommandResult:
    return orchestrate_benchmark.CommandResult(
        command=command,
        cwd=str(cwd),
        returncode=0,
        stdout="ok",
        stderr="",
    )


def test_prepare_writes_ready_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_dir = tmp_path / "report"
    monkeypatch.setattr(orchestrate_benchmark, "_run_command", _successful_command)

    rc = orchestrate_benchmark.main([
        "prepare",
        "--seed",
        "1200",
        "--version",
        "v1.0.0",
        "--report-dir",
        str(report_dir),
    ])

    assert rc == 0
    report = json.loads((report_dir / "report.json").read_text())
    assert report["status"] == "READY_TO_GENERATE"
    assert report["generation_status"] == "READY_TO_GENERATE"
    assert report["dataset_role"] == "scaffold"
    assert report["construction_mode"] in {"world_pack", "mixed"}
    assert report["profile_source"] in {"agentsocialbench", "mixed"}
    assert report["asb_dataset_version"]
    assert report["naturalization_mode"] == "deterministic"
    assert report["realism_status"] == "worldpack_draft"
    assert report["release_ready"] is False
    assert report["dataset"]["scenario_count"] == 680
    assert report["dataset"]["strata"] == {
        "main": 630,
        "hard": 25,
        "episode_graph": 20,
        "audit_challenges": 5,
    }
    assert report["dataset"]["resource_count"] == 675
    assert report["dataset"]["task_schema_v0_count"] == 680
    assert report["dataset"]["main_designed_difficulty_tiers"] == {
        "easy": 210,
        "realistic": 210,
        "stress": 210,
    }
    assert report["validation"]["validated_count"] == 680
    assert all(result["returncode"] == 0 for result in report["commands"])


def test_generate_requires_yes(
    tmp_path: Path,
    capsys,
) -> None:
    out = tmp_path / "canonical"

    rc = orchestrate_benchmark.main([
        "generate",
        "--seed",
        "1200",
        "--version",
        "v1.0.0",
        "--out",
        str(out),
    ])

    assert rc == 2
    assert not out.exists()
    assert "--yes is required" in capsys.readouterr().err


def test_generate_with_yes_writes_build_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out = tmp_path / "canonical"
    monkeypatch.setattr(orchestrate_benchmark, "_run_command", _successful_command)

    rc = orchestrate_benchmark.main([
        "generate",
        "--yes",
        "--seed",
        "1200",
        "--version",
        "v1.0.0",
        "--out",
        str(out),
    ])

    assert rc == 0
    assert (out / "index.json").exists()
    report = json.loads((out / "build_report.json").read_text())
    assert report["status"] == "SCAFFOLD_GENERATED"
    assert report["generation_status"] == "SCAFFOLD_GENERATED"
    assert report["dataset_role"] == "scaffold"
    assert report["release_ready"] is False
    assert report["dataset"]["scenario_count"] == 680
    assert report["dataset"]["resource_count"] == 675
    assert report["dataset"]["task_schema_v0_count"] == 680
    assert report["output_path"] == str(out)


def test_generate_with_yes_removes_stale_generated_children(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out = tmp_path / "canonical"
    stale_bundle = out / "main" / "stale-scenario"
    stale_bundle.mkdir(parents=True)
    (stale_bundle / "scenario.json").write_text("{}")
    (out / "build_report.json").write_text(json.dumps({"status": "OLD"}))
    monkeypatch.setattr(orchestrate_benchmark, "_run_command", _successful_command)

    rc = orchestrate_benchmark.main([
        "generate",
        "--yes",
        "--seed",
        "1200",
        "--version",
        "v1.0.0",
        "--out",
        str(out),
    ])

    assert rc == 0
    assert not stale_bundle.exists()
    assert (out / "index.json").exists()


def test_generate_refuses_to_clean_existing_unmarked_custom_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out = tmp_path / "not-a-generated-root"
    out.mkdir()
    (out / "notes.txt").write_text("do not delete")
    monkeypatch.setattr(orchestrate_benchmark, "_run_command", _successful_command)

    rc = orchestrate_benchmark.main([
        "generate",
        "--yes",
        "--seed",
        "1200",
        "--version",
        "v1.0.0",
        "--out",
        str(out),
    ])

    assert rc == 1
    assert (out / "notes.txt").exists()


def test_prepare_records_failed_check(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_dir = tmp_path / "report"

    def command_runner(
        command: list[str],
        *,
        cwd: Path,
    ) -> orchestrate_benchmark.CommandResult:
        if "ruff" in command:
            return orchestrate_benchmark.CommandResult(
                command=command,
                cwd=str(cwd),
                returncode=1,
                stdout="",
                stderr="ruff failed",
            )
        return _successful_command(command, cwd=cwd)

    monkeypatch.setattr(orchestrate_benchmark, "_run_command", command_runner)

    rc = orchestrate_benchmark.main([
        "prepare",
        "--seed",
        "1200",
        "--version",
        "v1.0.0",
        "--report-dir",
        str(report_dir),
    ])

    assert rc == 1
    report = json.loads((report_dir / "report.json").read_text())
    assert report["status"] == "FAILED"
    assert report["generation_status"] == "FAILED"
    assert any(result["returncode"] == 1 for result in report["commands"])
    assert report["failed_checks"]
    assert "ruff failed" in json.dumps(report["commands"])


def test_check_commands_cover_task_schema_evaluator_and_calibration_files() -> None:
    command_text = "\n".join(
        " ".join(command)
        for command in orchestrate_benchmark._check_commands(run_full_suite=False)
    )

    for path in (
        "clawsocialarena/scenario/models.py",
        "clawsocialarena/scenario/validate.py",
        "clawsocialarena/eval/runner.py",
        "clawsocialarena/eval/tool_evidence.py",
        "clawsocialarena/generator/task_success_specs.py",
        "clawsocialarena/generator/task_difficulty.py",
        "clawsocialarena/generator/task_patterns.py",
        "scripts/task_success_calibration.py",
    ):
        assert path in command_text
