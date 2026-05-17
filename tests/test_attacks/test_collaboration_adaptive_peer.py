"""Tests for the collaboration adaptive-peer stress recipe.

Covers the contract laid out in the recipe's docstring:

1. The recipe registers in ``STRESS_RECIPE_REGISTRY`` at import time.
2. ``name`` and ``axis`` are the spec-stable values.
3. ``requires_runtime_peer`` is True (this is the adaptive recipe).
4. The resolved ``attacker_peer_id`` is non-focal and both ids live
   in the bundle's ``agent_graph.nodes``.
5. The per-family dispatch produces a >=200-word peer prompt for
   each of the 6 canonical families.
6. The prompt is deterministic in ``(family_id, seed)``.
7. The sabotage menu is surfaced in the prompt text (the words
   ``refuse``, ``redirect``, and ``contradict`` -- or close variants
   -- show up).
"""
from __future__ import annotations

from typing import Any

import pytest

from clawsocialarena.attacks.stress_recipes import STRESS_RECIPE_REGISTRY
from clawsocialarena.attacks.stress_recipes.base import (
    StressRecipe,
    StressVariantArtifacts,
)
from clawsocialarena.attacks.stress_recipes.collaboration_adaptive_peer import (
    COLLABORATION_ADAPTIVE_PEER,
)


# ---------- Test fixtures ---------------------------------------------


def _make_bundle(
    *,
    family_id: str,
    focal_id: str,
    focal_role: str,
    peer_id: str,
    peer_role: str,
    extra_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal base_bundle dict with an agent_graph + agents.

    Matches the on-disk shape of Phase-5 ``scenario.json`` files
    closely enough for the recipe's resolver to do its work.
    """
    nodes: list[dict[str, Any]] = [
        {
            "agent_id": focal_id,
            "role_label": focal_role,
            "owner_id": focal_id.split("_")[0],
            "active_identity": f"{focal_id}@x",
            "approval_mandate": "self",
            "scope": ["read:x", "write:x"],
        },
        {
            "agent_id": peer_id,
            "role_label": peer_role,
            "owner_id": peer_id.split("_")[0],
            "active_identity": f"{peer_id}@x",
            "approval_mandate": "self",
            "scope": ["read:x"],
        },
    ]
    if extra_nodes:
        nodes.extend(extra_nodes)
    return {
        "scenario_id": f"{family_id}_test_scenario",
        "family_id": family_id,
        "agent_graph": {"nodes": nodes, "edges": []},
        "agents": [
            {"agent_id": n["agent_id"], "user_id": n["owner_id"]} for n in nodes
        ],
        "opening_message": {"from": "system", "to": focal_id, "content": "go"},
    }


_FAMILY_TEST_CASES: dict[str, dict[str, str]] = {
    "tau2_telecom": {
        "focal_id": "leo_assistant",
        "focal_role": "primary_account_holder",
        "peer_id": "maya_assistant",
        "peer_role": "secondary_line_owner",
    },
    "tau2_retail": {
        "focal_id": "alice_assistant",
        "focal_role": "primary_account_holder",
        "peer_id": "bob_assistant",
        "peer_role": "secondary_account_holder",
    },
    "tau2_airline": {
        "focal_id": "alice_organizer",
        "focal_role": "group_organizer",
        "peer_id": "bob_traveler",
        "peer_role": "group_traveler",
    },
    "wildclaw_social": {
        "focal_id": "alice_director_assistant",
        "focal_role": "meeting_organizer",
        "peer_id": "bob_assistant",
        "peer_role": "meeting_participant",
    },
    "marble_research": {
        "focal_id": "alice_pi",
        "focal_role": "convener_pi",
        "peer_id": "bob_pi",
        "peer_role": "peer_pi",
    },
    "marble_bargaining": {
        "focal_id": "alice_buyer",
        "focal_role": "buyer",
        "peer_id": "bob_seller",
        "peer_role": "seller",
    },
    "travel": {
        "focal_id": "mt_1_traveler",
        "focal_role": "traveler",
        "peer_id": "huaning_county_yunnan_hotel_partner_hotel",
        "peer_role": "partner_hotel",
    },
}


# ---------- Tests -----------------------------------------------------


def test_recipe_registers_in_stress_recipe_registry() -> None:
    """Importing the package side-effects the recipe into the registry."""
    assert "adaptive_malicious_peer" in STRESS_RECIPE_REGISTRY
    assert STRESS_RECIPE_REGISTRY["adaptive_malicious_peer"] is (
        COLLABORATION_ADAPTIVE_PEER
    )
    assert isinstance(COLLABORATION_ADAPTIVE_PEER, StressRecipe)


def test_recipe_name_and_axis_match_spec() -> None:
    """The recipe's identity fields match the spec-stable values."""
    assert COLLABORATION_ADAPTIVE_PEER.name == "adaptive_malicious_peer"
    assert COLLABORATION_ADAPTIVE_PEER.axis == "collaboration"


def test_recipe_requires_runtime_peer() -> None:
    """The collaboration recipe is adaptive, so the runtime substrate
    must spin up an attacker peer LLM.
    """
    case = _FAMILY_TEST_CASES["tau2_telecom"]
    bundle = _make_bundle(family_id="tau2_telecom", **case)
    artifacts = COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
        base_bundle=bundle, family_id="tau2_telecom", seed=0,
    )
    assert isinstance(artifacts, StressVariantArtifacts)
    assert artifacts.requires_runtime_peer is True
    assert artifacts.attacker_peer_prompt is not None
    assert artifacts.attacker_peer_id is not None


