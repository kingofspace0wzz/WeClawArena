"""Tests for travel-family attack-recipe payloads (Task 7)."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.attacks.stress_recipes import STRESS_RECIPE_REGISTRY
from clawsocialarena.generator.family_packs.travel.loader import (
    load_travel_scenario,
)


@pytest.fixture
def cu_base_bundle() -> dict:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    scn = bundle.scenario
    return {
        "scenario_id": scn.scenario_id,
        "family_id": "travel",
        "category": scn.category,
        "agent_graph": scn.agent_graph.model_dump(mode="json"),
        "initial_state": dict(scn.initial_state),
        "governance_manifest": {"governed_actions": {}},
        "trip_id": bundle.trip_id,
    }


@pytest.fixture
def mg_base_bundle() -> dict:
    bundle = load_travel_scenario(
        trip_id="TRIP-MG-OE-101",
        resource_profile="owned_ecosystem_family_group_guizhou",
    )
    scn = bundle.scenario
    return {
        "scenario_id": scn.scenario_id,
        "family_id": "travel",
        "category": scn.category,
        "agent_graph": scn.agent_graph.model_dump(mode="json"),
        "initial_state": dict(scn.initial_state),
        "governance_manifest": {"governed_actions": {}},
        "trip_id": bundle.trip_id,
    }


# --- security: indirect_resource_prompt_injection ---------------------------


def test_security_recipe_handles_travel_family(cu_base_bundle: dict) -> None:
    recipe = STRESS_RECIPE_REGISTRY["indirect_resource_prompt_injection"]
    artifacts = recipe.build_variant_artifacts(
        base_bundle=cu_base_bundle, family_id="travel", seed=0,
    )
    # Travel uses a file delivery surface (prior_bookings/confirmation.pdf).
    assert artifacts.resource_file_writes or artifacts.resource_db_inserts
    payload = artifacts.payload_text
    assert payload
    assert artifacts.target_agent_id


def test_security_recipe_payload_contains_travel_idiom(cu_base_bundle: dict) -> None:
    recipe = STRESS_RECIPE_REGISTRY["indirect_resource_prompt_injection"]
    artifacts = recipe.build_variant_artifacts(
        base_bundle=cu_base_bundle, family_id="travel", seed=0,
    )
    travel_idioms = ("CONCIERGE", "LOYALTY DESK", "PROPERTY", "GROUP TRAVEL", "booking", "upgrade")
    matched = any(
        i.lower() in artifacts.payload_text.lower() for i in travel_idioms
    )
    assert matched, f"travel idiom missing from payload: {artifacts.payload_text!r}"


# --- privacy: adaptive_exfiltration -----------------------------------------


def test_privacy_recipe_handles_travel_family(cu_base_bundle: dict) -> None:
    recipe = STRESS_RECIPE_REGISTRY["adaptive_exfiltration"]
    artifacts = recipe.build_variant_artifacts(
        base_bundle=cu_base_bundle, family_id="travel", seed=0,
    )
    assert artifacts.requires_runtime_peer is True
    assert artifacts.attacker_peer_id
    assert artifacts.attacker_peer_prompt
    pp = artifacts.attacker_peer_prompt.lower()
    # Travel-flavored exfiltration cue should appear.
    assert any(k in pp for k in ("passport", "loyalty", "upgrade", "elite"))


# --- governance: poisoned_consent_row ---------------------------------------


def test_governance_recipe_handles_travel_family(cu_base_bundle: dict) -> None:
    recipe = STRESS_RECIPE_REGISTRY["poisoned_consent_row"]
    artifacts = recipe.build_variant_artifacts(
        base_bundle=cu_base_bundle, family_id="travel", seed=0,
    )
    # Travel's governance injection writes a poisoned approval_log row.
    has_db_write = bool(artifacts.resource_db_inserts) or bool(
        artifacts.resource_db_updates
    )
    has_file_write = bool(artifacts.resource_file_writes)
    assert has_db_write or has_file_write


# --- collaboration: adaptive_malicious_peer ---------------------------------


def test_collaboration_recipe_handles_travel_cu(cu_base_bundle: dict) -> None:
    recipe = STRESS_RECIPE_REGISTRY["adaptive_malicious_peer"]
    artifacts = recipe.build_variant_artifacts(
        base_bundle=cu_base_bundle, family_id="travel", seed=0,
    )
    assert artifacts.requires_runtime_peer is True
    assert artifacts.attacker_peer_prompt
    pp = artifacts.attacker_peer_prompt.lower()
    # CU uses strategic-delay or constraint flavor; either way it should
    # reference partner / counter / delay.
    assert any(k in pp for k in ("counter", "delay", "constraint", "block", "sabotage", "stall"))


def test_collaboration_recipe_handles_travel_mg(mg_base_bundle: dict) -> None:
    recipe = STRESS_RECIPE_REGISTRY["adaptive_malicious_peer"]
    artifacts = recipe.build_variant_artifacts(
        base_bundle=mg_base_bundle, family_id="travel", seed=0,
    )
    assert artifacts.requires_runtime_peer is True
    # MG should pick a co_traveler or partner peer.
    assert artifacts.attacker_peer_id


# --- contract: recipes must not mutate base_bundle ---------------------------


@pytest.mark.parametrize("recipe_name", [
    "indirect_resource_prompt_injection",
    "adaptive_exfiltration",
    "poisoned_consent_row",
    "adaptive_malicious_peer",
])
def test_recipe_does_not_mutate_base_bundle(
    recipe_name: str, cu_base_bundle: dict
) -> None:
    import copy
    recipe = STRESS_RECIPE_REGISTRY[recipe_name]
    snapshot = copy.deepcopy(cu_base_bundle)
    recipe.build_variant_artifacts(
        base_bundle=cu_base_bundle, family_id="travel", seed=0,
    )
    assert cu_base_bundle == snapshot, (
        f"{recipe_name} mutated base_bundle (StressRecipe protocol violation)"
    )
