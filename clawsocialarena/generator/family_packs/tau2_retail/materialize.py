"""Bundle materialization adapter for the tau2_retail family pack.

Converts the in-memory ``SharedAccountScenarioBundle`` produced by the
loader into the on-disk bundle layout the rest of the construction
pipeline (docker simulation, eval runner) expects.

Output layout (subset of the legacy bundle layout from
``clawsocialarena/generator/cli.py:220+``):

    <out_dir>/
        scenario.json
        scenario.gt.json
        docker-compose.yml
        personas/
            <agent_id>.system.md
            <agent_id>.tools.json
        mcp/
            <tool_name>.json           (one stub per declared tool)
        governance/
            manifest.json
        resources/
            users/<owner_id>/db/personal.sqlite
            household/<household_id>/orders.json

This is the Phase 3 follow-on for the family-pack design (spec C
section 7 migration plan). MCP tool wrappers and full database
materialization are stubbed; the bundle layout itself is complete.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from clawsocialarena.generator.compose_emitter import emit_compose_yaml
from clawsocialarena.generator.family_packs.tau2_retail.loaders.loader_shared_account import (
    SharedAccountLoader,
    SharedAccountScenarioBundle,
)
from clawsocialarena.generator.governance_emitter import (
    emit_governance_manifest_files,
    emit_governance_manifest_from_graph,
)
from clawsocialarena.generator.persona_emitter import emit_persona_files
from clawsocialarena.scenario.models import Scenario


_RETAIL_TOOLS = (
    "find_user_id_by_name_zip",
    "find_user_id_by_email",
    "get_user_details",
    "get_order_details",
    "list_my_orders",
    "get_product_details",
    "exchange_item",
    "modify_address",
    "cancel_pending_order",
    "place_order",
    "transfer_to_human_agents",
)


def materialize_shared_account_bundle(
    bundle: SharedAccountScenarioBundle,
    out_dir: Path | str,
    *,
    tau2_loader: SharedAccountLoader | None = None,
) -> Path:
    """Write the shared-account scenario bundle to disk.

    Returns the materialized ``out_dir`` path. Overwrites any existing
    bundle files; does not touch unrelated entries in ``out_dir``.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    scenario = bundle.scenario

    _write_scenario_json(scenario, out_path)
    _write_scenario_gt_json(bundle, out_path)
    _write_family_pack_context(scenario, out_path)
    _write_docker_compose(scenario, out_path)
    _write_personas(scenario, out_path)
    _write_mcp_stubs(out_path)
    _write_governance(scenario, out_path)
    _write_resources(
        bundle,
        out_path,
        tau2_loader=tau2_loader or SharedAccountLoader(),
    )

    return out_path


def _write_family_pack_context(scenario: Scenario, out_dir: Path) -> None:
    """Persist the household identity so the gateway can replay the same
    primary / secondary mapping the materializer used.

    Without this, every gateway boot would fall back to the loader's
    hard-coded defaults (alice / bob / HH-7), so HH-99 or HH-42 bundles
    would silently lose their household identity once Docker came up.
    """
    if not scenario.family_id:
        return
    graph = scenario.agent_graph
    if graph is None or not graph.nodes:
        return
    primary_node = next(
        (n for n in graph.nodes if n.role_label == "primary_account_holder"),
        graph.nodes[0],
    )
    secondary_node_ids = [
        n.owner_id for n in graph.nodes if n.role_label != "primary_account_holder"
    ]
    household_id = (
        scenario.initial_state.get("household_id")
        if isinstance(scenario.initial_state, dict)
        else None
    )
    context = {
        "household_id": household_id or "HH-UNKNOWN",
        "primary_owner_id": primary_node.owner_id,
        "secondary_owner_ids": secondary_node_ids,
    }
    (out_dir / "family_pack_context.json").write_text(
        json.dumps(context, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_scenario_json(scenario: Scenario, out_dir: Path) -> None:
    data = scenario.model_dump(mode="json", exclude_none=True)
    (out_dir / "scenario.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_scenario_gt_json(
    bundle: SharedAccountScenarioBundle,
    out_dir: Path,
) -> None:
    """Assemble scenario.gt.json from the bundle's auxiliary data.

    Schema follows the task-contract spec section 6 (terminal_predicate
    replaced by evaluation_criteria, other fields unchanged).
    """
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
            tool_name: {"schema": {"type": "object"}, "audit_class": "retail"}
            for tool_name in _RETAIL_TOOLS
        },
        "persona_manifest": {
            node.agent_id: {
                "profile_ref": f"family-pack://tau2_retail/{node.role_label}",
                "agent_id": node.agent_id,
            }
            for node in (scenario.agent_graph.nodes if scenario.agent_graph else [])
        },
        "construction_manifest": {
            "family_id": scenario.family_id,
            "source": "tau2_retail",
            "household_seed": "HH-7",
            "naturalization_mode": "deterministic_seed",
        },
        "construction_seed": bundle.governance_seed,
    }
    (out_dir / "scenario.gt.json").write_text(
        json.dumps(gt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_docker_compose(scenario: Scenario, out_dir: Path) -> None:
    # Family-pack bundles always carry a populated resources/ tree, a
    # family_id, and a sibling family_pack_context.json. The compose
    # mounts the resources tree, the scenario.json, and the context
    # file, and threads matching CLI flags into the gateway.
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
            node.agent_id: list(_RETAIL_TOOLS)
            for node in (scenario.agent_graph.nodes if scenario.agent_graph else [])
        },
    )
    for filename, contents in files.items():
        (personas_dir / filename).write_text(contents, encoding="utf-8")


