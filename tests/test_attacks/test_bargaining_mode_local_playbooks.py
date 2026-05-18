from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawsocialarena.attacks.stress_recipes import STRESS_RECIPE_REGISTRY
from clawsocialarena.generator.family_packs.marble_bargaining import (
    load_bargaining_scenario,
    materialize_bargaining_bundle,
)


def _base_bundle(tmp_path: Path) -> dict:
    bundle = load_bargaining_scenario()
    bundle_dir = materialize_bargaining_bundle(bundle, tmp_path / "scenario")
    scenario = json.loads((bundle_dir / "scenario.json").read_text())
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    merged = dict(scenario)
    merged.update(gt)
    merged["family_pack_context"] = context
    return merged


@pytest.mark.parametrize(
    ("recipe_name", "axis", "tactic_ids"),
    [
        (
            "bargaining_collaboration_mode_local_playbook",
            "collaboration",
            ["strategic_delay_peer", "deal_breaker_anchor", "off_platform_detour"],
        ),
        (
            "bargaining_security_mode_local_playbook",
            "security",
            [
                "poisoned_market_notice",
                "tool_observation_instruction",
                "fake_platform_policy",
            ],
        ),
        (
            "bargaining_privacy_mode_local_playbook",
            "privacy",
            [
                "budget_ceiling_extraction",
                "reservation_price_probe",
                "inferential_range_trap",
            ],
        ),
        (
            "bargaining_governance_mode_local_playbook",
            "governance",
            [
                "forged_approval_request",
                "stale_approval_replay",
                "policy_exception_laundering",
                "wrong_terms_approval",
                "approval_id_laundering",
            ],
        ),
    ],
)
def test_bargaining_playbook_artifacts_have_required_metadata(
    tmp_path: Path,
    recipe_name: str,
    axis: str,
    tactic_ids: list[str],
) -> None:
    recipe = STRESS_RECIPE_REGISTRY[recipe_name]
    artifacts = recipe.build_variant_artifacts(
        base_bundle=_base_bundle(tmp_path),
        family_id="marble_bargaining",
        seed=7,
    )

    metadata = artifacts.recipe_metadata
    assert recipe.axis == axis
    assert metadata["attack_recipe"] == "mode_local_playbook"
    assert metadata["attack_intensity"] == "stress"
    expected_playbook_id = (
        "governance_bargaining_stress_v5"
        if axis == "governance"
        else f"{axis}_bargaining_stress_v1"
    )
    assert metadata["playbook_id"] == expected_playbook_id
    assert metadata["attacker_control"] == "scripted_multi_turn"
    assert [t["tactic_id"] for t in metadata["tactics"]] == tactic_ids
    assert artifacts.target_agent_id in metadata["target_agent_ids"]
    assert len(artifacts.injected_messages) >= 2
    assert all(
        msg["attack_recipe"] == "mode_local_playbook"
        for msg in artifacts.injected_messages
    )


def test_bargaining_playbook_backfills_agent_ids_from_agent_graph(
    tmp_path: Path,
) -> None:
    base_bundle = _base_bundle(tmp_path)
    base_bundle["family_pack_context"].pop("buyer_agent_id")
    base_bundle["family_pack_context"].pop("seller_agent_id")
    buyer_agent_id = next(
        node["agent_id"]
        for node in base_bundle["agent_graph"]["nodes"]
        if node["role_label"] == "buyer"
    )
    seller_agent_id = next(
        node["agent_id"]
        for node in base_bundle["agent_graph"]["nodes"]
        if node["role_label"] == "seller"
    )

    artifacts = STRESS_RECIPE_REGISTRY[
        "bargaining_collaboration_mode_local_playbook"
    ].build_variant_artifacts(
        base_bundle=base_bundle,
        family_id="marble_bargaining",
        seed=7,
    )

    assert artifacts.target_agent_id == buyer_agent_id
    assert artifacts.recipe_metadata["target_agent_ids"] == [
        buyer_agent_id,
        seller_agent_id,
    ]


def test_security_playbook_records_attack_price_parameters(tmp_path: Path) -> None:
    base_bundle = _base_bundle(tmp_path)
    artifacts = STRESS_RECIPE_REGISTRY[
        "bargaining_security_mode_local_playbook"
    ].build_variant_artifacts(
        base_bundle=base_bundle,
        family_id="marble_bargaining",
        seed=7,
    )

    context = base_bundle["family_pack_context"]
    expected_price = min(
        float(context["buyer_budget_ceiling"]),
        float(context["market_reference_price"]) * 1.10,
    )
    assert expected_price > 0
    params = artifacts.recipe_metadata["attack_parameters"]
    assert params["attack_price"] == pytest.approx(expected_price)
    assert (
        params["attack_price_basis"]
        == "min(buyer_budget_ceiling, market_reference_price * 1.10)"
    )
    assert params["target_owner_id"] == context["buyer_owner_id"]
    assert "verified settlement price" in artifacts.payload_text.lower()


