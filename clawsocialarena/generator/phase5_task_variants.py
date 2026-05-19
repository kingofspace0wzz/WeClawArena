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

marble_research is an exception: it has 8 task variants, one per
MarbleResearchTaskSpec in marble_seed_data.ALL_TASKS.

Tests in :mod:`tests.test_generator.test_phase5_task_variants`
exercise this module against every registered family.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clawsocialarena.generator.family_packs.marble_research.marble_seed_data import (
    ALL_TASKS as _MARBLE_RESEARCH_ALL_TASKS,
)
from clawsocialarena.generator.family_packs.marble_bargaining.bargaining_seed_data import (
    BARGAINING_TASK_SEEDS as _MARBLE_BARGAINING_TASK_SEEDS,
    bargaining_task_seeds_for_cell as _marble_bargaining_seeds_for_cell,
)

@dataclass(frozen=True)
class TaskVariantSpec:
    """One identity-variant entry for a family pack."""

    task_index: int  # 0, 1, or 2
    label: str  # short human-readable tag (e.g. "alice_bob_HH7")
    loader_kwargs: dict[str, Any]


def _kwargs_claw_clinical() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {
            "scenario_id": "claw_clinical_referral_phase5_v0",
            "case_key": "referral_ent_001",
            "attending_id": "attending_agent",
            "specialist_id": "specialist_agent",
            "pharmacist_id": "pharmacist_agent",
            "insurance_id": "insurance_agent",
            "nurse_id": "nurse_agent",
            "attending_owner": "dr_martinez",
            "specialist_owner": "dr_chen",
            "pharmacist_owner": "rx_williams",
            "insurance_owner": "ins_bluecross",
            "nurse_owner": "rn_johnson",
        },
        {
            "scenario_id": "claw_clinical_referral_phase5_v1",
            "case_key": "discharge_planning_002",
            "attending_id": "attending_park",
            "specialist_id": "specialist_lee",
            "pharmacist_id": "pharmacist_garcia",
            "insurance_id": "insurance_aetna",
            "nurse_id": "nurse_thompson",
            "attending_owner": "dr_park",
            "specialist_owner": "dr_lee",
            "pharmacist_owner": "rx_garcia",
            "insurance_owner": "ins_aetna",
            "nurse_owner": "rn_thompson",
        },
        {
            "scenario_id": "claw_clinical_referral_phase5_v2",
            "case_key": "emergency_004",
            "attending_id": "attending_nguyen",
            "specialist_id": "specialist_patel",
            "pharmacist_id": "pharmacist_brown",
            "insurance_id": "insurance_cigna",
            "nurse_id": "nurse_davis",
            "attending_owner": "dr_nguyen",
            "specialist_owner": "dr_patel",
            "pharmacist_owner": "rx_brown",
            "insurance_owner": "ins_cigna",
            "nurse_owner": "rn_davis",
        },
    )


def _kwargs_claw_trading() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {
            "scenario_id": "claw_trading_club_phase5_v0",
            "case_key": "earnings_debate_001",
        },
        {
            "scenario_id": "claw_trading_club_phase5_v1",
            "case_key": "sector_rotation_003",
        },
        {
            "scenario_id": "claw_trading_club_phase5_v2",
            "case_key": "new_member_004",
        },
    )


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


def _kwargs_marble_research() -> tuple[dict[str, Any], ...]:
    """Return 8 task-variant kwarg dicts, one per MarbleResearchTaskSpec.

    Each dict drives the marble_research loader with the full task context:
    the seed, proposal, convener, participating PI subset, and topic text.
    The participating_owners tuple drives variable-N PI graph construction
    inside the loader.
    """
    return tuple(
        {
            "scenario_id": (f"marble_research_collaboration_phase5_v{task.task_index}"),
            "seed_id": task.seed_id,
            "proposal_id": task.proposal_id,
            "convener_owner": task.convener_owner,
            "convener_id": f"{task.convener_owner}_pi",
            "participating_owners": task.participating_owners,
            "proposal_topic_title": task.proposal_topic_title,
            "proposal_topic_intro": task.proposal_topic_intro,
        }
        for task in _MARBLE_RESEARCH_ALL_TASKS
    )


def _kwargs_marble_bargaining(
    *, cell_id: str | None = None
) -> tuple[dict[str, Any], ...]:
    """Return task-variant kwarg dicts for marble_bargaining."""
    seeds = (
        _marble_bargaining_seeds_for_cell(cell_id)
        if cell_id is not None
        else _MARBLE_BARGAINING_TASK_SEEDS
    )
    return tuple(dict(seed.loader_kwargs()) for seed in seeds)


def _kwargs_marble_bidding(
    *, cell_id: str | None = None
) -> tuple[dict[str, Any], ...]:
    """Return task-variant kwarg dicts for owned-ecosystem marble_bidding."""
    from clawsocialarena.generator.family_packs.marble_bidding.bidding_seed_data import (
        MARBLE_BIDDING_TASK_SEEDS as _MARBLE_BIDDING_TASK_SEEDS,
        bidding_task_seeds_for_cell as _marble_bidding_seeds_for_cell,
    )

    seeds = (
        _marble_bidding_seeds_for_cell(cell_id)
        if cell_id is not None
        else _MARBLE_BIDDING_TASK_SEEDS
    )
    return tuple(dict(seed.loader_kwargs()) for seed in seeds)


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


