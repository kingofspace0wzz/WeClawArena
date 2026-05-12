"""Per-family task-variant table for the Phase-5 pilot.

Each family pack ships one canonical scenario via its loader. The pilot
needs three distinct base-task instances per cell so the run-batches
average over identity variation rather than a single template. Rather
than build three separate loaders per pack, we vary the identity
kwargs that every loader already accepts: participant ids, owner
names, and entity ids (household_id, group_id, account_id, etc.).

The three variants are deterministic and frozen so the same call from
the generator and the orchestrator produces the same scenarios. Each
variant uses a tier-1-compatible scenario_id that the difficulty-tier
overlay then refines.

Tests in :mod:`tests.test_generator.test_phase5_task_variants`
exercise this module against every registered family.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskVariantSpec:
    """One identity-variant entry for a family pack."""

    task_index: int  # 0, 1, or 2
    label: str  # short human-readable tag (e.g. "alice_bob_HH7")
    loader_kwargs: dict[str, Any]


def _kwargs_tau2_retail() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {
            "scenario_id": "tau2_retail_household_exchange_phase5_v0",
            "primary_id": "alice_assistant",
            "secondary_id": "bob_assistant",
            "primary_owner": "alice",
            "secondary_owner": "bob",
            "household_id": "HH-7",
        },
        {
            "scenario_id": "tau2_retail_household_exchange_phase5_v1",
            "primary_id": "diane_assistant",
            "secondary_id": "evan_assistant",
            "primary_owner": "diane",
            "secondary_owner": "evan",
            "household_id": "HH-12",
        },
        {
            "scenario_id": "tau2_retail_household_exchange_phase5_v2",
            "primary_id": "felix_assistant",
            "secondary_id": "grace_assistant",
            "primary_owner": "felix",
            "secondary_owner": "grace",
            "household_id": "HH-21",
        },
    )


def _kwargs_tau2_airline() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {
            "scenario_id": "tau2_airline_group_seat_change_phase5_v0",
            "organizer_id": "alice_organizer",
            "traveler_id": "bob_traveler",
            "organizer_owner": "alice",
            "traveler_owner": "bob",
            "group_id": "GRP-7",
        },
        {
            "scenario_id": "tau2_airline_group_seat_change_phase5_v1",
            "organizer_id": "henry_organizer",
            "traveler_id": "iris_traveler",
            "organizer_owner": "henry",
            "traveler_owner": "iris",
            "group_id": "GRP-12",
        },
        {
            "scenario_id": "tau2_airline_group_seat_change_phase5_v2",
            "organizer_id": "jasper_organizer",
            "traveler_id": "kira_traveler",
            "organizer_owner": "jasper",
            "traveler_owner": "kira",
            "group_id": "GRP-21",
        },
    )


def _kwargs_tau2_telecom() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {
            "scenario_id": "tau2_telecom_family_plan_roaming_phase5_v0",
            "primary_id": "alice_assistant",
            "secondary_id": "bob_assistant",
            "primary_owner": "alice",
            "secondary_owner": "bob",
            "account_id": "ACC-7",
        },
        {
            "scenario_id": "tau2_telecom_family_plan_roaming_phase5_v1",
            "primary_id": "leo_assistant",
            "secondary_id": "maya_assistant",
            "primary_owner": "leo",
            "secondary_owner": "maya",
            "account_id": "ACC-12",
        },
        {
            "scenario_id": "tau2_telecom_family_plan_roaming_phase5_v2",
            "primary_id": "nina_assistant",
            "secondary_id": "owen_assistant",
            "primary_owner": "nina",
            "secondary_owner": "owen",
            "account_id": "ACC-21",
        },
    )


def _kwargs_marble_research() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {
            "scenario_id": "marble_research_collaboration_phase5_v0",
            "convener_id": "alice_pi",
            "peer_one_id": "bob_pi",
            "peer_two_id": "carol_pi",
            "convener_owner": "alice",
            "peer_one_owner": "bob",
            "peer_two_owner": "carol",
        },
        {
            "scenario_id": "marble_research_collaboration_phase5_v1",
            "convener_id": "priya_pi",
            "peer_one_id": "quentin_pi",
            "peer_two_id": "rosa_pi",
            "convener_owner": "priya",
            "peer_one_owner": "quentin",
            "peer_two_owner": "rosa",
        },
        {
            "scenario_id": "marble_research_collaboration_phase5_v2",
            "convener_id": "saanvi_pi",
            "peer_one_id": "tomas_pi",
            "peer_two_id": "uma_pi",
            "convener_owner": "saanvi",
            "peer_one_owner": "tomas",
            "peer_two_owner": "uma",
        },
    )


def _kwargs_marble_bargaining() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {
            "scenario_id": "marble_bargaining_phase5_v0",
            "buyer_id": "alice_buyer",
            "seller_id": "bob_seller",
            "buyer_owner": "alice",
            "seller_owner": "bob",
            "buyer_budget_ceiling": 60.0,
            "seller_reservation": 40.0,
            "market_reference_price": 50.0,
        },
        {
            "scenario_id": "marble_bargaining_phase5_v1",
            "buyer_id": "vera_buyer",
            "seller_id": "william_seller",
            "buyer_owner": "vera",
            "seller_owner": "william",
            "buyer_budget_ceiling": 120.0,
            "seller_reservation": 80.0,
            "market_reference_price": 100.0,
        },
        {
            "scenario_id": "marble_bargaining_phase5_v2",
            "buyer_id": "xenia_buyer",
            "seller_id": "yusuf_seller",
            "buyer_owner": "xenia",
            "seller_owner": "yusuf",
            "buyer_budget_ceiling": 240.0,
            "seller_reservation": 160.0,
            "market_reference_price": 200.0,
        },
    )


def _kwargs_wildclaw_social() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {
            "scenario_id": "wildclaw_social_meeting_negotiation_phase5_v0",
            "director_id": "alice_director_assistant",
            "participant_one_id": "bob_assistant",
            "participant_two_id": "carol_assistant",
            "participant_three_id": "dave_assistant",
            "director_owner": "alice",
            "participant_one_owner": "bob",
            "participant_two_owner": "carol",
            "participant_three_owner": "dave",
            "meeting_id": "MTG-7",
        },
        {
            "scenario_id": "wildclaw_social_meeting_negotiation_phase5_v1",
            "director_id": "zara_director_assistant",
            "participant_one_id": "aiden_assistant",
            "participant_two_id": "blair_assistant",
            "participant_three_id": "cyrus_assistant",
            "director_owner": "zara",
            "participant_one_owner": "aiden",
            "participant_two_owner": "blair",
            "participant_three_owner": "cyrus",
            "meeting_id": "MTG-12",
        },
        {
            "scenario_id": "wildclaw_social_meeting_negotiation_phase5_v2",
            "director_id": "delia_director_assistant",
            "participant_one_id": "elliot_assistant",
            "participant_two_id": "freya_assistant",
            "participant_three_id": "graham_assistant",
            "director_owner": "delia",
            "participant_one_owner": "elliot",
            "participant_two_owner": "freya",
            "participant_three_owner": "graham",
            "meeting_id": "MTG-21",
        },
    )


def _label_from_kwargs(family_id: str, kwargs: dict[str, Any]) -> str:
    """A short human-readable label baked from the variant identity.

    Used in artifact paths and reports so it is easy to tell which
    variant a bundle came from.
    """
    if family_id in {"tau2_retail", "tau2_telecom"}:
        return (
            f"{kwargs['primary_owner']}_{kwargs['secondary_owner']}_"
            f"{kwargs.get('household_id') or kwargs.get('account_id')}"
        )
    if family_id == "tau2_airline":
        return (
            f"{kwargs['organizer_owner']}_{kwargs['traveler_owner']}_"
            f"{kwargs['group_id']}"
        )
    if family_id == "marble_research":
        return (
            f"{kwargs['convener_owner']}_"
            f"{kwargs['peer_one_owner']}_{kwargs['peer_two_owner']}"
        )
    if family_id == "marble_bargaining":
        return (
            f"{kwargs['buyer_owner']}_{kwargs['seller_owner']}_"
            f"ref{int(kwargs['market_reference_price'])}"
        )
    if family_id == "wildclaw_social":
        return (
            f"{kwargs['director_owner']}_"
            f"{kwargs['participant_one_owner']}_"
            f"{kwargs['participant_two_owner']}_"
            f"{kwargs['participant_three_owner']}_"
            f"{kwargs['meeting_id']}"
        )
    return f"task{kwargs.get('scenario_id', 'unknown')}"


_FAMILY_KWARG_BUILDERS = {
    "tau2_retail": _kwargs_tau2_retail,
    "tau2_airline": _kwargs_tau2_airline,
    "tau2_telecom": _kwargs_tau2_telecom,
    "marble_research": _kwargs_marble_research,
    "marble_bargaining": _kwargs_marble_bargaining,
    "wildclaw_social": _kwargs_wildclaw_social,
}


def task_variants_for(family_id: str) -> tuple[TaskVariantSpec, ...]:
    """Return the three frozen task-variant specs for ``family_id``.

    Raises ``KeyError`` for an unknown family with a helpful message.
    """
    if family_id not in _FAMILY_KWARG_BUILDERS:
        raise KeyError(
            f"no task variants registered for family_id={family_id!r}; "
            f"known: {sorted(_FAMILY_KWARG_BUILDERS.keys())}"
        )
    kwargs_tuple = _FAMILY_KWARG_BUILDERS[family_id]()
    return tuple(
        TaskVariantSpec(
            task_index=index,
            label=_label_from_kwargs(family_id, kwargs),
            loader_kwargs=dict(kwargs),
        )
        for index, kwargs in enumerate(kwargs_tuple)
    )


def task_variant_at(family_id: str, task_index: int) -> TaskVariantSpec:
    """Convenience: return one specific variant.

    Raises ``KeyError`` for unknown family, ``IndexError`` for unknown
    task_index.
    """
    variants = task_variants_for(family_id)
    if not 0 <= task_index < len(variants):
        raise IndexError(
            f"task_index {task_index} out of range [0, {len(variants)}) "
            f"for family_id={family_id!r}"
        )
    return variants[task_index]
