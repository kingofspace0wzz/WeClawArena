"""Tests for the Phase-5 attack payload table (S3 step 4).

Per spec section 2 ("Matched Main-Stratum Design"), every base task
emits five variants along the **attack_mode axis**: no_attacker,
collaboration, security, privacy, governance. These tests pin the
axis contract, the mode-to-recipe mapping, and the per-family
payload alignment.
"""
from __future__ import annotations

from pathlib import Path

import json

import pytest

from clawsocialarena.attacks.schema import AttackerControl, DeliverySurface
from clawsocialarena.generator.family_pack_registry import (
    FAMILY_LOADERS,
    load_and_materialize,
)
from clawsocialarena.generator.phase5_attack_payloads import (
    ATTACK_MODES_ALL,
    ATTACK_MODES_NON_BASELINE,
    MODE_TO_RECIPE,
    PAYLOAD_BUILDERS,
    RECIPE_TO_MODE,
    AttackPayload,
    attack_payloads_for,
)
from clawsocialarena.generator.phase5_task_variants import task_variants_for


def test_attack_modes_taxonomy_has_one_baseline_plus_four_axes() -> None:
    assert ATTACK_MODES_ALL[0] == "no_attacker"
    assert ATTACK_MODES_NON_BASELINE == tuple(ATTACK_MODES_ALL[1:])
    assert set(ATTACK_MODES_NON_BASELINE) == {
        "collaboration",
        "security",
        "privacy",
        "governance",
    }
    assert len(ATTACK_MODES_ALL) == 5


def test_mode_to_recipe_is_one_to_one() -> None:
    """Phase-5 ships exactly one recipe per mode."""
    assert set(MODE_TO_RECIPE.keys()) == set(ATTACK_MODES_NON_BASELINE)
    assert len(set(MODE_TO_RECIPE.values())) == len(MODE_TO_RECIPE)
    # And RECIPE_TO_MODE is the inverse.
    for mode, recipe in MODE_TO_RECIPE.items():
        assert RECIPE_TO_MODE[recipe] == mode


def test_every_family_has_a_payload_builder() -> None:
    missing = set(FAMILY_LOADERS.keys()) - set(PAYLOAD_BUILDERS.keys())
    assert not missing, f"PAYLOAD_BUILDERS missing entries for: {missing}"


@pytest.mark.parametrize("family_id", sorted(FAMILY_LOADERS.keys()))
def test_payloads_align_to_non_baseline_modes_in_order(
    family_id: str, tmp_path: Path
) -> None:
    """Each family's payload tuple must align 1:1 with the ordered
    list of non-baseline modes. Misorder here would mean the
    orchestrator picks the wrong payload for a given mode.
    """
    variant = task_variants_for(family_id)[0]
    bundle_dir, _bundle = load_and_materialize(
        family_id=family_id,
        out_dir=tmp_path / family_id,
        load_kwargs=variant.loader_kwargs,
    )
    scenario = json.loads(
        (bundle_dir / "scenario.json").read_text(encoding="utf-8")
    )
    payloads = attack_payloads_for(
        family_id, scenario=scenario, loader_kwargs=variant.loader_kwargs
    )
    assert len(payloads) == len(ATTACK_MODES_NON_BASELINE)
    for payload, expected_mode in zip(payloads, ATTACK_MODES_NON_BASELINE):
        assert payload.attack_mode == expected_mode, (
            f"{family_id}: expected {expected_mode}, got {payload.attack_mode}"
        )
        assert payload.attack_recipe == MODE_TO_RECIPE[expected_mode]


