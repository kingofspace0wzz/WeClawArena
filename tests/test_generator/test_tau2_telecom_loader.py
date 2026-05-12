"""Tests for the tau2_telecom family pack loader."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.tau2_telecom import (
    Tau2TelecomLoader,
    load_family_plan_roaming_scenario,
)
from clawsocialarena.scenario.models import CoordinationMode


def test_scenario_has_two_node_graph_and_family_id() -> None:
    bundle = load_family_plan_roaming_scenario()
    assert bundle.scenario.family_id == "tau2_telecom"
    assert bundle.scenario.coordination_mode == CoordinationMode.GRAPH
    assert bundle.scenario.agent_graph is not None
    assert len(bundle.scenario.agent_graph.nodes) == 2
    primary = next(
        n
        for n in bundle.scenario.agent_graph.nodes
        if n.role_label == "primary_account_holder"
    )
    secondary = next(
        n
        for n in bundle.scenario.agent_graph.nodes
        if n.role_label == "secondary_line_owner"
    )
    assert primary.owner_id == "alice"
    assert secondary.owner_id == "bob"


def test_seeded_lines_split_between_primary_and_secondary() -> None:
    bundle = load_family_plan_roaming_scenario()
    owners = {line["owner_id"] for line in bundle.seeded_lines}
    assert owners == {"alice", "bob"}
    # Both lines start with roaming disabled so the canonical task has
    # a meaningful "before" state.
    for line in bundle.seeded_lines:
        assert line["roaming_enabled"] is False


def test_evaluation_criteria_targets_secondary_line() -> None:
    bundle = load_family_plan_roaming_scenario()
    secondary_line_id = next(
        line["line_id"]
        for line in bundle.seeded_lines
        if line["owner_id"] == "bob"
    )
    target_line = bundle.evaluation_criteria["env_assertions"][0]["args"]["line_id"]
    assert target_line == secondary_line_id


def test_evaluation_criteria_consent_arg_is_secondary_owner() -> None:
    bundle = load_family_plan_roaming_scenario()
    consent_assertion = next(
        a
        for a in bundle.evaluation_criteria["env_assertions"]
        if a["predicate"] == "line_owner_consented_to_change"
    )
    assert consent_assertion["args"]["expected_consenter_id"] == "bob"


def test_phase_schedule_has_diagnosis_and_approval_phases() -> None:
    bundle = load_family_plan_roaming_scenario()
    phases = [phase["phase"] for phase in bundle.phase_schedule]
    assert "diagnosis" in phases
    assert "approval" in phases


def test_loader_kwargs_propagate_to_scenario() -> None:
    bundle = load_family_plan_roaming_scenario(
        primary_owner="carol",
        secondary_owner="dave",
        account_id="ACC-99",
    )
    assert bundle.scenario.initial_state["account_id"] == "ACC-99"
    owners = {n.owner_id for n in bundle.scenario.agent_graph.nodes}
    assert owners == {"carol", "dave"}


def test_db_loader_reads_toml() -> None:
    loader = Tau2TelecomLoader()
    db = loader._load_db()
    assert "plans" in db
    assert "lines" in db
    assert isinstance(db["lines"], list)
