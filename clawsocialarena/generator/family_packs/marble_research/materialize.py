"""Bundle materialization adapter for the marble_research family pack."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from clawsocialarena.generator.compose_emitter import emit_compose_yaml
from clawsocialarena.generator.family_packs.marble_research.loader import (
    ResearchCollaborationBundle,
)
from clawsocialarena.generator.governance_emitter import (
    emit_governance_manifest_files,
    emit_governance_manifest_from_graph,
)
from clawsocialarena.generator.persona_emitter import emit_persona_files
from clawsocialarena.scenario.models import Scenario


_RESEARCH_TOOLS = (
    "find_pi_by_lab",
    "get_pi_details",
    "list_my_unpublished_results",
    "get_proposal_status",
    "draft_proposal_section",
    "request_citation_approval",
    "grant_citation_approval",
    "finalize_proposal",
)


def materialize_research_collaboration_bundle(
    bundle: ResearchCollaborationBundle,
    out_dir: Path | str,
) -> Path:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    scenario = bundle.scenario
    _write_scenario_json(scenario, out_path)
    _write_scenario_gt_json(bundle, out_path)
    _write_shared_research_context(bundle, out_path)
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
    bundle: ResearchCollaborationBundle,
    out_dir: Path,
) -> None:
    scenario = bundle.scenario
    governance_manifest = emit_governance_manifest_from_graph(scenario.agent_graph)
    proposal_id = str(scenario.initial_state.get("proposal_id", "PROP-7"))
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
                rid: {"resource_id": rid, "owner_id": bundle.seed.seed_id}
                for rid in bundle.declared_resource_ids
            }
        },
        "attack_plan": None,
        "mcp_tool_manifest": {
            tool_name: {"schema": {"type": "object"}, "audit_class": "research"}
            for tool_name in _RESEARCH_TOOLS
        },
        "persona_manifest": {
            node.agent_id: {
                "profile_ref": f"family-pack://marble_research/{node.role_label}",
                "agent_id": node.agent_id,
            }
            for node in (scenario.agent_graph.nodes if scenario.agent_graph else [])
        },
        "construction_manifest": {
            "family_id": scenario.family_id,
            "source": "marble_research",
            "seed_id": bundle.seed.seed_id,
            "proposal_id": proposal_id,
            "naturalization_mode": "deterministic_seed",
        },
        "construction_seed": bundle.governance_seed,
    }
    (out_dir / "scenario.gt.json").write_text(
        json.dumps(gt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_shared_research_context(
    bundle: ResearchCollaborationBundle,
    out_dir: Path,
) -> None:
    """Write shared_research_context.json with topic intro and PI summaries.

    This file is mounted as a read-only shared resource in the MCP server
    so all agents can read the proposal background without needing to
    query individual PI databases.
    """
    scenario = bundle.scenario
    proposal_id = str(scenario.initial_state.get("proposal_id", "PROP-7"))
    proposal_topic_title = str(
        scenario.initial_state.get("proposal_topic_title", "Research Collaboration")
    )
    proposal_topic_intro = str(
        scenario.initial_state.get("research_context_summary", "")
    )
    pi_summaries = [
        {
            "owner_id": r.owner_id,
            "agent_id": r.agent_id,
            "lab": r.lab,
            "research_summary": r.research_summary,
        }
        for r in bundle.researchers
    ]
    context = {
        "proposal_id": proposal_id,
        "seed_id": bundle.seed.seed_id,
        "seed_name": bundle.seed.seed_name,
        "proposal_topic_title": proposal_topic_title,
        "proposal_topic_intro": proposal_topic_intro,
        "participating_pis": pi_summaries,
    }
    (out_dir / "shared_research_context.json").write_text(
        json.dumps(context, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_family_pack_context(
    scenario: Scenario,
    bundle: ResearchCollaborationBundle,
    out_dir: Path,
) -> None:
    if not scenario.family_id:
        return
    graph = scenario.agent_graph
    if graph is None or not graph.nodes:
        return
    convener_node = next(
        (n for n in graph.nodes if n.role_label == "convener_pi"),
        graph.nodes[0],
    )
    peer_ids = [n.owner_id for n in graph.nodes if n.role_label != "convener_pi"]
    proposal_id = str(scenario.initial_state.get("proposal_id", "PROP-7"))
    context = {
        "proposal_id": proposal_id,
        "seed_id": bundle.seed.seed_id,
        "convener_owner_id": convener_node.owner_id,
        "peer_owner_ids": peer_ids,
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
            node.agent_id: list(_RESEARCH_TOOLS)
            for node in (scenario.agent_graph.nodes if scenario.agent_graph else [])
        },
    )
    for filename, contents in files.items():
        (personas_dir / filename).write_text(contents, encoding="utf-8")


def _write_mcp_stubs(out_dir: Path) -> None:
    mcp_dir = out_dir / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    for tool_name in _RESEARCH_TOOLS:
        manifest = {
            "tool_name": tool_name,
            "audit_class": "research",
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
    bundle: ResearchCollaborationBundle,
    out_dir: Path,
) -> None:
    """Materialize per-PI SQLite databases with real MARBLE seed URs.

    Each PI has a per-owner SQLite with two tables:
    - proposals: an empty proposal slot (filled as the scenario unfolds)
    - unpublished_results: the PI's own unpublished results from seed data

    Per-PI URs are stable across tasks within the same seed: a PI appearing
    in multiple tasks carries the same unpublished_results rows in each.
    The proposal_id and proposal_topic do vary per task.
    """
    resources_dir = out_dir / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    scenario = bundle.scenario
    proposal_id = str(scenario.initial_state.get("proposal_id") or "PROP-7")
    for researcher in bundle.researchers:
        owner_dir = resources_dir / "pis" / researcher.owner_id / "db"
        owner_dir.mkdir(parents=True, exist_ok=True)
        sqlite_path = owner_dir / "personal.sqlite"
        _emit_pi_sqlite(
            sqlite_path,
            owner=researcher.owner_id,
            proposal_id=proposal_id,
            unpublished_results=list(researcher.unpublished_results),
        )


def _emit_pi_sqlite(
    sqlite_path: Path,
    *,
    owner: str,
    proposal_id: str,
    unpublished_results: list[dict],
) -> None:
    if sqlite_path.exists():
        sqlite_path.unlink()
    conn = sqlite3.connect(sqlite_path)
    try:
        conn.execute(
            """
            CREATE TABLE proposals (
                proposal_id TEXT PRIMARY KEY,
                sections TEXT NOT NULL,
                citations TEXT NOT NULL,
                approvals TEXT NOT NULL,
                finalized INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE unpublished_results (
                result_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                summary TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO proposals VALUES (?, ?, ?, ?, 0)",
            (
                proposal_id,
                json.dumps({}),
                json.dumps([]),
                json.dumps({}),
            ),
        )
        for ur in unpublished_results:
            conn.execute(
                "INSERT INTO unpublished_results VALUES (?, ?, ?)",
                (ur["result_id"], ur["owner_id"], ur["summary"]),
            )
        conn.commit()
    finally:
        conn.close()
