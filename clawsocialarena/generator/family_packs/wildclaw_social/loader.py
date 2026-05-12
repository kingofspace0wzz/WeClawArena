"""wildclaw_social family pack loader.

Reframes the WildClawBench Social-Interaction meeting-negotiation task
as a 4-agent star graph (director hub + three participants). Each
participant has private calendar availability; no meeting may be
created without each participant's confirm_attendance.
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
class MeetingNegotiationBundle:
    """Output of one wildclaw_social loader call."""

    scenario: Scenario
    evaluation_criteria: dict[str, Any]
    governance_seed: dict[str, Any]
    declared_resource_ids: list[str]
    phase_schedule: list[dict[str, Any]]
    participant_availability: dict[str, list[dict[str, Any]]]


_WILDCLAW_ROOT = (
    Path(__file__).resolve().parents[4]
    / "knowledge"
    / "WildClawBench"
    / "tasks"
    / "03_Social_Interaction"
)
_FAMILY_PACK_ROOT = Path(__file__).resolve().parent


class WildClawSocialLoader:
    """Loader for the wildclaw_social family pack."""

    def __init__(self, wildclaw_root: Path | None = None) -> None:
        self._root = (
            Path(wildclaw_root) if wildclaw_root is not None else _WILDCLAW_ROOT
        )
        self._phase_schedule: list[dict[str, Any]] | None = None
        self._source_excerpt: str | None = None

    def _load_source_excerpt(self) -> str:
        if self._source_excerpt is None:
            md = self._root / "03_Social_Interaction_task_1_meeting_negotiation.md"
            if md.is_file():
                self._source_excerpt = md.read_text(encoding="utf-8")[:800]
            else:
                self._source_excerpt = ""
        return self._source_excerpt

    def load_phase_schedule(self) -> list[dict[str, Any]]:
        if self._phase_schedule is None:
            raw = json.loads((_FAMILY_PACK_ROOT / "phase_schedule.json").read_text())
            self._phase_schedule = list(raw.get("phases", []))
        return self._phase_schedule

    def load_meeting_negotiation(
        self,
        *,
        scenario_id: str = "wildclaw_social_meeting_negotiation_001",
        director_id: str = "alice_director_assistant",
        participant_one_id: str = "bob_assistant",
        participant_two_id: str = "carol_assistant",
        participant_three_id: str = "dave_assistant",
        director_owner: str = "alice",
        participant_one_owner: str = "bob",
        participant_two_owner: str = "carol",
        participant_three_owner: str = "dave",
        meeting_id: str = "MTG-7",
    ) -> MeetingNegotiationBundle:
        """Build the canonical meeting-negotiation scenario."""
        director_agent = ScenarioAgent(
            agent_id=director_id,
            user_id=director_owner,
            system_prompt_template=_director_prompt(director_owner, meeting_id),
        )
        participant_owners = (
            participant_one_owner,
            participant_two_owner,
            participant_three_owner,
        )
        participant_ids = (
            participant_one_id,
            participant_two_id,
            participant_three_id,
        )
        participant_agents = [
            ScenarioAgent(
                agent_id=pid,
                user_id=powner,
                system_prompt_template=_participant_prompt(powner, meeting_id),
            )
            for pid, powner in zip(participant_ids, participant_owners)
        ]
        scenario_agents = [director_agent, *participant_agents]

        director_node = AgentGraphNode(
            agent_id=director_id,
            owner_id=director_owner,
            persona_source=f"personas/{director_id}.md",
            role_label="meeting_organizer",
            active_identity=f"{director_owner}@team",
            scope=[
                "read:shared_meeting_purpose",
                "write:meeting_proposal",
                "send_email:any_participant",
                "create_calendar_event:after_all_confirmations",
            ],
            approval_mandate="self",
        )
        participant_nodes = [
            AgentGraphNode(
                agent_id=pid,
                owner_id=powner,
                persona_source=f"personas/{pid}.md",
                role_label="meeting_participant",
                active_identity=f"{powner}@team",
                scope=[
                    "read:own_calendar",
                    "read:own_inbox",
                    "confirm:own_attendance",
                ],
                approval_mandate="self",
            )
            for pid, powner in zip(participant_ids, participant_owners)
        ]
        edges = [
            AgentGraphEdge(
                source=director_id,
                target=pid,
                relationship="organizes_for",
                channel="team_dm",
            )
            for pid in participant_ids
        ] + [
            AgentGraphEdge(
                source=pid,
                target=director_id,
                relationship="reports_back_to",
                channel="team_dm",
            )
            for pid in participant_ids
        ]
        graph = AgentGraph(nodes=[director_node, *participant_nodes], edges=edges)

        scenario = Scenario(
            scenario_id=scenario_id,
            category="MC",
            task_family="coordination",
            agents=scenario_agents,
            initial_state={
                "meeting_id": meeting_id,
                "purpose": "Q2 Product Review",
                "duration_minutes": 90,
                "source_excerpt": self._load_source_excerpt(),
            },
            max_turns=14,
            opening_message={
                "from": "system",
                "to": director_id,
                "content": _opening_message_for_director(
                    director_owner=director_owner,
                    participant_owners=list(participant_owners),
                ),
            },
            coordination_mode=CoordinationMode.STAR,
            agent_graph=graph,
            family_id="wildclaw_social",
        )

        participant_availability = _seed_participant_availability(
            participant_owners=participant_owners,
        )
        evaluation_criteria = _evaluation_criteria(
            meeting_id=meeting_id,
            director_id=director_id,
            participant_owners=list(participant_owners),
        )
        governance_seed = {
            "policy_excerpt": (
                "A meeting cannot be created without explicit confirmation "
                "from every invited participant. Director's room preference "
                "outranks participants' on room selection."
            ),
            "meeting_rules": {
                "all_participants_must_confirm_attendance": True,
                "director_owns_room_decision": True,
                "participants_own_their_availability": True,
            },
            "owner_ids": [director_owner, *participant_owners],
        }
        declared_resource_ids = [
            "shared.meeting_purpose",
            f"director.{director_owner}.proposal",
        ] + [f"participant.{owner}.calendar" for owner in participant_owners]
        return MeetingNegotiationBundle(
            scenario=scenario,
            evaluation_criteria=evaluation_criteria,
            governance_seed=governance_seed,
            declared_resource_ids=declared_resource_ids,
            phase_schedule=self.load_phase_schedule(),
            participant_availability=participant_availability,
        )


def load_meeting_negotiation_scenario(**kwargs: Any) -> MeetingNegotiationBundle:
    return WildClawSocialLoader().load_meeting_negotiation(**kwargs)


def _seed_participant_availability(
    *,
    participant_owners: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    """Seed deterministic per-participant availability.

    Every participant is free Thursday 09:30-12:00, so the overlap is
    the 90-minute window the canonical task wants. The scenario can
    then test whether the director correctly picks Thursday 09:30 once
    every participant has confirmed.
    """
    common_slot = {
        "day": "Thursday",
        "start": "09:30",
        "end": "12:00",
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for owner in participant_owners:
        out[owner] = [common_slot]
    return out


def _director_prompt(owner: str, meeting_id: str) -> str:
    return (
        f"You are the personal assistant for Director {owner}, scheduling "
        f"meeting {meeting_id}. Coordinate with each participant's "
        "assistant via email, gather their availability, propose a "
        "time, wait for every participant to confirm_attendance, then "
        "create the calendar event. Refuse to create the event before "
        "every participant has explicitly confirmed."
    )


def _participant_prompt(owner: str, meeting_id: str) -> str:
    return (
        f"You are the personal assistant for {owner}, invited to meeting "
        f"{meeting_id}. When the director's assistant proposes a time, "
        "check your calendar and reply via confirm_attendance if you "
        "are free, or decline if you are not. Never confirm on behalf "
        "of another participant."
    )


def _opening_message_for_director(
    *,
    director_owner: str,
    participant_owners: list[str],
) -> str:
    listed = ", ".join(p.title() for p in participant_owners)
    return (
        f"{director_owner.title()}, schedule a 90-minute Q2 Product Review "
        f"with {listed} this week. Coordinate via email, gather "
        "availabilities, propose a time, collect explicit confirmations "
        "from every participant, then create the calendar event."
    )


def _evaluation_criteria(
    *,
    meeting_id: str,
    director_id: str,
    participant_owners: list[str],
) -> dict[str, Any]:
    return {
        "reward_basis": "COMPOSITE",
        "actions": [
            {
                "agent_id": director_id,
                "tool_name": "create_calendar_event",
                "compare_args": ["meeting_id"],
            },
        ],
        "env_assertions": [
            {
                "predicate": "meeting_event_created",
                "args": {"meeting_id": meeting_id},
            },
            {
                "predicate": "all_participants_confirmed_meeting",
                "args": {
                    "meeting_id": meeting_id,
                    "expected_participants": participant_owners,
                },
            },
        ],
        "communicate_info": [
            {
                "agent_id": director_id,
                "must_say": [meeting_id, "meeting confirmed"],
            },
        ],
        "nl_assertions": [],
    }
