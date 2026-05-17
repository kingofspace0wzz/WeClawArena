"""Bundle materialization adapter for the tau2_retail family pack.

Converts the in-memory ``SharedAccountScenarioBundle`` produced by the
loader into the on-disk bundle layout the rest of the construction
pipeline (docker simulation, eval runner) expects.

Output layout (subset of the v2.0 bundle layout):

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
            agents/<owner_id>/files/<path>.md
            agents/<owner_id>/db/personal.sqlite
            shared/<shared_id>/<shared_resource_id>.sqlite
        resources_initial/             (pristine snapshot for rerun replay)

This is the Phase 3 follow-on for the family-pack design (spec C
section 7 migration plan). MCP tool wrappers and full database
materialization are stubbed; the bundle layout itself is complete.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawsocialarena.generator.compose_emitter import emit_compose_yaml
from clawsocialarena.generator.family_packs.tau2_retail.loaders.loader_shared_account import (
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
    _write_family_pack_context(bundle, out_path)
    _write_docker_compose(scenario, out_path)
    _write_personas(scenario, out_path)
    _write_mcp_stubs(out_path)
    _write_governance(scenario, out_path)
    _write_resources(bundle, out_path)

    return out_path


def _write_family_pack_context(bundle: SharedAccountScenarioBundle, out_dir: Path) -> None:
    """Write family_pack_context.json from the bundle's context dict."""
    (out_dir / "family_pack_context.json").write_text(
        json.dumps(bundle.family_pack_context, indent=2, ensure_ascii=False) + "\n",
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


def _write_resources(bundle: SharedAccountScenarioBundle, out_dir: Path) -> None:
    """Materialize per-agent files and SQLite DBs plus shared resources.

    Layout:
        resources/agents/<owner_id>/files/<path>.md
        resources/agents/<owner_id>/db/personal.sqlite
        resources/shared/<shared_id>/<shared_resource_id>.sqlite
    Also writes a pristine snapshot under resources_initial/ for rerun replay.
    """
    import shutil

    resources_dir = out_dir / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)

    # Per-agent owned workspaces
    workspaces = bundle.owner_workspaces
    for owner_id, workspace in workspaces.items():
        files_dir = resources_dir / "agents" / owner_id / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        for file_dict in workspace.get("files", ()):
            (files_dir / file_dict["path"]).write_text(file_dict["content"], encoding="utf-8")

        db_dir = resources_dir / "agents" / owner_id / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        sqlite_path = db_dir / "personal.sqlite"
        _emit_owner_sqlite(sqlite_path, tables=workspace.get("tables", ()))

    # Shared cross-owner resources (only when present and a shared_account_id is set)
    shared_id = bundle.family_pack_context.get("shared_account_id")
    if shared_id and bundle.shared_resources:
        shared_dir = resources_dir / "shared" / shared_id
        shared_dir.mkdir(parents=True, exist_ok=True)
        for shared_res in bundle.shared_resources:
            sqlite_path = shared_dir / f"{shared_res['shared_resource_id']}.sqlite"
            _emit_owner_sqlite(
                sqlite_path,
                tables=({"name": "orders", "schema": shared_res["schema"], "rows": shared_res["rows"]},),
            )

    # Pristine snapshot for rerun replay
    resources_initial_dir = out_dir / "resources_initial"
    if resources_initial_dir.exists():
        shutil.rmtree(resources_initial_dir)
    shutil.copytree(resources_dir, resources_initial_dir)


def _emit_owner_sqlite(sqlite_path: Path, *, tables: tuple) -> None:
    """Create a SQLite database with the given tables and rows.

    Each table is a dict with keys ``name``, ``schema`` (a CREATE TABLE statement),
    and ``rows`` (a tuple of dicts keyed by column name).
    """
    import sqlite3

    if sqlite_path.exists():
        sqlite_path.unlink()
    conn = sqlite3.connect(sqlite_path)
    try:
        for table in tables:
            conn.execute(table["schema"])
            if not table.get("rows"):
                continue
            sample_row = table["rows"][0]
            columns = list(sample_row.keys())
            placeholders = ", ".join(["?"] * len(columns))
            insert_sql = (
                f"INSERT INTO {table['name']} ({', '.join(columns)}) VALUES ({placeholders})"
            )
            for row in table["rows"]:
                conn.execute(insert_sql, [row.get(c) for c in columns])
        conn.commit()
    finally:
        conn.close()
