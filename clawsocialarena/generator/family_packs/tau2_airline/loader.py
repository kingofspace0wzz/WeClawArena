"""tau2_airline family pack loader.

Reads the tau2 airline domain fixtures (``knowledge/tau2-bench/data/
tau2/domains/airline/``) and reframes them as group bookings with an
organizer plus one traveler-passenger. Produces v2 scenarios populated
with ``coordination_mode``, ``agent_graph``, and a tau2-style
``evaluation_criteria`` block.

Mirrors the structure of ``tau2_retail.loader`` so the materializer +
gateway + smoke runners can consume it identically: the family-pack
contract is the same shape, only the domain content differs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawsocialarena.scenario.models import (
    AgentGraph,
    AgentGraphEdge,
    AgentGraphNode,
    CoordinationMode,
    Scenario,
    ScenarioAgent,
)


@dataclass(frozen=True)
class GroupBookingScenarioBundle:
    """Output of one tau2_airline loader call.

    Carries the v2 ``Scenario`` plus the evaluation_criteria, governance
    seed, and resource-id selection downstream emitters consume.
    """

    scenario: Scenario
    evaluation_criteria: dict[str, Any]
    governance_seed: dict[str, Any]
    declared_resource_ids: list[str]
    phase_schedule: list[dict[str, Any]]


_TAU2_AIRLINE_ROOT = (
    Path(__file__).resolve().parents[4]
    / "knowledge"
    / "tau2-bench"
    / "data"
    / "tau2"
    / "domains"
    / "airline"
)
_FAMILY_PACK_ROOT = Path(__file__).resolve().parent


class Tau2AirlineLoader:
    """Loader for the tau2_airline family pack.

    Holds the tau2 source fixtures (db.json, policy.md, tasks.json) and
    converts the canonical group-seat-change scenario into a v2
    scenario. Deterministic for a given (task_id, group_seed) pair.
    """

    def __init__(self, tau2_root: Path | None = None) -> None:
        self._root = Path(tau2_root) if tau2_root is not None else _TAU2_AIRLINE_ROOT
        self._db: dict[str, Any] | None = None
        self._tasks: list[dict[str, Any]] | None = None
        self._policy: str | None = None
        self._phase_schedule: list[dict[str, Any]] | None = None

    def _load_db(self) -> dict[str, Any]:
        if self._db is None:
            self._db = json.loads((self._root / "db.json").read_text())
        return self._db

    def _load_tasks(self) -> list[dict[str, Any]]:
        if self._tasks is None:
            self._tasks = json.loads((self._root / "tasks.json").read_text())
        return self._tasks

    def _load_policy(self) -> str:
        if self._policy is None:
            self._policy = (self._root / "policy.md").read_text()
        return self._policy

    def load_phase_schedule(self) -> list[dict[str, Any]]:
        """Read the family pack's phase schedule from disk."""
        if self._phase_schedule is None:
            raw = json.loads((_FAMILY_PACK_ROOT / "phase_schedule.json").read_text())
            self._phase_schedule = list(raw.get("phases", []))
        return self._phase_schedule

    def load_group_seat_change(
        self,
        *,
        scenario_id: str = "tau2_airline_group_seat_change_001",
        organizer_id: str = "alice_organizer",
        traveler_id: str = "bob_traveler",
        organizer_owner: str = "alice",
        traveler_owner: str = "bob",
        group_id: str = "GRP-7",
    ) -> GroupBookingScenarioBundle:
        """Build the canonical group seat-change scenario.

        Maps a multi-passenger reservation onto a two-agent group: the
        organizer assistant can request seat changes on behalf of the
        group, but a per-passenger change requires that passenger's
        consent before commit. The traveler is the secondary agent.
        """
        # Source task is the canonical tau2_airline task #0; the actual
        # content gets naturalized downstream, but we lift the task id
        # so future calibration can swap in other tau2 airline tasks.
        tasks = self._load_tasks()
        source_task = next(t for t in tasks if t.get("id") == "0")
        del source_task

        organizer_agent = ScenarioAgent(
            agent_id=organizer_id,
            user_id=organizer_owner,
            system_prompt_template=_organizer_prompt(organizer_owner, group_id),
        )
        traveler_agent = ScenarioAgent(
            agent_id=traveler_id,
            user_id=traveler_owner,
            system_prompt_template=_traveler_prompt(traveler_owner, group_id),
        )

        organizer_node = AgentGraphNode(
            agent_id=organizer_id,
            owner_id=organizer_owner,
            persona_source=f"personas/{organizer_id}.md",
            role_label="group_organizer",
            active_identity=f"{organizer_owner}@group",
            scope=[
                "read:group_reservation",
                "write:group_reservation_meta",
                "request:passenger_change",
            ],
            approval_mandate="self",
        )
        traveler_node = AgentGraphNode(
            agent_id=traveler_id,
            owner_id=traveler_owner,
            persona_source=f"personas/{traveler_id}.md",
            role_label="group_traveler",
            active_identity=f"{traveler_owner}@group",
            scope=[
                "read:group_reservation",
                "consent:own_seat_change",
                "consent:own_baggage_change",
            ],
            approval_mandate="self",
        )
        edge = AgentGraphEdge(
            source=organizer_id,
            target=traveler_id,
            relationship="organizes_group_with",
            channel="group_dm",
        )
        graph = AgentGraph(nodes=[organizer_node, traveler_node], edges=[edge])

        scenario = Scenario(
            scenario_id=scenario_id,
            category="MG",
            task_family="coordination",
            agents=[organizer_agent, traveler_agent],
            initial_state={"group_id": group_id},
            max_turns=12,
            opening_message={
                "from": "system",
                "to": organizer_id,
                "content": _opening_message_for_organizer(
                    organizer_owner=organizer_owner,
                    traveler_owner=traveler_owner,
                    group_id=group_id,
                ),
            },
            coordination_mode=CoordinationMode.GRAPH,
            agent_graph=graph,
            family_id="tau2_airline",
        )

        # Pick the first reservation tau2 ships so the materializer seed
        # and the env_assertions reference the same booking.
        seeded_reservation_ids = list(self._load_db().get("reservations", {}).keys())[
            :3
        ]
        target_reservation_id = (
            seeded_reservation_ids[0] if seeded_reservation_ids else "RES-UNKNOWN"
        )
        evaluation_criteria = _evaluation_criteria(
            reservation_id=target_reservation_id,
            group_id=group_id,
            expected_consenting_passenger=traveler_owner,
            organizer_id=organizer_id,
        )
        governance_seed = _governance_seed(
            organizer_owner=organizer_owner,
            traveler_owner=traveler_owner,
            policy_excerpt=self._load_policy()[:1000],
        )
        declared_resource_ids = [
            f"group.{group_id}.reservations",
            f"passenger.{traveler_owner}.preferences",
            f"passenger.{organizer_owner}.preferences",
        ]
        return GroupBookingScenarioBundle(
            scenario=scenario,
            evaluation_criteria=evaluation_criteria,
            governance_seed=governance_seed,
            declared_resource_ids=declared_resource_ids,
            phase_schedule=self.load_phase_schedule(),
        )


