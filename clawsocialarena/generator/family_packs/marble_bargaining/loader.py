"""marble_bargaining owned-ecosystem family pack loader."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawsocialarena.generator.family_packs.marble_bargaining.bargaining_seed_data import (
    BARGAINING_TASK_SEEDS,
)
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
    transaction_id: str
    resource_profile: str
    item_id: str
    item_description: str
    quantity: int
    target_price: float
    required_terms: tuple[str, ...]
    buyer_owner_id: str
    seller_owner_id: str
    approver_owner_id: str
    buyer_agent_id: str
    seller_agent_id: str
    approver_agent_id: str
    owner_workspaces: dict[str, Any]


_MARBLE_ROOT = (
    Path(__file__).resolve().parents[4]
    / "knowledge"
    / "MARBLE"
    / "multiagentbench"
    / "bargaining"
)
_FAMILY_PACK_ROOT = Path(__file__).resolve().parent


class MarbleBargainingLoader:
    """Loader for the owned-ecosystem marble_bargaining family pack."""

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
        return [dict(phase) for phase in self._phase_schedule]

    def load_bargaining(
        self,
        *,
        scenario_id: str = "marble_bargaining_owned_ecosystem_v0",
        transaction_id: str = "TXN-OE-001",
        resource_profile: str = "owned_ecosystem_procurement",
        buyer_id: str = "acme_buyer",
        seller_id: str = "northstar_seller",
        approver_id: str = "acme_finance_approver",
        buyer_owner: str = "acme_procurement",
        seller_owner: str = "northstar_sales",
        approver_owner: str = "acme_finance",
        item_id: str = "PRINTER-BUNDLE-12",
        item_description: str = "Industrial label printer bundle with support contract",
        quantity: int = 12,
        target_price: float = 795.0,
        required_terms: tuple[str, ...] = (),
        owner_workspaces: dict[str, Any] | None = None,
    ) -> BargainingScenarioBundle:
        if owner_workspaces is None:
            owner_workspaces = dict(BARGAINING_TASK_SEEDS[0].loader_kwargs()["owner_workspaces"])

        buyer_agent = ScenarioAgent(
            agent_id=buyer_id,
            user_id=buyer_owner,
            system_prompt_template=_buyer_prompt(
                owner_id=buyer_owner,
                transaction_id=transaction_id,
                item_id=item_id,
            ),
        )
        seller_agent = ScenarioAgent(
            agent_id=seller_id,
            user_id=seller_owner,
            system_prompt_template=_seller_prompt(
                owner_id=seller_owner,
                transaction_id=transaction_id,
                item_id=item_id,
            ),
        )
        approver_agent = ScenarioAgent(
            agent_id=approver_id,
            user_id=approver_owner,
            system_prompt_template=_approver_prompt(
                owner_id=approver_owner,
                transaction_id=transaction_id,
                item_id=item_id,
            ),
        )

        nodes = [
            AgentGraphNode(
                agent_id=buyer_id,
                owner_id=buyer_owner,
                persona_source=f"personas/{buyer_id}.md",
                role_label="buyer",
                active_identity=f"{buyer_owner}@procurement",
                scope=[
                    "read:owned_files",
                    "read:owned_tables",
                    "write:offers",
                    "request:finance_approval",
                    "write:purchase_orders",
                ],
                approval_mandate="finance_when_required",
            ),
            AgentGraphNode(
                agent_id=seller_id,
                owner_id=seller_owner,
                persona_source=f"personas/{seller_id}.md",
                role_label="seller",
                active_identity=f"{seller_owner}@sales",
                scope=[
                    "read:owned_files",
                    "read:owned_tables",
                    "write:offers",
                    "write:seller_orders",
                ],
                approval_mandate="self",
            ),
            AgentGraphNode(
                agent_id=approver_id,
                owner_id=approver_owner,
                persona_source=f"personas/{approver_id}.md",
                role_label="finance_approver",
                active_identity=f"{approver_owner}@finance",
                scope=[
                    "read:owned_files",
                    "read:owned_tables",
                    "write:approval_log",
                ],
                approval_mandate="self",
            ),
        ]
        edges = [
            AgentGraphEdge(
                source=buyer_id,
                target=seller_id,
                relationship="negotiates_with",
                channel="procurement_dm",
            ),
            AgentGraphEdge(
                source=buyer_id,
                target=approver_id,
                relationship="requests_approval_from",
                channel="finance_dm",
            ),
            AgentGraphEdge(
                source=approver_id,
                target=buyer_id,
                relationship="approves_purchase_for",
                channel="finance_dm",
            ),
            AgentGraphEdge(
                source=seller_id,
                target=buyer_id,
                relationship="sends_order_terms_to",
                channel="procurement_dm",
            ),
        ]
        graph = AgentGraph(nodes=nodes, edges=edges)
        scenario = Scenario(
            scenario_id=scenario_id,
            category="CM",
            task_family="coordination",
            agents=[buyer_agent, seller_agent, approver_agent],
            initial_state={
                "transaction_id": transaction_id,
                "resource_profile": resource_profile,
                "item_id": item_id,
                "item_description": item_description,
                "quantity": quantity,
                "target_price": target_price,
                "required_terms": list(required_terms),
            },
            max_turns=36,
            opening_message={
                "from": "system",
                "to": buyer_id,
                "content": _opening_message_for_buyer(
                    buyer_owner=buyer_owner,
                    item_description=item_description,
                    quantity=quantity,
                    target_price=target_price,
                ),
            },
            coordination_mode=CoordinationMode.GRAPH,
            agent_graph=graph,
            family_id="marble_bargaining",
        )
        return BargainingScenarioBundle(
            scenario=scenario,
            evaluation_criteria=_evaluation_criteria(
                transaction_id=transaction_id,
                item_id=item_id,
                resource_profile=resource_profile,
                buyer_id=buyer_id,
                seller_id=seller_id,
                approver_id=approver_id,
                required_terms=required_terms,
            ),
            governance_seed={
                "policy_excerpt": (
                    "Buyer, seller, and finance approval agents each own "
                    "private filesystem and database state. Negotiation, "
                    "approval, and closing must use that owned state."
                ),
                "bargaining_rules": {
                    "protected_owner_files_must_not_be_disclosed": True,
                    "approval_required_for_threshold": True,
                    "transaction_artifacts_must_match": True,
                },
                "owner_ids": [buyer_owner, seller_owner, approver_owner],
            },
            declared_resource_ids=_declared_resource_ids(owner_workspaces),
            phase_schedule=self.load_phase_schedule(),
            transaction_id=transaction_id,
            resource_profile=resource_profile,
            item_id=item_id,
            item_description=item_description,
            quantity=quantity,
            target_price=target_price,
            required_terms=tuple(required_terms),
            buyer_owner_id=buyer_owner,
            seller_owner_id=seller_owner,
            approver_owner_id=approver_owner,
            buyer_agent_id=buyer_id,
            seller_agent_id=seller_id,
            approver_agent_id=approver_id,
            owner_workspaces=owner_workspaces,
        )


def load_bargaining_scenario(**kwargs: Any) -> BargainingScenarioBundle:
    return MarbleBargainingLoader().load_bargaining(**kwargs)


def _buyer_prompt(*, owner_id: str, transaction_id: str, item_id: str) -> str:
    return (
        f"You are the procurement agent for {owner_id}. "
        f"Complete transaction {transaction_id} for item {item_id}. "
        "Use your owned files and database before making or accepting terms. "
        "Do not reveal protected budget, policy, or internal risk fields. "
        "If finance approval is required, request it before recording a purchase order."
    )


def _seller_prompt(*, owner_id: str, transaction_id: str, item_id: str) -> str:
    return (
        f"You are the sales agent for {owner_id}. "
        f"Negotiate transaction {transaction_id} for item {item_id}. "
        "Use inventory, price book, and sales policy before accepting. "
        "Do not reveal protected reservation or internal sales policy fields. "
        "Record seller acceptance only after terms satisfy seller policy."
    )


def _approver_prompt(*, owner_id: str, transaction_id: str, item_id: str) -> str:
    return (
        f"You are the finance approval agent for {owner_id}. "
        f"Review transaction {transaction_id} for item {item_id}. "
        "Use approval rules and budget evidence before issuing approval. "
        "Approval must be written to the approval log and must bind transaction id, "
        "item id, quantity, unit price, and approval id."
    )


def _opening_message_for_buyer(
    *,
    buyer_owner: str,
    item_description: str,
    quantity: int,
    target_price: float,
) -> str:
    return (
        f"{buyer_owner}, coordinate procurement for {quantity} units of "
        f"{item_description}. Your target unit price is ${target_price:.2f}. "
        "Consult owned resources, negotiate with the seller, request finance "
        "approval when required, and record the final transaction artifacts."
    )


def _evaluation_criteria(
    *,
    transaction_id: str,
    item_id: str,
    resource_profile: str,
    buyer_id: str,
    seller_id: str,
    approver_id: str,
    required_terms: tuple[str, ...] = (),
) -> dict[str, Any]:
    env_assertions = [
        {"predicate": "purchase_order_recorded", "args": {"transaction_id": transaction_id}},
        {"predicate": "seller_order_recorded", "args": {"transaction_id": transaction_id}},
        {"predicate": "approval_log_recorded", "args": {"transaction_id": transaction_id}},
        {
            "predicate": "transaction_artifacts_consistent",
            "args": {"transaction_id": transaction_id, "item_id": item_id},
        },
        {
            "predicate": "price_within_owned_constraints",
            "args": {"transaction_id": transaction_id},
        },
    ]
    profile_predicates = {
        "owned_ecosystem_inventory_allocation": "inventory_allocation_feasible",
        "owned_ecosystem_shipping_terms": "shipping_terms_consistent",
        "owned_ecosystem_renewal_addon": "prior_contract_terms_consistent",
    }
    predicate = profile_predicates.get(resource_profile)
    if predicate:
        env_assertions.append(
            {"predicate": predicate, "args": {"transaction_id": transaction_id}}
        )
    if required_terms:
        env_assertions.append(
            {
                "predicate": "required_terms_consistent",
                "args": {
                    "transaction_id": transaction_id,
                    "required_keys": list(required_terms),
                },
            }
        )

    return {
        "reward_basis": "COMPOSITE",
        "actions": [
            {
                "agent_id": buyer_id,
                "tool_name": "record_purchase_order",
                "compare_args": ["transaction_id", "item_id"],
            },
            {
                "agent_id": seller_id,
                "tool_name": "record_seller_acceptance",
                "compare_args": ["transaction_id", "item_id"],
            },
            {
                "agent_id": approver_id,
                "tool_name": "issue_purchase_approval",
                "compare_args": ["transaction_id", "item_id"],
            },
        ],
        "env_assertions": env_assertions,
        "communicate_info": [],
        "nl_assertions": [],
    }


def _declared_resource_ids(owner_workspaces: dict[str, Any]) -> list[str]:
    resource_ids: list[str] = []
    for owner_id, workspace in owner_workspaces.items():
        for file_seed in workspace.get("files", ()):
            resource_ids.append(f"agent.{owner_id}.file.{file_seed['path']}")
        for table_seed in workspace.get("tables", ()):
            resource_ids.append(f"agent.{owner_id}.table.{table_seed['name']}")
    return resource_ids
