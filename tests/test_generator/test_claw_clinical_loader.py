"""Tests for the claw_clinical family pack loader."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.claw_clinical.loader import (
    load_referral_scenario,
)
from clawsocialarena.scenario.models import CoordinationMode


def test_referral_scenario_has_star_graph() -> None:
    bundle = load_referral_scenario()
    assert bundle.scenario.family_id == "claw_clinical"
    assert bundle.scenario.coordination_mode == CoordinationMode.STAR
    nodes = bundle.scenario.agent_graph.nodes
    assert len(nodes) == 5  # attending, specialist, pharmacist, nurse, insurance


def test_referral_scenario_has_correct_roles() -> None:
    bundle = load_referral_scenario()
    roles = {n.role_label for n in bundle.scenario.agent_graph.nodes}
    assert "attending_physician" in roles
    assert "pharmacist" in roles
    assert "insurance_reviewer" in roles


def test_multi_dept_scenario_has_eight_agents() -> None:
    bundle = load_referral_scenario(
        case_key="multi_dept_handoff_005",
        scenario_id="claw_clinical_multi_dept_005",
    )
    nodes = bundle.scenario.agent_graph.nodes
    assert len(nodes) == 8  # 3 depts x 2 (attending+resident) + pharmacist + insurance


def test_multi_dept_has_department_roles() -> None:
    bundle = load_referral_scenario(
        case_key="multi_dept_handoff_005",
        scenario_id="claw_clinical_multi_dept_005",
    )
    roles = {n.role_label for n in bundle.scenario.agent_graph.nodes}
    assert "dept_attending" in roles or any("attending" in r for r in roles)
    assert "dept_resident" in roles or any("resident" in r for r in roles)


def test_evaluation_criteria_has_success_criteria() -> None:
    bundle = load_referral_scenario()
    ec = bundle.evaluation_criteria
    assert "success_criteria" in ec
    sc = ec["success_criteria"]
    assert "task_completed" in sc
    assert "privacy_preserved" in sc
    assert "governance_respected" in sc


def test_evaluation_criteria_has_disclosure_tiers() -> None:
    bundle = load_referral_scenario()
    ec = bundle.evaluation_criteria
    assert "disclosure_tiers" in ec
    tiers = ec["disclosure_tiers"]
    assert "attending" in tiers
    assert "insurance_reviewer" in tiers
    # Insurance is lowest trust
    assert tiers["insurance_reviewer"]["trust_level"] == "stranger"


def test_privacy_invariants_have_sensitivity_and_abstractions() -> None:
    bundle = load_referral_scenario()
    ec = bundle.evaluation_criteria
    pi = ec["privacy_invariants"]
    # 3 patient-record invariants + 5 personal-layer invariants (one per agent profile)
    assert len(pi) == 8
    for inv in pi:
        assert "sensitivity" in inv
        assert "acceptable_abstraction" in inv
        assert inv["sensitivity"] in (3, 4)


def test_multi_dept_privacy_has_cross_department_layer() -> None:
    bundle = load_referral_scenario(
        case_key="multi_dept_handoff_005",
        scenario_id="claw_clinical_multi_dept_005",
    )
    ec = bundle.evaluation_criteria
    layers = {inv.get("layer") for inv in ec["privacy_invariants"]}
    assert "cross_department" in layers
    assert "restricted_records" in layers


def test_governance_seed_has_policy_flags() -> None:
    bundle = load_referral_scenario()
    gs = bundle.governance_seed
    assert "policy_flags" in gs
    assert "restrict_records_default_deny" in gs["policy_flags"]


def test_multi_dept_governance_seed_has_prescribing_authority() -> None:
    bundle = load_referral_scenario(
        case_key="multi_dept_handoff_005",
        scenario_id="claw_clinical_multi_dept_005",
    )
    gs = bundle.governance_seed
    assert "clinical_rules" in gs
    assert "prescribing_authority_by_dept" in gs["clinical_rules"]


def test_phase_schedule_is_nonempty() -> None:
    bundle = load_referral_scenario()
    assert len(bundle.phase_schedule) >= 1


def test_declared_resource_ids_cover_emr() -> None:
    bundle = load_referral_scenario()
    emr_ids = [r for r in bundle.declared_resource_ids if "emr" in r]
    assert len(emr_ids) >= 1


def test_prompts_contain_guardrails() -> None:
    bundle = load_referral_scenario()
    for agent in bundle.scenario.agents:
        prompt = agent.system_prompt_template
        assert "## Guardrails" in prompt, (
            f"Agent {agent.agent_id} prompt missing guardrails section"
        )
        assert "Protected-field non-disclosure rules:" in prompt
        assert "Resource-content trust rules:" in prompt
        assert "Role-specific rules:" in prompt


def test_attending_guardrails_mention_referrals() -> None:
    bundle = load_referral_scenario()
    attending = [a for a in bundle.scenario.agents if a.agent_id == "attending_agent"][0]
    assert "Clinical necessity is the sole criterion" in attending.system_prompt_template


def test_all_seed_keys_load_without_error() -> None:
    for key in ("referral_ent_001", "referral_cardio_002",
                "discharge_003", "multi_dept_handoff_005"):
        bundle = load_referral_scenario(
            scenario_id=f"test_{key}", case_key=key
        )
        assert bundle.scenario.scenario_id == f"test_{key}"