@pytest.mark.parametrize("family_id", sorted(FAMILY_LOADERS.keys()))
def test_payload_target_agent_ids_are_real_for_each_family(
    family_id: str, tmp_path: Path
) -> None:
    """The target_agent_id must exist in the scenario's agent list,
    otherwise the orchestrator cannot deliver the message."""
    variant = task_variants_for(family_id)[0]
    bundle_dir, _bundle = load_and_materialize(
        family_id=family_id,
        out_dir=tmp_path / family_id,
        load_kwargs=variant.loader_kwargs,
    )
    scenario = json.loads(
        (bundle_dir / "scenario.json").read_text(encoding="utf-8")
    )
    agent_ids = {a["agent_id"] for a in scenario["agents"]}
    payloads = attack_payloads_for(
        family_id, scenario=scenario, loader_kwargs=variant.loader_kwargs
    )
    for payload in payloads:
        assert isinstance(payload, AttackPayload)
        assert payload.target_agent_id in agent_ids, (
            f"{family_id} payload {payload.attack_mode} targets "
            f"unknown agent {payload.target_agent_id!r}; "
            f"known: {sorted(agent_ids)}"
        )
        assert payload.message_kind in {
            "opening_message",
            "peer_message",
            "system_aside",
        }
        valid_surfaces = {str(s) for s in DeliverySurface}
        assert payload.delivery_surface in valid_surfaces, (
            f"{family_id}/{payload.attack_mode} has invalid delivery_surface "
            f"{payload.delivery_surface!r}; valid: {sorted(valid_surfaces)}"
        )
        assert payload.attacker_control == str(AttackerControl.SCRIPTED)
        assert payload.payload_text.strip(), (
            f"{family_id}/{payload.attack_mode} has empty payload text"
        )


def test_payload_text_quotes_identity_fields_for_tau2_retail(
    tmp_path: Path,
) -> None:
    """Pin that the tau2_retail payloads use the loader_kwargs identity
    (household_id) so subsequent kwargs changes are visible in tests.
    """
    variant = task_variants_for("tau2_retail")[0]
    bundle_dir, _bundle = load_and_materialize(
        family_id="tau2_retail",
        out_dir=tmp_path,
        load_kwargs=variant.loader_kwargs,
    )
    scenario = json.loads(
        (bundle_dir / "scenario.json").read_text(encoding="utf-8")
    )
    payloads = attack_payloads_for(
        "tau2_retail",
        scenario=scenario,
        loader_kwargs=variant.loader_kwargs,
    )
    assert any(
        variant.loader_kwargs["household_id"] in p.payload_text
        for p in payloads
    )


def test_attack_payloads_for_rejects_unknown_family(tmp_path: Path) -> None:
    with pytest.raises(KeyError) as excinfo:
        attack_payloads_for(
            "not_a_real_family",
            scenario={"agents": []},
            loader_kwargs={},
        )
    assert "known" in str(excinfo.value)


def test_attack_payloads_for_rejects_out_of_order_builder() -> None:
    """A custom builder that returns payloads in the wrong mode order
    must be caught by ``attack_payloads_for``'s validation pass.
    """
    from clawsocialarena.generator.phase5_attack_payloads import _build_payload

    def bad_builder(scenario, loader_kwargs):
        return (
            _build_payload(
                attack_mode="security",  # wrong slot (expects collaboration)
                message_kind="peer_message",
                target_agent_id=scenario["agents"][0]["agent_id"],
                payload_text="bad",
                metadata={},
            ),
            _build_payload(
                attack_mode="collaboration",
                message_kind="peer_message",
                target_agent_id=scenario["agents"][0]["agent_id"],
                payload_text="bad",
                metadata={},
            ),
            _build_payload(
                attack_mode="privacy",
                message_kind="peer_message",
                target_agent_id=scenario["agents"][0]["agent_id"],
                payload_text="bad",
                metadata={},
            ),
            _build_payload(
                attack_mode="governance",
                message_kind="peer_message",
                target_agent_id=scenario["agents"][0]["agent_id"],
                payload_text="bad",
                metadata={},
            ),
        )

    PAYLOAD_BUILDERS["__bad_test_pack__"] = bad_builder
    try:
        with pytest.raises(ValueError) as excinfo:
            attack_payloads_for(
                "__bad_test_pack__",
                scenario={"agents": [{"agent_id": "anyone"}]},
                loader_kwargs={},
            )
        assert "ATTACK_MODES_NON_BASELINE" in str(excinfo.value)
    finally:
        PAYLOAD_BUILDERS.pop("__bad_test_pack__", None)