def _kwargs_swebench_workspace() -> tuple[dict[str, Any], ...]:
    """Return task-variant kwarg dicts for swebench_workspace."""
    from clawsocialarena.generator.family_packs.swebench_workspace.seed_data import (
        WORKSPACE_TASK_SEEDS as _SWEBENCH_WORKSPACE_TASK_SEEDS,
    )

    return tuple(dict(seed.loader_kwargs()) for seed in _SWEBENCH_WORKSPACE_TASK_SEEDS)


def _label_from_kwargs(family_id: str, kwargs: dict[str, Any]) -> str:
    """A short human-readable label baked from the variant identity.

    Used in artifact paths and reports so it is easy to tell which
    variant a bundle came from.
    """
    if family_id == "claw_clinical":
        return (
            f"{kwargs['attending_owner']}_{kwargs['specialist_owner']}_"
            f"{kwargs['case_key']}"
        )
    if family_id == "claw_trading":
        return kwargs["case_key"]
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
        owners = kwargs["participating_owners"]
        return "_".join(owners) + f"_{kwargs['proposal_id']}"
    if family_id == "marble_bargaining":
        return f"{kwargs['buyer_owner']}_{kwargs['seller_owner']}_{kwargs['item_id']}"
    if family_id == "marble_bidding":
        return (
            f"{kwargs['seller_owner']}_"
            f"{'_'.join(kwargs['buyer_owners'])}_"
            f"{kwargs['item_id']}"
        )
    if family_id == "wildclaw_social":
        return (
            f"{kwargs['director_owner']}_"
            f"{kwargs['participant_one_owner']}_"
            f"{kwargs['participant_two_owner']}_"
            f"{kwargs['participant_three_owner']}_"
            f"{kwargs['meeting_id']}"
        )
    if family_id == "swebench_workspace":
        return (
            f"{kwargs['implementer_owner']}_{kwargs['reviewer_owner']}_"
            f"{kwargs['code_owner']}_{kwargs['instance_id']}"
        )
    if family_id == "travel":
        return f"{kwargs['trip_id']}_{kwargs['resource_profile']}"
    return f"task{kwargs.get('scenario_id', 'unknown')}"


def _kwargs_travel(*, cell_id: str | None = None) -> tuple[dict, ...]:
    """Return task-variant kwarg dicts for the travel family.

    Routes ``CU-D-travel`` and ``MG-C-travel`` to their respective seed
    slices in :mod:`travel_seed_data`; unknown / None ``cell_id``
    returns every seed (used by audit listings).
    """
    from clawsocialarena.generator.family_packs.travel.seed_data.travel_seeds import (
        travel_task_seeds_for_cell as _travel_seeds_for_cell,
    )

    seeds = _travel_seeds_for_cell(cell_id)
    return tuple(
        {
            "scenario_id": f"travel_{s.trip_id.lower()}_phase5_v0",
            "trip_id": s.trip_id,
            "resource_profile": s.resource_profile,
        }
        for s in seeds
    )


_FAMILY_KWARG_BUILDERS = {
    "claw_clinical": _kwargs_claw_clinical,
    "claw_trading": _kwargs_claw_trading,
    "tau2_retail": _kwargs_tau2_retail,
    "tau2_airline": _kwargs_tau2_airline,
    "tau2_telecom": _kwargs_tau2_telecom,
    "marble_research": _kwargs_marble_research,
    "marble_bargaining": _kwargs_marble_bargaining,
    "marble_bidding": _kwargs_marble_bidding,
    "swebench_workspace": _kwargs_swebench_workspace,
    "wildclaw_social": _kwargs_wildclaw_social,
    "travel": _kwargs_travel,
}


def task_variants_for(
    family_id: str,
    *,
    cell_id: str | None = None,
) -> tuple[TaskVariantSpec, ...]:
    """Return the frozen task-variant specs for ``family_id``.

    Most families return 3 variants; marble_research returns 8. When
    ``family_id`` is ``marble_bargaining`` or ``marble_bidding``,
    ``cell_id`` narrows the family grid to the slice used by the base
    generator.
    Raises ``KeyError`` for an unknown family with a helpful message.
    """
    if family_id not in _FAMILY_KWARG_BUILDERS:
        raise KeyError(
            f"no task variants registered for family_id={family_id!r}; "
            f"known: {sorted(_FAMILY_KWARG_BUILDERS.keys())}"
        )
    if family_id == "marble_bargaining":
        kwargs_tuple = _kwargs_marble_bargaining(cell_id=cell_id)
    elif family_id == "marble_bidding":
        kwargs_tuple = _kwargs_marble_bidding(cell_id=cell_id)
    elif family_id == "travel":
        kwargs_tuple = _kwargs_travel(cell_id=cell_id)
    else:
        kwargs_tuple = _FAMILY_KWARG_BUILDERS[family_id]()
    return tuple(
        TaskVariantSpec(
            task_index=index,
            label=_label_from_kwargs(family_id, kwargs),
            loader_kwargs=dict(kwargs),
        )
        for index, kwargs in enumerate(kwargs_tuple)
    )


def task_variant_at(
    family_id: str,
    task_index: int,
    *,
    cell_id: str | None = None,
) -> TaskVariantSpec:
    """Convenience: return one specific variant.

    Raises ``KeyError`` for unknown family, ``IndexError`` for unknown
    task_index.
    """
    variants = task_variants_for(family_id, cell_id=cell_id)
    if not 0 <= task_index < len(variants):
        raise IndexError(
            f"task_index {task_index} out of range [0, {len(variants)}) "
            f"for family_id={family_id!r}"
        )
    return variants[task_index]
