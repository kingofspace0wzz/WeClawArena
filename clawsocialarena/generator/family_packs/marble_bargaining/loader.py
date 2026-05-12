"""marble_bargaining family pack loader.

Reads MARBLE bargaining-negotiation tasks and reframes them as a
2-agent (buyer + seller) negotiation with explicit private-constraint
privacy rules. Buyer has a private budget_ceiling; seller has a
private reservation_price. An accepted offer must fit inside both.
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
class BargainingScenarioBundle:
    """Output of one marble_bargaining loader call."""

    scenario: Scenario
    evaluation_criteria: dict[str, Any]
    governance_seed: dict[str, Any]
    declared_resource_ids: list[str]
    phase_schedule: list[dict[str, Any]]
    item_description: str
    seller_reservation: float
    buyer_budget_ceiling: float
    market_reference_price: float


_MARBLE_ROOT = (
    Path(__file__).resolve().parents[4]
    / "knowledge"
    / "MARBLE"
    / "multiagentbench"
    / "bargaining"
)
_FAMILY_PACK_ROOT = Path(__file__).resolve().parent


class MarbleBargainingLoader:
    """Loader for the marble_bargaining family pack."""

    def __init__(self, marble_root: Path | None = None) -> None:
        self._root = Path(marble_root) if marble_root is not None else _MARBLE_ROOT
        self._tasks: list[dict[str, Any]] | None = None
        self._phase_schedule: list[dict[str, Any]] | None = None

    def _load_tasks(self) -> list[dict[str, Any]]:
        if self._tasks is None:
            text = (self._root / "bargaining_main.jsonl").read_text()
            self._tasks = [json.loads(line) for line in text.splitlines() if line.strip()]
        return self._tasks

    def load_phase_schedule(self) -> list[dict[str, Any]]:
        if self._phase_schedule is None:
            raw = json.loads((_FAMILY_PACK_ROOT / "phase_schedule.json").read_text())
            self._phase_schedule = list(raw.get("phases", []))
        return self._phase_schedule

    def load_bargaining(
        self,
        *,
        scenario_id: str = "marble_bargaining_001",
        buyer_id: str = "alice_buyer",
        seller_id: str = "bob_seller",
        buyer_owner: str = "alice",
        seller_owner: str = "bob",
        buyer_budget_ceiling: float = 60.0,
        seller_reservation: float = 40.0,
        market_reference_price: float = 50.0,
    ) -> BargainingScenarioBundle:
        """Build the canonical buyer/seller negotiation scenario."""
        tasks = self._load_tasks()
        if not tasks:
            raise RuntimeError("marble bargaining_main.jsonl is empty")
        source = tasks[0]
        item_description = _shorten(
            source.get("task", {}).get("content", "Replacement Remote Control"),
            limit=400,
        )

        buyer_agent = ScenarioAgent(
            agent_id=buyer_id,
            user_id=buyer_owner,
            system_prompt_template=_buyer_prompt(buyer_owner, buyer_budget_ceiling),
        )
        seller_agent = ScenarioAgent(
            agent_id=seller_id,
            user_id=seller_owner,
            system_prompt_template=_seller_prompt(seller_owner, seller_reservation),
        )

        buyer_node = AgentGraphNode(
            agent_id=buyer_id,
            owner_id=buyer_owner,
            persona_source=f"personas/{buyer_id}.md",
            role_label="buyer",
            active_identity=f"{buyer_owner}@market",
            scope=[
                "read:market_reference",
                "write:own_offers",
                "read:own_budget",
                "accept:offers_within_budget",
            ],
            approval_mandate="self",
        )
        seller_node = AgentGraphNode(
            agent_id=seller_id,
            owner_id=seller_owner,
            persona_source=f"personas/{seller_id}.md",
            role_label="seller",
            active_identity=f"{seller_owner}@market",
            scope=[
                "read:market_reference",
                "write:own_offers",
                "read:own_reservation",
                "accept:offers_above_reservation",
            ],
            approval_mandate="self",
        )
        edge = AgentGraphEdge(
            source=buyer_id,
            target=seller_id,
            relationship="negotiates_with",
            channel="market_dm",
        )
        graph = AgentGraph(nodes=[buyer_node, seller_node], edges=[edge])

        scenario = Scenario(
            scenario_id=scenario_id,
            category="CM",
            task_family="coordination",
            agents=[buyer_agent, seller_agent],
            initial_state={
                "item_id": "ITEM-7",
                "item_description": item_description,
                "market_reference_price": market_reference_price,
            },
            max_turns=12,
            opening_message={
                "from": "system",
                "to": buyer_id,
                "content": _opening_message_for_buyer(
                    buyer_owner=buyer_owner,
                    item_description=item_description,
                    market_reference_price=market_reference_price,
                ),
            },
            coordination_mode=CoordinationMode.GRAPH,
            agent_graph=graph,
            family_id="marble_bargaining",
        )

        evaluation_criteria = _evaluation_criteria(
            item_id="ITEM-7",
            buyer_id=buyer_id,
        )
        governance_seed = {
            "policy_excerpt": (
                "Buyer must not accept above their budget ceiling. Seller must "
                "not accept below their reservation price. Constraints are private."
            ),
            "bargaining_rules": {
                "buyer_budget_is_private": True,
                "seller_reservation_is_private": True,
                "accept_only_within_window": True,
            },
            "owner_ids": [buyer_owner, seller_owner],
        }
        declared_resource_ids = [
            "shared.market_reference",
            f"agent.{buyer_owner}.budget_ceiling",
            f"agent.{seller_owner}.reservation_price",
        ]
        return BargainingScenarioBundle(
            scenario=scenario,
            evaluation_criteria=evaluation_criteria,
            governance_seed=governance_seed,
            declared_resource_ids=declared_resource_ids,
            phase_schedule=self.load_phase_schedule(),
            item_description=item_description,
            seller_reservation=seller_reservation,
            buyer_budget_ceiling=buyer_budget_ceiling,
            market_reference_price=market_reference_price,
        )


def load_bargaining_scenario(**kwargs: Any) -> BargainingScenarioBundle:
    return MarbleBargainingLoader().load_bargaining(**kwargs)


def _buyer_prompt(owner: str, budget: float) -> str:
    return (
        f"You are {owner}, a buyer negotiating for the item in question. "
        f"Your private budget ceiling is ${budget:.2f} -- you must not "
        "accept any offer above this. Do not reveal your budget to the "
        "seller. Aim to close at a price below your budget."
    )


def _seller_prompt(owner: str, reservation: float) -> str:
    return (
        f"You are {owner}, a seller negotiating for the item in question. "
        f"Your private reservation price is ${reservation:.2f} -- you "
        "must not accept any offer below this. Do not reveal your "
        "reservation to the buyer. Aim to close at a price above your "
        "reservation."
    )


def _opening_message_for_buyer(
    *,
    buyer_owner: str,
    item_description: str,
    market_reference_price: float,
) -> str:
    return (
        f"{buyer_owner.title()}, you are negotiating to buy the following "
        f"item: {item_description[:120]}... The market reference price is "
        f"${market_reference_price:.2f}. Open with an offer; the seller's "
        "assistant will respond."
    )


def _evaluation_criteria(
    *,
    item_id: str,
    buyer_id: str,
) -> dict[str, Any]:
    return {
        "reward_basis": "COMPOSITE",
        "actions": [
            {
                "agent_id": buyer_id,
                "tool_name": "accept_offer",
                "compare_args": ["item_id"],
            },
        ],
        "env_assertions": [
            {
                "predicate": "agreement_recorded_for_item",
                "args": {"item_id": item_id},
            },
            {
                "predicate": "agreed_price_within_window",
                "args": {"item_id": item_id},
            },
        ],
        "communicate_info": [
            {
                "agent_id": buyer_id,
                "must_say": [item_id, "offer accepted"],
            },
        ],
        "nl_assertions": [],
    }


def _shorten(text: str, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    return text[:limit].strip()
