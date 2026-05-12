"""Bundle materialization adapter for the marble_bargaining family pack.

Per-agent SQLite carries the agent's private constraint (budget ceiling
for the buyer, reservation price for the seller) plus a shared offers
table that tracks the negotiation history. Acceptance writes a final
agreed-price row.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from clawsocialarena.generator.compose_emitter import emit_compose_yaml
from clawsocialarena.generator.family_packs.marble_bargaining.loader import (
    BargainingScenarioBundle,
)
from clawsocialarena.generator.governance_emitter import (
    emit_governance_manifest_files,
    emit_governance_manifest_from_graph,
)
from clawsocialarena.generator.persona_emitter import emit_persona_files
from clawsocialarena.scenario.models import Scenario


_BARGAINING_TOOLS = (
    "get_market_reference",
    "get_negotiation_status",
    "offer_price",
    "counter_offer",
    "accept_offer",
    "reveal_constraint",
)


def materialize_bargaining_bundle(
    bundle: BargainingScenarioBundle,
    out_dir: Path | str,
) -> Path:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    scenario = bundle.scenario
    _write_scenario_json(scenario, out_path)
    _write_scenario_gt_json(bundle, out_path)
    _write_family_pack_context(scenario, bundle, out_path)
    _write_docker_compose(scenario, out_path)
    _write_personas(scenario, out_path)
    _write_mcp_stubs(out_path)
    _write_governance(scenario, out_path)
    _write_resources(bundle, out_path)
    return out_path


def _write_scenario_json(scenario: Scenario, out_dir: Path) -> None:
    data = scenario.model_dump(mode="json", exclude_none=True)
    (out_dir / "scenario.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_scenario_gt_json(
    bundle: BargainingScenarioBundle,
    out_dir: Path,
) -> None:
    scenario = bundle.scenario
    governance_manifest = emit_governance_manifest_from_graph(scenario.agent_graph)
    gt: dict[str, Any] = {
        "scenario_id": scenario.scenario_id,
        "canonical_action_stream": [],
        "phase_schedule": bundle.phase_schedule,
        "policies": {"flat": [], "phase_scoped": []},
        "attribution_dag": {"nodes": [], "edges": []},
        "integrity_requirements": {
            "outbound_message": 2,
            "tool_call": 2,
            "tool_observation_return": 2,
            "memory_write": 2,
            "summary_write": 2,
            "policy_decision": 2,
        },
        "evaluation_criteria": bundle.evaluation_criteria,
        "invariants": {
            "privacy_must_not_cross": [],
            "security_must_not_happen": [],
            "governance_must_not_happen": [],
        },
        "governance_manifest": governance_manifest,
        "resource_manifest": {
            "resources": {
                rid: {"resource_id": rid, "owner_id": "alice"}
                for rid in bundle.declared_resource_ids
            }
        },
        "attack_plan": None,
        "mcp_tool_manifest": {
            tool_name: {"schema": {"type": "object"}, "audit_class": "bargaining"}
            for tool_name in _BARGAINING_TOOLS
        },
        "persona_manifest": {
            node.agent_id: {
                "profile_ref": f"family-pack://marble_bargaining/{node.role_label}",
                "agent_id": node.agent_id,
            }
            for node in (scenario.agent_graph.nodes if scenario.agent_graph else [])
        },
        "construction_manifest": {
            "family_id": scenario.family_id,
            "source": "marble_bargaining",
            "naturalization_mode": "deterministic_seed",
        },
        "construction_seed": bundle.governance_seed,
    }
    (out_dir / "scenario.gt.json").write_text(
        json.dumps(gt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_family_pack_context(
    scenario: Scenario,
    bundle: BargainingScenarioBundle,
    out_dir: Path,
) -> None:
    if not scenario.family_id:
        return
    graph = scenario.agent_graph
    if graph is None or not graph.nodes:
        return
    buyer_node = next((n for n in graph.nodes if n.role_label == "buyer"), graph.nodes[0])
    seller_node = next(
        (n for n in graph.nodes if n.role_label == "seller"), graph.nodes[-1]
    )
    context = {
        "item_id": str(scenario.initial_state.get("item_id", "ITEM-7")),
        "buyer_owner_id": buyer_node.owner_id,
        "seller_owner_id": seller_node.owner_id,
        "buyer_budget_ceiling": bundle.buyer_budget_ceiling,
        "seller_reservation": bundle.seller_reservation,
        "market_reference_price": bundle.market_reference_price,
    }
    (out_dir / "family_pack_context.json").write_text(
        json.dumps(context, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_docker_compose(scenario: Scenario, out_dir: Path) -> None:
    yaml_text = emit_compose_yaml(
        scenario,
        include_resources=True,
        family_pack_context_path="./family_pack_context.json"
        if scenario.family_id
        else None,
    )
    (out_dir / "docker-compose.yml").write_text(yaml_text, encoding="utf-8")


def _write_personas(scenario: Scenario, out_dir: Path) -> None:
    personas_dir = out_dir / "personas"
    personas_dir.mkdir(parents=True, exist_ok=True)
    files = emit_persona_files(
        scenario,
        tool_allowlist_by_agent={
            node.agent_id: list(_BARGAINING_TOOLS)
            for node in (scenario.agent_graph.nodes if scenario.agent_graph else [])
        },
    )
    for filename, contents in files.items():
        (personas_dir / filename).write_text(contents, encoding="utf-8")


def _write_mcp_stubs(out_dir: Path) -> None:
    mcp_dir = out_dir / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    for tool_name in _BARGAINING_TOOLS:
        manifest = {
            "tool_name": tool_name,
            "audit_class": "bargaining",
            "status": "stub",
            "implementation": "pending_mcp_wrapper",
        }
        (mcp_dir / f"{tool_name}.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )


def _write_governance(scenario: Scenario, out_dir: Path) -> None:
    manifest = emit_governance_manifest_from_graph(scenario.agent_graph)
    files = emit_governance_manifest_files(manifest)
    if not files:
        return
    governance_dir = out_dir / "governance"
    governance_dir.mkdir(parents=True, exist_ok=True)
    for filename, contents in files.items():
        (governance_dir / filename).write_text(contents, encoding="utf-8")


def _write_resources(
    bundle: BargainingScenarioBundle,
    out_dir: Path,
) -> None:
    resources_dir = out_dir / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    graph = bundle.scenario.agent_graph
    if graph is None:
        return
    item_id = str(bundle.scenario.initial_state.get("item_id") or "ITEM-7")
    buyer_owner = next(
        (n.owner_id for n in graph.nodes if n.role_label == "buyer"), "alice"
    )
    seller_owner = next(
        (n.owner_id for n in graph.nodes if n.role_label == "seller"), "bob"
    )
    for node in graph.nodes:
        owner_dir = resources_dir / "agents" / node.owner_id / "db"
        owner_dir.mkdir(parents=True, exist_ok=True)
        sqlite_path = owner_dir / "personal.sqlite"
        if node.owner_id == buyer_owner:
            private_budget = bundle.buyer_budget_ceiling
            private_reservation = None
        elif node.owner_id == seller_owner:
            private_budget = None
            private_reservation = bundle.seller_reservation
        else:
            private_budget = None
            private_reservation = None
        _emit_bargaining_sqlite(
            sqlite_path,
            owner=node.owner_id,
            item_id=item_id,
            market_reference_price=bundle.market_reference_price,
            private_budget=private_budget,
            private_reservation=private_reservation,
        )


def _emit_bargaining_sqlite(
    sqlite_path: Path,
    *,
    owner: str,
    item_id: str,
    market_reference_price: float,
    private_budget: float | None,
    private_reservation: float | None,
) -> None:
    if sqlite_path.exists():
        sqlite_path.unlink()
    conn = sqlite3.connect(sqlite_path)
    try:
        conn.execute(
            """
            CREATE TABLE items (
                item_id TEXT PRIMARY KEY,
                market_reference_price REAL NOT NULL,
                agreement TEXT,
                offers TEXT NOT NULL,
                revealed_constraints TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE private_constraints (
                owner_id TEXT PRIMARY KEY,
                budget_ceiling REAL,
                reservation_price REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO items VALUES (?, ?, ?, ?, ?)",
            (
                item_id,
                market_reference_price,
                None,
                json.dumps([]),
                json.dumps([]),
            ),
        )
        conn.execute(
            "INSERT INTO private_constraints VALUES (?, ?, ?)",
            (owner, private_budget, private_reservation),
        )
        conn.commit()
    finally:
        conn.close()
