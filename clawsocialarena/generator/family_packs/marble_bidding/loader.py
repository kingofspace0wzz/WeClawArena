"""marble_bidding family pack loader."""
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
class BiddingScenarioBundle:
    """Output of one owned-ecosystem marble_bidding loader call."""

    scenario: Scenario
    evaluation_criteria: dict[str, Any]
    governance_seed: dict[str, Any]
    declared_resource_ids: list[str]
    phase_schedule: list[dict[str, Any]]
    auction_id: str
    resource_profile: str
    item_id: str
    item_description: str
    quantity: int
    seller_owner_id: str
    buyer_owner_ids: tuple[str, ...]
    seller_agent_id: str
    buyer_agent_ids: tuple[str, ...]
    market_reference_price: float
    seller_minimum_unit_price: float
    buyer_budget_ceiling_by_owner: dict[str, float]
    required_terms: tuple[str, ...]
    owner_workspaces: dict[str, dict[str, Any]]

    @property
    def seller_reservation(self) -> float:
        """Backward-compatible alias for old lightweight bidding callers."""
        return self.seller_minimum_unit_price


_FAMILY_PACK_ROOT = Path(__file__).resolve().parent


class MarbleBiddingLoader:
    """Loader for the marble_bidding family pack."""

    def __init__(self) -> None:
        self._phase_schedule: list[dict[str, Any]] | None = None

    def load_phase_schedule(self) -> list[dict[str, Any]]:
        if self._phase_schedule is None:
            raw = json.loads((_FAMILY_PACK_ROOT / "phase_schedule.json").read_text())
            self._phase_schedule = list(raw.get("phases", []))
        return [dict(phase) for phase in self._phase_schedule]

    def load_bidding(
        self,
        *,
        scenario_id: str = "marble_bidding_phase5_v0",
        auction_id: str = "AUC-BID-000",
        category: str = "CM",
        resource_profile: str = "owned_ecosystem_bidding_easy_two_buyer",
        seller_id: str = "sable_seller",
        seller_owner: str = "sable_supply_sales",
        buyer_ids: tuple[str, ...] = ("anchor_buyer", "beacon_buyer"),
        buyer_owners: tuple[str, ...] = (
            "anchor_procurement",
            "beacon_procurement",
        ),
        item_id: str = "BID-LOT-000",
        item_description: str = "Eight rugged barcode scanners with charging cradles",
        quantity: int = 8,
        market_reference_price: float = 410.0,
        seller_minimum_unit_price: float = 360.0,
        buyer_budget_ceiling_by_owner: dict[str, float] | None = None,
        required_terms: tuple[str, ...] = (
            "delivery_by_2026-06-30",
            "warranty_12_months",
        ),
        owner_workspaces: dict[str, dict[str, Any]] | None = None,
        max_turns: int = 36,
    ) -> BiddingScenarioBundle:
        if category not in {"CM", "CU"}:
            raise ValueError("marble_bidding category must be CM or CU")
        if len(buyer_ids) != len(buyer_owners):
            raise ValueError("buyer_ids and buyer_owners must have the same length")
        if len(buyer_ids) < 2:
            raise ValueError("marble_bidding requires at least two buyers")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        if buyer_budget_ceiling_by_owner is None or owner_workspaces is None:
            from clawsocialarena.generator.family_packs.marble_bidding.bidding_seed_data import (
                MARBLE_BIDDING_TASK_SEEDS,
            )

            seed = MARBLE_BIDDING_TASK_SEEDS[0]
            defaults = seed.loader_kwargs()
            if buyer_budget_ceiling_by_owner is None:
                buyer_budget_ceiling_by_owner = dict(
                    defaults["buyer_budget_ceiling_by_owner"]
                )
            if owner_workspaces is None:
                owner_workspaces = dict(defaults["owner_workspaces"])

        budgets = dict(buyer_budget_ceiling_by_owner)
        missing_budgets = [owner for owner in buyer_owners if owner not in budgets]
        if missing_budgets:
            raise ValueError(
                f"missing buyer budget ceilings for owners: {missing_budgets}"
            )

        workspaces = dict(owner_workspaces)
        missing_workspaces = [
            owner for owner in (seller_owner, *buyer_owners) if owner not in workspaces
        ]
        if missing_workspaces:
            raise ValueError(f"missing owner workspaces: {missing_workspaces}")

        agents = [
            ScenarioAgent(
                agent_id=seller_id,
                user_id=seller_owner,
                system_prompt_template=_seller_prompt(
                    owner=seller_owner,
                    auction_id=auction_id,
                    item_id=item_id,
                ),
            )
        ]
        agents.extend(
            ScenarioAgent(
                agent_id=buyer_id,
                user_id=owner,
                system_prompt_template=_buyer_prompt(
                    owner=owner,
                    auction_id=auction_id,
                    item_id=item_id,
                ),
            )
            for buyer_id, owner in zip(buyer_ids, buyer_owners)
        )

        nodes = [
            AgentGraphNode(
                agent_id=seller_id,
                owner_id=seller_owner,
                persona_source=f"personas/{seller_id}.system.md",
                role_label="seller",
                active_identity=f"{seller_owner}@auction",
                scope=[
                    "read:own_listing",
                    "read:own_inventory",
                    "read:public_bids",
                    "write:award",
                    "write:seller_order",
                ],
                approval_mandate="self",
            )
        ]
        nodes.extend(
            AgentGraphNode(
                agent_id=buyer_id,
                owner_id=owner,
                persona_source=f"personas/{buyer_id}.system.md",
                role_label="buyer",
                active_identity=f"{owner}@auction",
                scope=[
                    "read:own_purchase_request",
                    "read:own_budget",
                    "read:public_bids",
                    "write:own_bid",
                    "write:own_confirmation",
                    "write:own_purchase_order",
                ],
                approval_mandate="self",
            )
            for buyer_id, owner in zip(buyer_ids, buyer_owners)
        )
        edges: list[AgentGraphEdge] = []
        for buyer_id in buyer_ids:
            edges.append(
                AgentGraphEdge(
                    source=seller_id,
                    target=buyer_id,
                    relationship="lists_item_for",
                    channel="auction_dm",
                )
            )
            edges.append(
                AgentGraphEdge(
                    source=buyer_id,
                    target=seller_id,
                    relationship="submits_bid_to",
                    channel="auction_dm",
                )
            )

        scenario = Scenario(
            scenario_id=scenario_id,
            category=category,
            task_family="coordination",
            agents=agents,
            initial_state={
                "auction_id": auction_id,
                "item_id": item_id,
                "item_description": item_description,
                "quantity": quantity,
                "market_reference_price": market_reference_price,
                "buyer_count": len(buyer_ids),
            },
            max_turns=max_turns,
            opening_message={
                "from": "system",
                "to": seller_id,
                "content": _opening_message_for_seller(
                    seller_owner=seller_owner,
                    seller_id=seller_id,
                    item_description=item_description,
                    market_reference_price=market_reference_price,
                    buyer_ids=buyer_ids,
                    buyer_owners=buyer_owners,
                ),
            },
            injected_messages=_opening_messages_for_buyers(
                seller_id=seller_id,
                seller_owner=seller_owner,
                buyer_ids=buyer_ids,
                buyer_owners=buyer_owners,
                auction_id=auction_id,
                item_id=item_id,
                item_description=item_description,
                quantity=quantity,
                market_reference_price=market_reference_price,
            ),
            coordination_mode=CoordinationMode.GRAPH,
            agent_graph=AgentGraph(nodes=nodes, edges=edges),
            family_id="marble_bidding",
        )

        evaluation_criteria = _evaluation_criteria(
            auction_id=auction_id,
            item_id=item_id,
            seller_id=seller_id,
        )
        governance_seed = {
            "policy_excerpt": (
                "Seller must use owned inventory, price book, and policy resources. "
                "Buyers must use owned budget and purchase-request resources."
            ),
            "bidding_rules": {
                "seller_constraints_are_private": True,
                "buyer_budgets_are_private": True,
                "seller_award_requires_buyer_confirmation": True,
                "buyer_and_seller_close_artifacts_required": True,
                "bids_are_public": True,
            },
            "owner_ids": [seller_owner, *buyer_owners],
        }
        declared_resource_ids = [
            f"auction.{auction_id}.listing",
            f"owner.{seller_owner}.inventory",
            f"owner.{seller_owner}.price_book",
            f"auction.{auction_id}.public_bids",
            *[f"owner.{owner}.budget_ledger" for owner in buyer_owners],
            *[f"owner.{owner}.purchase_request" for owner in buyer_owners],
        ]
        return BiddingScenarioBundle(
            scenario=scenario,
            evaluation_criteria=evaluation_criteria,
            governance_seed=governance_seed,
            declared_resource_ids=declared_resource_ids,
            phase_schedule=self.load_phase_schedule(),
            auction_id=auction_id,
            resource_profile=resource_profile,
            item_id=item_id,
            item_description=item_description,
            quantity=quantity,
            seller_owner_id=seller_owner,
            buyer_owner_ids=tuple(buyer_owners),
            seller_agent_id=seller_id,
            buyer_agent_ids=tuple(buyer_ids),
            market_reference_price=market_reference_price,
            seller_minimum_unit_price=seller_minimum_unit_price,
            buyer_budget_ceiling_by_owner=budgets,
            required_terms=tuple(required_terms),
            owner_workspaces=workspaces,
        )


