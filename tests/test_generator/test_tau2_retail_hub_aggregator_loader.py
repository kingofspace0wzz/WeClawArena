"""Tests for hub_aggregator loader (4 agents, star topology)."""
from __future__ import annotations


def test_hub_aggregator_loader_uses_star_coordination_mode() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail import load_hub_aggregator_scenario
    from clawsocialarena.scenario.models import CoordinationMode
    bundle = load_hub_aggregator_scenario(task_index=0)
    assert bundle.scenario.coordination_mode == CoordinationMode.STAR


def test_hub_aggregator_loader_passes_scenario_validator(tmp_path) -> None:
    from clawsocialarena.generator.family_packs.tau2_retail import load_hub_aggregator_scenario
    from clawsocialarena.generator.scenario_validator import validate_scenario
    bundle = load_hub_aggregator_scenario(task_index=0)
    # validate_scenario returns a ValidationResult; surface .errors as a
    # list so the verbatim assertion shape from the plan (issues == [])
    # holds against the real API.
    issues = list(validate_scenario(bundle.scenario).errors)
    assert issues == [], f"validator issues: {issues}"


def test_hub_aggregator_no_spoke_to_spoke_edges() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail import load_hub_aggregator_scenario
    bundle = load_hub_aggregator_scenario(task_index=0)
    spoke_agent_ids = bundle.family_pack_context["spoke_agent_ids"]
    for edge in bundle.scenario.agent_graph.edges:
        if edge.source in spoke_agent_ids and edge.target in spoke_agent_ids:
            assert False, f"forbidden spoke-to-spoke edge: {edge.source} -> {edge.target}"


def test_hub_aggregator_loader_loads_all_six_task_indices() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail import load_hub_aggregator_scenario
    for i in range(6):
        bundle = load_hub_aggregator_scenario(task_index=i)
        assert bundle.scenario.coordination_mode.value == "star"
        assert len(bundle.scenario.agents) == 4  # 1 hub + 3 spokes
        assert bundle.family_pack_context["archetype"] == "hub_aggregator"
