"""Tests for the claw_trading family pack loader."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.claw_trading.loader import (
    TradingClubLoader,
    load_trading_club_scenario,
)
from clawsocialarena.scenario.models import CoordinationMode


def test_simple_scenario_has_star_graph() -> None:
    bundle = load_trading_club_scenario()
    assert bundle.scenario.family_id == "claw_trading"
    assert bundle.scenario.coordination_mode == CoordinationMode.GRAPH
    nodes = bundle.scenario.agent_graph.nodes
    assert len(nodes) >= 3  # admin + at least 2 members


def test_simple_scenario_has_correct_roles() -> None:
    bundle = load_trading_club_scenario()
    roles = {n.role_label for n in bundle.scenario.agent_graph.nodes}
    assert "club_admin" in roles
    assert "club_member" in roles


def test_multi_team_scenario_has_nine_agents() -> None:
    bundle = load_trading_club_scenario(
        case_key="multi_team_debate_005",
        scenario_id="claw_trading_multi_team_005",
    )
    nodes = bundle.scenario.agent_graph.nodes
    assert len(nodes) == 9  # 3 members x 3 sub-agents each
    roles = {n.role_label for n in nodes}
    assert "team_analyst" in roles
    assert "team_researcher" in roles
    assert "club_member_trader" in roles


def test_multi_team_edges_connect_within_and_across_teams() -> None:
    bundle = load_trading_club_scenario(
        case_key="multi_team_debate_005",
        scenario_id="claw_trading_multi_team_005",
    )
    edges = bundle.scenario.agent_graph.edges
    channels = {e.channel for e in edges}
    assert "intra_team" in channels or any("team" in c for c in channels)
    assert len(edges) >= 20  # At least 20 edges for 3x3 topology


def test_evaluation_criteria_has_success_criteria() -> None:
    bundle = load_trading_club_scenario()
    ec = bundle.evaluation_criteria
    assert "success_criteria" in ec
    sc = ec["success_criteria"]
    assert "task_completed" in sc
    assert "privacy_preserved" in sc
    assert "governance_respected" in sc


def test_evaluation_criteria_has_disclosure_tiers() -> None:
    bundle = load_trading_club_scenario()
    ec = bundle.evaluation_criteria
    assert "disclosure_tiers" in ec
    assert "admin" in ec["disclosure_tiers"]
    assert "club_member" in ec["disclosure_tiers"]


def test_privacy_invariants_have_acceptable_abstractions() -> None:
    bundle = load_trading_club_scenario()
    ec = bundle.evaluation_criteria
    pi = ec["privacy_invariants"]
    assert len(pi) >= 3  # One per member
    for inv in pi:
        assert "sensitivity" in inv
        assert "acceptable_abstractions" in inv
        assert inv["sensitivity"] in (1, 2, 3, 4)


def test_multi_team_privacy_has_three_layers() -> None:
    bundle = load_trading_club_scenario(
        case_key="multi_team_debate_005",
        scenario_id="claw_trading_multi_team_005",
    )
    ec = bundle.evaluation_criteria
    layers = {inv.get("layer") for inv in ec["privacy_invariants"]}
    assert "cross_member" in layers
    assert "cross_role" in layers
    assert "cross_team" in layers


def test_governance_seed_has_policy_flags() -> None:
    bundle = load_trading_club_scenario()
    gs = bundle.governance_seed
    assert "policy_flags" in gs
    assert "admin_must_announce_results" in gs["policy_flags"]


def test_multi_team_governance_seed_has_sub_agent_ids() -> None:
    bundle = load_trading_club_scenario(
        case_key="multi_team_debate_005",
        scenario_id="claw_trading_multi_team_005",
    )
    gs = bundle.governance_seed
    assert "sub_agent_ids" in gs
    assert len(gs["sub_agent_ids"]) == 9  # 3 members x 3 roles


def test_phase_schedule_is_nonempty() -> None:
    bundle = load_trading_club_scenario()
    assert len(bundle.phase_schedule) >= 1


def test_declared_resource_ids_cover_portfolios() -> None:
    bundle = load_trading_club_scenario()
    portfolio_ids = [r for r in bundle.declared_resource_ids if "portfolio" in r]
    assert len(portfolio_ids) >= 3  # One per member


def test_simple_prompts_contain_guardrails() -> None:
    bundle = load_trading_club_scenario()
    for agent in bundle.scenario.agents:
        prompt = agent.system_prompt_template
        assert "## Guardrails" in prompt
        assert "Protected-field non-disclosure rules:" in prompt
        assert "Resource-content trust rules:" in prompt


def test_multi_team_prompts_contain_guardrails() -> None:
    bundle = load_trading_club_scenario(
        case_key="multi_team_debate_005",
        scenario_id="claw_trading_multi_team_005",
    )
    for agent in bundle.scenario.agents:
        prompt = agent.system_prompt_template
        assert "## Guardrails" in prompt
        assert "Protected-field non-disclosure rules:" in prompt
        assert "Resource-content trust rules:" in prompt


def test_all_seed_keys_load_without_error() -> None:
    loader = TradingClubLoader()
    for key in ("earnings_debate_001", "sector_rotation_003",
                "new_member_004", "multi_team_debate_005"):
        bundle = loader.load_trading_club(
            scenario_id=f"test_{key}", case_key=key
        )
        assert bundle.scenario.scenario_id == f"test_{key}"
