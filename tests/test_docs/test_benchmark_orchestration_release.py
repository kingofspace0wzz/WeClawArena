"""Release-path tests for benchmark orchestration docs and CI."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_readme_points_to_category_sweep_batch_run() -> None:
    content = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    start = content.index("## Current Benchmark Next Step")
    end = content.index("## License")
    next_step = content[start:end]

    assert "scripts/naturalize_and_run_batch.py" in next_step
    assert "--batch-strategy category-sweep" in next_step
    assert "--sweep-index 0" in next_step
    assert "--batch-size 70" in next_step
    assert "scripts/generate_main_150.py" not in next_step


def test_benchmark_orchestration_workflow_runs_prepare_only() -> None:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "benchmark-orchestration.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    steps = workflow["jobs"]["benchmark-orchestration"]["steps"]
    uses = [step["uses"] for step in steps if "uses" in step]
    runs = [step["run"] for step in steps if "run" in step]

    assert "actions/checkout@v5" in uses
    assert "actions/setup-python@v6" in uses
    assert any("scripts/orchestrate_benchmark.py prepare" in run for run in runs)
    assert not any("scripts/orchestrate_benchmark.py generate" in run for run in runs)