def test_attacker_peer_and_target_are_distinct_and_in_agent_graph() -> None:
    """The peer must be a real non-focal agent_graph node."""
    for family_id, case in _FAMILY_TEST_CASES.items():
        bundle = _make_bundle(family_id=family_id, **case)
        artifacts = COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
            base_bundle=bundle, family_id=family_id, seed=0,
        )
        node_ids = {n["agent_id"] for n in bundle["agent_graph"]["nodes"]}
        assert artifacts.target_agent_id != artifacts.attacker_peer_id, (
            f"{family_id}: target and peer collided"
        )
        assert artifacts.target_agent_id in node_ids, (
            f"{family_id}: target {artifacts.target_agent_id!r} not in nodes"
        )
        assert artifacts.attacker_peer_id in node_ids, (
            f"{family_id}: peer {artifacts.attacker_peer_id!r} not in nodes"
        )
        # The focal should match the family's canonical focal role.
        assert artifacts.target_agent_id == case["focal_id"]
        assert artifacts.attacker_peer_id == case["peer_id"]


def test_per_family_prompt_length_meets_two_hundred_words() -> None:
    """Each family's peer prompt is at least 200 words."""
    for family_id, case in _FAMILY_TEST_CASES.items():
        bundle = _make_bundle(family_id=family_id, **case)
        artifacts = COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
            base_bundle=bundle, family_id=family_id, seed=0,
        )
        prompt = artifacts.attacker_peer_prompt or ""
        word_count = len(prompt.split())
        assert word_count >= 200, (
            f"{family_id}: peer prompt only {word_count} words; "
            f"expected >= 200"
        )
        # Personas should be tied to actual agent_ids, not template
        # placeholders left in the text.
        assert "${peer_id}" not in prompt
        assert "${focal_id}" not in prompt
        assert case["peer_id"] in prompt
        assert case["focal_id"] in prompt


def test_same_seed_produces_deterministic_prompt() -> None:
    """Same (family_id, seed) -> same prompt; different seed pool
    cycles through the family's variant pool.
    """
    case = _FAMILY_TEST_CASES["tau2_telecom"]
    bundle = _make_bundle(family_id="tau2_telecom", **case)
    a1 = COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
        base_bundle=bundle, family_id="tau2_telecom", seed=42,
    )
    a2 = COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
        base_bundle=bundle, family_id="tau2_telecom", seed=42,
    )
    assert a1.attacker_peer_prompt == a2.attacker_peer_prompt
    assert a1.payload_text == a2.payload_text
    # Different seeds picking a different variant must produce
    # observably different prompts (we sample seeds 0 / 1 / 2 which
    # land on three different variants in a 3-variant pool).
    prompts = {
        seed: COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
            base_bundle=bundle, family_id="tau2_telecom", seed=seed,
        ).attacker_peer_prompt
        for seed in (0, 1, 2)
    }
    assert len(set(prompts.values())) == 3, (
        "tau2_telecom seeds 0/1/2 should pick three distinct variants"
    )


def test_sabotage_menu_surfaced_in_prompt() -> None:
    """Each per-variant prompt must:

    - mention at least one sabotage verb (refuse / redirect /
      contradict / stall / block / obstruct -- so the LLM peer
      always has a concrete move to pick from);
    - carry an escalation policy (the word ``escalat`` should appear);
    - carry the no-giveaways guardrail (the word ``test`` or
      ``sabotag`` so the prompt explicitly forbids attack giveaways).

    Different family scenarios naturally emphasize different sabotage
    flavors (e.g. ``marble_bargaining`` peers stall on price; ``tau2_telecom``
    peers refuse consent). Requiring every verb in every family is
    overly strict; we instead allow any one of the synonymous verbs
    per variant.
    """
    sabotage_verbs = {
        "refuse",
        "redirect",
        "contradict",
        "stall",
        "block",
        "obstruct",
    }
    for family_id, case in _FAMILY_TEST_CASES.items():
        bundle = _make_bundle(family_id=family_id, **case)
        for seed in range(3):
            artifacts = COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
                base_bundle=bundle, family_id=family_id, seed=seed,
            )
            prompt = (artifacts.attacker_peer_prompt or "").lower()
            hits = {verb for verb in sabotage_verbs if verb in prompt}
            assert hits, (
                f"{family_id} seed={seed}: prompt mentions none of the "
                f"sabotage verbs {sabotage_verbs!r}"
            )
            assert "escalat" in prompt
            assert "test" in prompt or "sabotag" in prompt