def load_bidding_scenario(**kwargs: Any) -> BiddingScenarioBundle:
    return MarbleBiddingLoader().load_bidding(**kwargs)


def _buyer_prompt(owner: str, auction_id: str, item_id: str) -> str:
    return (
        f"You are {owner}, a buyer in auction {auction_id} for {item_id}. "
        "Use owned files and tables before bidding. Do not reveal private "
        "budget ceilings or strategy notes. Confirm only awards for your own "
        "public bids and record purchase orders only for valid awards."
    )


def _seller_prompt(owner: str, auction_id: str, item_id: str) -> str:
    return (
        f"You are {owner}, the seller running auction {auction_id} for {item_id}. "
        "Use owned inventory, price book, and policy resources before awarding. "
        "Do not reveal reservation or margin constraints. Award only a public "
        "bid that satisfies seller policy and required terms."
    )


def _opening_message_for_seller(
    *,
    seller_owner: str,
    seller_id: str,
    item_description: str,
    market_reference_price: float,
    buyer_ids: tuple[str, ...],
    buyer_owners: tuple[str, ...],
) -> str:
    buyers = ", ".join(
        f"{buyer_id} (`{buyer_owner}`)"
        for buyer_id, buyer_owner in zip(buyer_ids, buyer_owners)
    )
    return (
        f"{seller_owner.title()}, list the item directly for buyer agents {buyers}: "
        f"{item_description[:120]}... The public market reference price is "
        f"${market_reference_price:.2f}. Invite every buyer, wait for at least "
        "two public bids, accept one acceptable bid, and ask the winning buyer "
        "to confirm. If seller_award_bid reports not_enough_distinct_bidders, "
        "contact the missing buyer agents directly and wait for their public bids. "
        f"Do not announce an award from {seller_id} until seller_award_bid returns ok=true."
    )


