"""CLI tests (Task D7).

The generator CLI emits a full v2 scenario bundle per scenario id:

- ``scenario.json``
- ``scenario.gt.json``
- ``docker-compose.yml``
- ``personas/<agent_id>.system.md`` + ``.tools.json``
- ``mcp/<tool>.json``  (empty dir when the template declares no tools)

These tests exercise the CLI via both ``cli_main(argv)`` (fast) and an
out-of-process subprocess invocation (smoke test: asserts the argv surface
matches the spec).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from clawsocialarena.generator.cli import main as cli_main
from clawsocialarena.scenario.loader import ScenarioLoader
from clawsocialarena.scenario.models import GTBundle, Scenario


def test_cli_generates_scenario_and_gt(tmp_path: Path):
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "1", "--seed", "123",
        "--out", str(tmp_path),
    ])
    assert rc == 0
    scenario_dirs = list(tmp_path.iterdir())
    assert len(scenario_dirs) == 1
    sd = scenario_dirs[0]
    assert (sd / "scenario.json").exists()
    assert (sd / "scenario.gt.json").exists()

    Scenario.model_validate(json.loads((sd / "scenario.json").read_text()))
    GTBundle.model_validate(json.loads((sd / "scenario.gt.json").read_text()))


def test_cli_generates_multiple_scenarios(tmp_path: Path):
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "3", "--seed", "0",
        "--out", str(tmp_path),
    ])
    assert rc == 0
    assert len(list(tmp_path.iterdir())) == 3


def test_cli_with_attacker_produces_attribution_dag(tmp_path: Path):
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "1", "--seed", "1",
        "--attack", "collaborative_exfiltration",
        "--attacker-agent", "bob",
        "--out", str(tmp_path),
    ])
    assert rc == 0
    sd = next(tmp_path.iterdir())
    gt = json.loads((sd / "scenario.gt.json").read_text())
    assert len(gt["attribution_dag"]["nodes"]) == 1
    assert gt["attribution_dag"]["nodes"][0]["agent_id"] == "bob"


def test_cli_attacker_without_agent_flag_errors(tmp_path: Path):
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "1", "--seed", "1",
        "--attack", "social_engineering",
        "--out", str(tmp_path),
    ])
    assert rc == 2


def test_cli_generated_scenarios_round_trip_through_loader(tmp_path: Path):
    cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "2", "--seed", "7",
        "--out", str(tmp_path),
    ])
    loader = ScenarioLoader(root=tmp_path)
    for scenario_id_dir in tmp_path.iterdir():
        loaded = loader.load(scenario_id_dir.name)
        # loader.load returns either (Scenario, GTBundle) pre-D8 or a 3-tuple
        # post-D8. Accept both so this test stays green during the D7->D8
        # transition.
        scenario = loaded[0]
        assert scenario.scenario_id.startswith("cu-scheduling-")


def test_cli_emits_compose_personas_and_mcp_dirs(tmp_path: Path):
    """Task D7: every scenario dir ships the full v2 bundle."""
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "1", "--seed", "42",
        "--out", str(tmp_path),
    ])
    assert rc == 0
    sd = next(tmp_path.iterdir())

    assert (sd / "docker-compose.yml").exists()
    doc = yaml.safe_load((sd / "docker-compose.yml").read_text())
    assert "gateway" in doc["services"]

    personas_dir = sd / "personas"
    assert personas_dir.is_dir()
    scenario = Scenario.model_validate(
        json.loads((sd / "scenario.json").read_text())
    )
    for agent in scenario.agents:
        assert (personas_dir / f"{agent.agent_id}.system.md").exists()
        assert (personas_dir / f"{agent.agent_id}.tools.json").exists()

    # mcp/ dir is always present (CU scheduling template declares no tools,
    # so the directory is empty, but it still gets created).
    assert (sd / "mcp").is_dir()


def test_cli_instantiation_mode_llm_falls_back_to_deterministic(tmp_path: Path):
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "1", "--seed", "9",
        "--instantiation-mode", "llm",
        "--out", str(tmp_path),
    ])
    assert rc == 0
    sd = next(tmp_path.iterdir())
    Scenario.model_validate(json.loads((sd / "scenario.json").read_text()))


def test_cli_list_templates_does_not_require_category_or_out(capsys):
    rc = cli_main(["--list-templates"])
    assert rc == 0
    out = capsys.readouterr().out
    # At least one registered template pair should be present.
    assert "CU" in out
    assert "scheduling" in out


def test_cli_subprocess_smoke_runs_end_to_end(tmp_path: Path):
    """Out-of-process smoke: ``python -m clawsocialarena.generator.cli``."""
    out_dir = tmp_path / "gen_test"
    result = subprocess.run(
        [
            sys.executable, "-m", "clawsocialarena.generator.cli",
            "--category", "CU", "--family", "scheduling",
            "--n", "1", "--seed", "42",
            "--out", str(out_dir),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.returncode == 0, result.stderr
    scenario_dirs = list(out_dir.iterdir())
    assert len(scenario_dirs) == 1
    sd = scenario_dirs[0]
    for rel in (
        "scenario.json",
        "scenario.gt.json",
        "docker-compose.yml",
        "personas",
        "mcp",
    ):
        assert (sd / rel).exists(), f"missing {rel}"