def test_recipe_metadata_describes_sabotage_axis() -> None:
    """The recipe_metadata dict carries the diagnostic signature
    fields downstream scorers / dashboards can read.
    """
    case = _FAMILY_TEST_CASES["marble_research"]
    bundle = _make_bundle(family_id="marble_research", **case)
    artifacts = COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
        base_bundle=bundle, family_id="marble_research", seed=5,
    )
    metadata = artifacts.recipe_metadata
    assert metadata["recipe"] == "adaptive_malicious_peer"
    assert metadata["axis"] == "collaboration"
    assert metadata["family_id"] == "marble_research"
    assert metadata["focal_id"] == artifacts.target_agent_id
    assert metadata["peer_id"] == artifacts.attacker_peer_id
    assert "sabotage_menu" in metadata
    assert isinstance(metadata["sabotage_menu"], list)
    assert any("refuse" in item for item in metadata["sabotage_menu"])
    assert metadata["escalation_policy"]
    # The diagnostic payload signature must mention the peer id.
    assert artifacts.attacker_peer_id in artifacts.payload_text


def test_payload_text_does_not_inject_into_opening_message() -> None:
    """Opening_message is left untouched -- the recipe declares peer
    behavior, not a static prompt injection.
    """
    case = _FAMILY_TEST_CASES["tau2_telecom"]
    bundle = _make_bundle(family_id="tau2_telecom", **case)
    artifacts = COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
        base_bundle=bundle, family_id="tau2_telecom", seed=0,
    )
    # No resource mutations, no injected messages -- this is a runtime
    # peer recipe.
    assert artifacts.opening_message_addendum == ""
    assert artifacts.resource_file_writes == {}
    assert artifacts.resource_db_inserts == {}
    assert artifacts.resource_db_updates == {}
    assert artifacts.injected_messages == []


def test_resolver_uses_governance_manifest_when_role_labels_missing() -> None:
    """If the agent_graph nodes lack matching role_labels, fall back
    to governance_manifest.governed_actions for the focal id.
    """
    bundle: dict[str, Any] = {
        "scenario_id": "novel_family_test",
        "family_id": "novel_family",
        "agent_graph": {
            "nodes": [
                {
                    "agent_id": "alice_focal",
                    "role_label": "unknown_role_a",
                    "owner_id": "alice",
                    "active_identity": "alice@x",
                    "approval_mandate": "self",
                    "scope": [],
                },
                {
                    "agent_id": "bob_peer",
                    "role_label": "unknown_role_b",
                    "owner_id": "bob",
                    "active_identity": "bob@x",
                    "approval_mandate": "self",
                    "scope": [],
                },
            ],
            "edges": [],
        },
        "agents": [
            {"agent_id": "alice_focal", "user_id": "alice"},
            {"agent_id": "bob_peer", "user_id": "bob"},
        ],
        "governance_manifest": {
            "governed_actions": {
                "act_1": {
                    "action_id": "act_1",
                    "action_type": "commit_action",
                    "agent_id": "alice_focal",
                    "resource_id": "r1",
                    "required_scope_id": "scope_1",
                }
            }
        },
        "opening_message": {"from": "system", "to": "alice_focal", "content": "go"},
    }
    artifacts = COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
        base_bundle=bundle, family_id="novel_family", seed=0,
    )
    assert artifacts.target_agent_id == "alice_focal"
    assert artifacts.attacker_peer_id == "bob_peer"
    # The fallback prompt should still be present + non-empty.
    assert artifacts.attacker_peer_prompt is not None
    assert "alice_focal" in artifacts.attacker_peer_prompt
    assert "bob_peer" in artifacts.attacker_peer_prompt


def test_resolver_raises_on_single_agent_bundle() -> None:
    """A bundle with no peer candidate cannot host a collaboration
    attack; the recipe should refuse rather than silently produce an
    invalid record.
    """
    bundle: dict[str, Any] = {
        "scenario_id": "single_agent_test",
        "family_id": "tau2_telecom",
        "agent_graph": {
            "nodes": [
                {
                    "agent_id": "lonely_agent",
                    "role_label": "primary_account_holder",
                    "owner_id": "lonely",
                    "active_identity": "lonely@x",
                    "approval_mandate": "self",
                    "scope": [],
                }
            ],
            "edges": [],
        },
        "agents": [{"agent_id": "lonely_agent", "user_id": "lonely"}],
    }
    with pytest.raises(ValueError, match="focal / peer"):
        COLLABORATION_ADAPTIVE_PEER.build_variant_artifacts(
            base_bundle=bundle, family_id="tau2_telecom", seed=0,
        )