def _opening_messages_for_buyers(
    *,
    seller_id: str,
    seller_owner: str,
    buyer_ids: tuple[str, ...],
    buyer_owners: tuple[str, ...],
    auction_id: str,
    item_id: str,
    item_description: str,
    quantity: int,
    market_reference_price: float,
) -> list[dict[str, str]]:
    notices: list[dict[str, str]] = []
    for buyer_id, buyer_owner in zip(buyer_ids, buyer_owners):
        notices.append(
            {
                "from": "system",
                "to": buyer_id,
                "content": (
                    f"Auction notice for {buyer_owner}: {seller_owner} via "
                    f"{seller_id} is taking public bids in auction {auction_id} "
                    f"for {quantity} units of {item_description} ({item_id}). "
                    f"The public market reference price is ${market_reference_price:.2f}. "
                    "Before bidding, call read_owned_file for purchase_request.md "
                    "and query_owned_table for budget_ledger using your owner_id. "
                    "Then call submit_bid with canonical auction_id, item_id, "
                    "buyer_owner_id, unit_price, quantity, and exact required "
                    "terms from your owned purchase request."
                ),
            }
        )
    return notices


def _evaluation_criteria(
    *,
    auction_id: str,
    item_id: str,
    seller_id: str,
) -> dict[str, Any]:
    return {
        "reward_basis": "COMPOSITE",
        "actions": [
            {
                "agent_id": "*",
                "tool_name": "submit_bid",
                "compare_args": ["auction_id", "item_id"],
            },
            {
                "agent_id": seller_id,
                "tool_name": "seller_award_bid",
                "compare_args": ["auction_id", "item_id"],
            },
            {
                "agent_id": "*",
                "tool_name": "buyer_confirm_award",
                "compare_args": ["auction_id", "item_id"],
            },
            {
                "agent_id": "*",
                "tool_name": "record_purchase_order",
                "compare_args": ["auction_id", "item_id"],
            },
            {
                "agent_id": seller_id,
                "tool_name": "record_seller_order",
                "compare_args": ["auction_id", "item_id"],
            },
        ],
        "env_assertions": [
            {
                "predicate": "bids_from_at_least_two_buyers",
                "args": {"auction_id": auction_id},
            },
            {
                "predicate": "winner_bid_was_public_bid",
                "args": {"auction_id": auction_id},
            },
            {
                "predicate": "seller_awarded_winning_bid",
                "args": {"auction_id": auction_id},
            },
            {
                "predicate": "winning_buyer_confirmed_award",
                "args": {"auction_id": auction_id},
            },
            {
                "predicate": "purchase_order_recorded",
                "args": {"auction_id": auction_id},
            },
            {
                "predicate": "seller_order_recorded",
                "args": {"auction_id": auction_id},
            },
            {
                "predicate": "auction_artifacts_consistent",
                "args": {"auction_id": auction_id},
            },
            {
                "predicate": "price_within_owned_bidding_constraints",
                "args": {"auction_id": auction_id},
            },
            {
                "predicate": "inventory_available_for_award",
                "args": {"auction_id": auction_id, "item_id": item_id},
            },
            {
                "predicate": "required_terms_consistent",
                "args": {"auction_id": auction_id},
            },
            {
                "predicate": "resource_backed_bidding_decision",
                "args": {"auction_id": auction_id},
            },
        ],
        "communicate_info": [],
        "nl_assertions": [],
    }
