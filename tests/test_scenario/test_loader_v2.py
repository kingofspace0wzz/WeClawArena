"""Scenario loader v2 round-trip tests (Task D8).

The loader returns ``(Scenario, GTBundle, ComposeSpec)`` from a v2 bundle
on disk. The ``ComposeSpec`` surfaces the compose YAML path and the
personas/mcp directories. Running the generator CLI and then loading the
resulting bundle exercises every emitter + the loader end-to-end.
"""

from __future__ import annotations

from pathlib import Path

from clawsocialarena.generator.cli import main as cli_main
from clawsocialarena.scenario.loader import ComposeSpec, ScenarioLoader
from clawsocialarena.scenario.models import GTBundle, Scenario


def test_loader_returns_triple_for_generated_bundle(tmp_path: Path):
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "1", "--seed", "101",
        "--out", str(tmp_path),
    ])
    assert rc == 0
    scenario_dir = next(tmp_path.iterdir())
    loader = ScenarioLoader(root=tmp_path)
    scenario, gt, compose = loader.load(scenario_dir.name)

    assert isinstance(scenario, Scenario)
    assert isinstance(gt, GTBundle)
    assert isinstance(compose, ComposeSpec)


def test_compose_spec_paths_point_at_bundle_contents(tmp_path: Path):
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "1", "--seed", "102",
        "--out", str(tmp_path),
    ])
    assert rc == 0
    scenario_dir = next(tmp_path.iterdir())
    _, _, compose = ScenarioLoader(root=tmp_path).load(scenario_dir.name)

    assert compose.compose_yaml == scenario_dir / "docker-compose.yml"
    assert compose.compose_yaml is not None
    assert compose.compose_yaml.exists()
    assert compose.personas_dir == scenario_dir / "personas"
    assert compose.personas_dir.is_dir()
    assert compose.mcp_dir == scenario_dir / "mcp"
    assert compose.mcp_dir.is_dir()


def test_loader_round_trips_scenario_and_gt(tmp_path: Path):
    """The scenario loaded from disk matches the one emitted."""
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "1", "--seed", "103",
        "--out", str(tmp_path),
    ])
    assert rc == 0
    scenario_dir = next(tmp_path.iterdir())
    scenario, gt, _ = ScenarioLoader(root=tmp_path).load(scenario_dir.name)
    assert scenario.scenario_id == scenario_dir.name
    # The GT bundle round-trip should include the v2 manifests.
    assert "alice" in gt.persona_manifest
    assert "bob" in gt.persona_manifest
    # Manifest is always a dict (possibly empty).
    assert isinstance(gt.mcp_tool_manifest, dict)


def test_loader_personas_dir_contains_one_pair_per_agent(tmp_path: Path):
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "1", "--seed", "104",
        "--out", str(tmp_path),
    ])
    assert rc == 0
    scenario_dir = next(tmp_path.iterdir())
    scenario, _, compose = ScenarioLoader(root=tmp_path).load(scenario_dir.name)
    for agent in scenario.agents:
        assert (compose.personas_dir / f"{agent.agent_id}.system.md").exists()
        assert (compose.personas_dir / f"{agent.agent_id}.tools.json").exists()