def _write_mcp_stubs(out_dir: Path) -> None:
    """Write one MCP manifest stub per declared tool.

    Stubs only — actual tool implementations live in the MCP wrapper
    layer (next milestone). The stubs let the bundle pass structural
    validation; agents will not be able to call these tools until the
    wrapper layer lands.
    """
    mcp_dir = out_dir / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    for tool_name in _RETAIL_TOOLS:
        manifest = {
            "tool_name": tool_name,
            "audit_class": "retail",
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
    bundle: SharedAccountScenarioBundle,
    out_dir: Path,
    *,
    tau2_loader: SharedAccountLoader,
) -> None:
    """Materialize the per-user SQLite databases and household JSON.

    Slices the tau2 retail db.json into per-user views: each household
    member gets a small SQLite database carrying the orders, payment
    methods, and addresses that belong to their owner_id. Cross-member
    visibility is the privacy challenge the audit gateway must enforce.
    """
    resources_dir = out_dir / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    household_id = str(bundle.scenario.initial_state.get("household_id") or "HH-7")
    household_dir = resources_dir / "household" / household_id
    household_dir.mkdir(parents=True, exist_ok=True)

    db_root = tau2_loader._load_db()
    orders = _household_orders_for(db_root, household_id)
    (household_dir / "orders.json").write_text(
        json.dumps(orders, indent=2) + "\n", encoding="utf-8"
    )

    graph = bundle.scenario.agent_graph
    if graph is None:
        return
    for node in graph.nodes:
        user_db_dir = resources_dir / "users" / node.owner_id / "db"
        user_db_dir.mkdir(parents=True, exist_ok=True)
        sqlite_path = user_db_dir / "personal.sqlite"
        _emit_user_sqlite(sqlite_path, owner_id=node.owner_id, orders=orders)


def _household_orders_for(
    db_root: dict[str, Any], household_id: str
) -> list[dict[str, Any]]:
    """Pick a small representative set of tau2 orders for the household.

    The skeleton uses the first 3 orders from tau2 retail and tags
    them with the household_id. A future calibration pass will pick
    orders that match the user_scenario.instructions narrative
    (Yusuf Rossi exchange, etc.).
    """
    orders_dict = db_root.get("orders", {})
    sample_orders = []
    for index, (order_id, order) in enumerate(orders_dict.items()):
        if index >= 3:
            break
        order_copy = dict(order)
        order_copy["order_id"] = order_id
        order_copy["household_id"] = household_id
        sample_orders.append(order_copy)
    return sample_orders


def _emit_user_sqlite(
    sqlite_path: Path,
    *,
    owner_id: str,
    orders: list[dict[str, Any]],
) -> None:
    """Write a minimal SQLite database carrying the household orders.

    Schema is intentionally small: one ``orders`` table with order_id,
    household_id, status, payment_authorized_by, shipping_address.
    Future iterations will mirror the full tau2 schema for the per-
    user view; for the skeleton this is enough to back the env_assertions
    in evaluation_criteria.
    """
    if sqlite_path.exists():
        sqlite_path.unlink()
    conn = sqlite3.connect(sqlite_path)
    try:
        conn.execute(
            """
            CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                owner_visible TEXT NOT NULL,
                status TEXT NOT NULL,
                payment_authorized_by TEXT,
                shipping_address TEXT
            )
            """
        )
        for order in orders:
            address = dict(order.get("address") or {})
            # Stamp the household_id onto the seeded shipping address so
            # the shipping_address_is_household_owned predicate has a
            # plausible starting state. Without this, the seeded address
            # is the upstream tau2 address (street/city/state/zip only)
            # and the predicate fails out of the box even before any
            # attack tampering. The handler's modify_address path still
            # enforces address.household_id == context.household_id, so
            # foreign-address attacks remain blocked.
            address.setdefault("household_id", order.get("household_id"))
            conn.execute(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
                (
                    order.get("order_id"),
                    order.get("household_id"),
                    owner_id,
                    order.get("status", "pending"),
                    order.get("payment_authorized_by"),
                    json.dumps(address),
                ),
            )
        conn.commit()
    finally:
        conn.close()
