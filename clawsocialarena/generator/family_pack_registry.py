"""Single source of truth for family-pack loaders and materializers.

The Phase-5 cell-aware generator and the live pilot orchestrator both
need a uniform way to ask "given this family_id, give me a materialized
bundle on disk." This module exposes that uniform surface:

- :data:`FAMILY_LOADERS` -- a dict mapping ``family_id`` to a
  :class:`FamilyPackEntry` carrying both the loader convenience entry
  and the materializer convenience entry.
- :func:`load_and_materialize` -- one call that hands you
  ``(bundle_dir, bundle)`` for a given family.

Adding a new pack requires (a) the pack itself (loader + materializer)
and (b) one new dict entry below; the rest of the pipeline picks it up
automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from clawsocialarena.generator.family_packs import (
    marble_bargaining as _marble_bargaining_pack,
    marble_research as _marble_research_pack,
    tau2_airline as _tau2_airline_pack,
    tau2_retail as _tau2_retail_pack,
    tau2_telecom as _tau2_telecom_pack,
    wildclaw_social as _wildclaw_social_pack,
)
from clawsocialarena.generator.family_packs.marble_bargaining import (
    load_bargaining_scenario,
    materialize_bargaining_bundle,
)
from clawsocialarena.generator.family_packs.marble_research import (
    load_research_collaboration_scenario,
    materialize_research_collaboration_bundle,
)
from clawsocialarena.generator.family_packs.tau2_airline import (
    load_group_seat_change_scenario,
    materialize_group_booking_bundle,
)
from clawsocialarena.generator.family_packs.tau2_retail import (
    load_household_exchange_scenario,
    materialize_household_bundle,
)
from clawsocialarena.generator.family_packs.tau2_telecom import (
    load_family_plan_roaming_scenario,
    materialize_family_plan_bundle,
)
from clawsocialarena.generator.family_packs.wildclaw_social import (
    load_meeting_negotiation_scenario,
    materialize_meeting_negotiation_bundle,
)


@dataclass(frozen=True)
class FamilyPackEntry:
    """One row in the family-pack registry.

    ``session_context_keys`` enumerates the keys that
    :meth:`clawsocialarena.gateway.session.Session.register_family_pack_tools`
    expects in ``family_pack_context`` for this family. Phase-5 tooling
    consults this when assembling per-pack context payloads from cell
    metadata.

    ``naturalization_hints`` carries the per-pack guidance the Phase-5
    skeleton builder appends to the gpt-5.2 naturalization payload so
    the model can produce domain-appropriate prose and resource
    payloads. The shape is ``{domain, tone, key_terms, naturalization_focus}``.
    """

    family_id: str
    load_fn: Callable[..., Any]
    materialize_fn: Callable[[Any, Path], Path]
    session_context_keys: tuple[str, ...]
    naturalization_hints: dict[str, Any]


FAMILY_LOADERS: dict[str, FamilyPackEntry] = {
    "tau2_retail": FamilyPackEntry(
        family_id="tau2_retail",
        load_fn=load_household_exchange_scenario,
        materialize_fn=materialize_household_bundle,
        session_context_keys=("household_id", "primary_owner_id", "secondary_owner_ids"),
        naturalization_hints=_tau2_retail_pack.NATURALIZATION_HINTS,
    ),
    "tau2_airline": FamilyPackEntry(
        family_id="tau2_airline",
        load_fn=load_group_seat_change_scenario,
        materialize_fn=materialize_group_booking_bundle,
        session_context_keys=("group_id", "organizer_owner_id", "traveler_owner_ids"),
        naturalization_hints=_tau2_airline_pack.NATURALIZATION_HINTS,
    ),
    "tau2_telecom": FamilyPackEntry(
        family_id="tau2_telecom",
        load_fn=load_family_plan_roaming_scenario,
        materialize_fn=materialize_family_plan_bundle,
        session_context_keys=("account_id", "primary_owner_id", "secondary_owner_ids"),
        naturalization_hints=_tau2_telecom_pack.NATURALIZATION_HINTS,
    ),
    "marble_research": FamilyPackEntry(
        family_id="marble_research",
        load_fn=load_research_collaboration_scenario,
        materialize_fn=materialize_research_collaboration_bundle,
        session_context_keys=("proposal_id", "convener_owner_id", "peer_owner_ids"),
        naturalization_hints=_marble_research_pack.NATURALIZATION_HINTS,
    ),
    "marble_bargaining": FamilyPackEntry(
        family_id="marble_bargaining",
        load_fn=load_bargaining_scenario,
        materialize_fn=materialize_bargaining_bundle,
        session_context_keys=(
            "item_id",
            "buyer_owner_id",
            "seller_owner_id",
            "buyer_budget_ceiling",
            "seller_reservation",
            "market_reference_price",
        ),
        naturalization_hints=_marble_bargaining_pack.NATURALIZATION_HINTS,
    ),
    "wildclaw_social": FamilyPackEntry(
        family_id="wildclaw_social",
        load_fn=load_meeting_negotiation_scenario,
        materialize_fn=materialize_meeting_negotiation_bundle,
        session_context_keys=("meeting_id", "organizer_owner_id", "participant_owner_ids"),
        naturalization_hints=_wildclaw_social_pack.NATURALIZATION_HINTS,
    ),
}


def get_entry(family_id: str) -> FamilyPackEntry:
    """Return the registry entry for ``family_id`` or raise ``KeyError``.

    The error message lists the available family_ids so callers can
    diagnose typos quickly.
    """
    try:
        return FAMILY_LOADERS[family_id]
    except KeyError as exc:
        known = sorted(FAMILY_LOADERS.keys())
        raise KeyError(
            f"unknown family_id={family_id!r}; registered ids: {known}"
        ) from exc


def load_and_materialize(
    *,
    family_id: str,
    out_dir: Path | str,
    load_kwargs: dict[str, Any] | None = None,
) -> tuple[Path, Any]:
    """Load + materialize a bundle for the named family.

    Returns a ``(bundle_dir, bundle)`` pair. The ``bundle`` instance is
    the pack-specific frozen dataclass produced by the loader (e.g.
    ``HouseholdScenarioBundle``, ``GroupBookingScenarioBundle``,
    etc.); callers that need uniform access should reach through
    ``bundle.scenario`` / ``bundle.evaluation_criteria`` /
    ``bundle.phase_schedule`` which every pack exposes by contract.
    """
    entry = get_entry(family_id)
    bundle = entry.load_fn(**(load_kwargs or {}))
    bundle_dir = entry.materialize_fn(bundle, Path(out_dir))
    return bundle_dir, bundle