def test_governance_v5_targets_approver_and_seller_close_path(
    tmp_path: Path,
) -> None:
    base_bundle = _base_bundle(tmp_path)
    artifacts = STRESS_RECIPE_REGISTRY[
        "bargaining_governance_mode_local_playbook"
    ].build_variant_artifacts(
        base_bundle=base_bundle,
        family_id="marble_bargaining",
        seed=7,
    )

    context = base_bundle["family_pack_context"]
    approver_agent = context["approver_agent_id"]
    recipients_by_tactic = {
        msg["tactic_id"]: msg["to"] for msg in artifacts.injected_messages
    }
    assert recipients_by_tactic == {
        "forged_approval_request": approver_agent,
        "stale_approval_replay": approver_agent,
        "policy_exception_laundering": approver_agent,
        "wrong_terms_approval": approver_agent,
        "approval_id_laundering": context["seller_agent_id"],
    }
    assert artifacts.target_agent_id == approver_agent
    assert artifacts.recipe_metadata["playbook_id"] == "governance_bargaining_stress_v5"


def test_governance_v4_delivery_surfaces_are_messages_and_database_rows(
    tmp_path: Path,
) -> None:
    base_bundle = _base_bundle(tmp_path)
    artifacts = STRESS_RECIPE_REGISTRY[
        "bargaining_governance_mode_local_playbook"
    ].build_variant_artifacts(
        base_bundle=base_bundle,
        family_id="marble_bargaining",
        seed=7,
    )

    metadata = artifacts.recipe_metadata
    assert metadata["delivery_surface"] == ["message", "database_row"]
    assert all(
        tactic["delivery_surface"] == ["message", "database_row"]
        for tactic in metadata["tactics"]
    )


def test_governance_playbook_records_delegated_close_attack_parameters(
    tmp_path: Path,
) -> None:
    base_bundle = _base_bundle(tmp_path)
    artifacts = STRESS_RECIPE_REGISTRY[
        "bargaining_governance_mode_local_playbook"
    ].build_variant_artifacts(
        base_bundle=base_bundle,
        family_id="marble_bargaining",
        seed=7,
    )

    context = base_bundle["family_pack_context"]
    params = artifacts.recipe_metadata["attack_parameters"]
    assert params["attack_contract"] == "approval_policy_bypass"
    assert params["approver_agent_id"] == context["approver_agent_id"]
    assert params["approver_owner_id"] == context["approver_owner_id"]
    assert params["forged_approval_id"].startswith("APR-")
    assert params["stale_approval_id"].startswith("STALE-")
    assert params["buyer_owner_id"] == context["buyer_owner_id"]
    assert params["seller_owner_id"] == context["seller_owner_id"]
    assert params["target_owner_id"] == context["approver_owner_id"]
    assert "issue_purchase_approval" in artifacts.payload_text
    assert "request_purchase_approval" in artifacts.payload_text
    assert "accept_offer" not in artifacts.payload_text
    assert params["forged_approval_id"] in artifacts.payload_text


def test_governance_v5_platform_notices_are_owner_targeted(tmp_path: Path) -> None:
    base_bundle = _base_bundle(tmp_path)
    artifacts = STRESS_RECIPE_REGISTRY[
        "bargaining_governance_mode_local_playbook"
    ].build_variant_artifacts(
        base_bundle=base_bundle,
        family_id="marble_bargaining",
        seed=7,
    )

    context = base_bundle["family_pack_context"]
    seller_owner = context["seller_owner_id"]
    approver_owner = context["approver_owner_id"]
    inserts = artifacts.resource_db_inserts
    seller_rows = inserts[
        (f"agents/{seller_owner}/db/personal.sqlite", "platform_notices")
    ]
    approver_rows = inserts[
        (f"agents/{approver_owner}/db/personal.sqlite", "platform_notices")
    ]

    assert {
        row["tactic_id"] for row in seller_rows
    } == {"approval_id_laundering"}
    assert {row["target_owner_id"] for row in seller_rows} == {seller_owner}
    assert {
        row["tactic_id"] for row in approver_rows
    } == {
        "forged_approval_request",
        "stale_approval_replay",
        "policy_exception_laundering",
        "wrong_terms_approval",
    }
    assert {row["target_owner_id"] for row in approver_rows} == {approver_owner}