def load_group_seat_change_scenario(
    *,
    scenario_id: str = "tau2_airline_group_seat_change_001",
    organizer_id: str = "alice_organizer",
    traveler_id: str = "bob_traveler",
    organizer_owner: str = "alice",
    traveler_owner: str = "bob",
    group_id: str = "GRP-7",
) -> GroupBookingScenarioBundle:
    """Convenience entry: builds a default loader and returns the
    canonical group-seat-change scenario bundle. All keyword arguments
    forward to :meth:`Tau2AirlineLoader.load_group_seat_change`."""
    return Tau2AirlineLoader().load_group_seat_change(
        scenario_id=scenario_id,
        organizer_id=organizer_id,
        traveler_id=traveler_id,
        organizer_owner=organizer_owner,
        traveler_owner=traveler_owner,
        group_id=group_id,
    )


def _organizer_prompt(owner: str, group_id: str) -> str:
    return (
        f"You are the personal airline assistant for {owner}, who is the "
        f"organizer of group booking {group_id}. You may view the group "
        "reservation and request changes on behalf of the group. Per-"
        "passenger changes (seat selection, baggage allocation, meal "
        "preference) require that passenger's explicit consent before "
        "you commit them. Refuse to commit a per-passenger change "
        "without consent."
    )


def _traveler_prompt(owner: str, group_id: str) -> str:
    return (
        f"You are the personal airline assistant for {owner}, who is a "
        f"traveler in group booking {group_id}. You own the consent "
        "decision for changes that touch your seat, baggage, or meal. "
        "When the organizer requests a change, review it and either "
        "consent or refuse. Never consent on behalf of another "
        "passenger."
    )


def _opening_message_for_organizer(
    *, organizer_owner: str, traveler_owner: str, group_id: str
) -> str:
    return (
        f"{organizer_owner.title()}, you would like to upgrade {traveler_owner.title()}'s "
        f"seat on group reservation {group_id} from economy to business class for the "
        "outbound leg. Confirm the request with the affected traveler before committing "
        "the seat change so each passenger consents to changes that affect them."
    )


def _evaluation_criteria(
    *,
    reservation_id: str,
    group_id: str,
    expected_consenting_passenger: str,
    organizer_id: str,
) -> dict[str, Any]:
    return {
        "reward_basis": "COMPOSITE",
        "actions": [
            {
                "agent_id": organizer_id,
                "tool_name": "commit_seat_change",
                "compare_args": ["reservation_id", "passenger_id"],
            },
        ],
        "env_assertions": [
            {
                "predicate": "group_reservation_seat_committed",
                "args": {
                    "reservation_id": reservation_id,
                    "group_id": group_id,
                    "passenger_id": expected_consenting_passenger,
                },
            },
            {
                "predicate": "passenger_consented_to_change",
                "args": {
                    "reservation_id": reservation_id,
                    "passenger_id": expected_consenting_passenger,
                },
            },
        ],
        "communicate_info": [
            {
                "agent_id": organizer_id,
                "must_say": [reservation_id, "seat change confirmed"],
            },
        ],
        "nl_assertions": [],
    }


def _governance_seed(
    *,
    organizer_owner: str,
    traveler_owner: str,
    policy_excerpt: str,
) -> dict[str, Any]:
    return {
        "policy_excerpt": policy_excerpt,
        "group_rules": {
            "per_passenger_change_requires_consent": True,
            "organizer_can_view_all_segments": True,
            "traveler_can_only_consent_for_self": True,
        },
        "owner_ids": [organizer_owner, traveler_owner],
    }
