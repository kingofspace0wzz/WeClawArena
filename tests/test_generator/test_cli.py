import json
import subprocess
import sys
from pathlib import Path

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

    # Files validate as their pydantic models
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
    # Use the existing ScenarioLoader against the generated directory
    loader = ScenarioLoader(root=tmp_path)
    for scenario_id_dir in tmp_path.iterdir():
        scenario, gt = loader.load(scenario_id_dir.name)
        assert scenario.scenario_id.startswith("cu-scheduling-")
