"""Bundle materialization adapter for the wildclaw_social family pack.

Per-agent SQLite carries the agent's private calendar plus a shared
meeting-coordination table. The director's DB additionally carries
the inbox / proposal queue so all message-flow tools have a single
place to read/write.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from clawsocialarena.generator.compose_emitter import emit_compose_yaml
from clawsocialarena.generator.family_packs.wildclaw_social.loader import (
    MeetingNegotiationBundle,
)
from clawsocialarena.generator.governance_emitter import (
    emit_governance_manifest_files,
    emit_governance_manifest_from_graph,
)
from clawsocialarena.generator.persona_emitter import emit_persona_files
from clawsocialarena.scenario.models import Scenario


_SOCIAL_TOOLS = (
    "send_email",
    "read_inbox",
    "check_availability",
    "get_meeting_status",
    "list_team_members",
    "propose_meeting_time",
    "confirm_attendance",
    "create_calendar_event",
)


def materialize_meeting_negotiation_bundle(
    bundle: MeetingNegotiationBundle,
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
    bundle: MeetingNegotiationBundle,
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
            tool_name: {"schema": {"type": "object"}, "audit_class": "social"}
            for tool_name in _SOCIAL_TOOLS
        },
        "persona_manifest": {
            node.agent_id: {
                "profile_ref": f"family-pack://wildclaw_social/{node.role_label}",
                "agent_id": node.agent_id,
            }
            for node in (scenario.agent_graph.nodes if scenario.agent_graph else [])
        },
        "construction_manifest": {
            "family_id": scenario.family_id,
            "source": "wildclaw_social",
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
    bundle: MeetingNegotiationBundle,
    out_dir: Path,
) -> None:
    if not scenario.family_id:
        return
    graph = scenario.agent_graph
    if graph is None or not graph.nodes:
        return
    organizer_node = next(
        (n for n in graph.nodes if n.role_label == "meeting_organizer"),
        graph.nodes[0],
    )
    participant_ids = [
        n.owner_id for n in graph.nodes if n.role_label != "meeting_organizer"
    ]
    context = {
        "meeting_id": str(scenario.initial_state.get("meeting_id", "MTG-7")),
        "organizer_owner_id": organizer_node.owner_id,
        "participant_owner_ids": participant_ids,
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
            node.agent_id: list(_SOCIAL_TOOLS)
            for node in (scenario.agent_graph.nodes if scenario.agent_graph else [])
        },
    )
    for filename, contents in files.items():
        (personas_dir / filename).write_text(contents, encoding="utf-8")


def _write_mcp_stubs(out_dir: Path) -> None:
    mcp_dir = out_dir / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    for tool_name in _SOCIAL_TOOLS:
        manifest = {
            "tool_name": tool_name,
            "audit_class": "social",
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
    bundle: MeetingNegotiationBundle,
    out_dir: Path,
) -> None:
    resources_dir = out_dir / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    graph = bundle.scenario.agent_graph
    if graph is None:
        return
    meeting_id = str(bundle.scenario.initial_state.get("meeting_id") or "MTG-7")
    for node in graph.nodes:
        owner_dir = resources_dir / "team" / node.owner_id / "db"
        owner_dir.mkdir(parents=True, exist_ok=True)
        sqlite_path = owner_dir / "personal.sqlite"
        availability = bundle.participant_availability.get(node.owner_id, [])
        _emit_team_sqlite(
            sqlite_path,
            owner=node.owner_id,
            meeting_id=meeting_id,
            availability=availability,
        )


def _emit_team_sqlite(
    sqlite_path: Path,
    *,
    owner: str,
    meeting_id: str,
    availability: list[dict[str, Any]],
) -> None:
    if sqlite_path.exists():
        sqlite_path.unlink()
    conn = sqlite3.connect(sqlite_path)
    try:
        conn.execute(
            """
            CREATE TABLE meetings (
                meeting_id TEXT PRIMARY KEY,
                proposed_time TEXT,
                event_created INTEGER NOT NULL DEFAULT 0,
                confirmations TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE availability (
                owner_id TEXT NOT NULL,
                day TEXT NOT NULL,
                start TEXT NOT NULL,
                end TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE inbox (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id TEXT NOT NULL,
                recipient_id TEXT NOT NULL,
                subject TEXT,
                body TEXT,
                read INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO meetings VALUES (?, NULL, 0, ?)",
            (meeting_id, json.dumps({})),
        )
        for slot in availability:
            conn.execute(
                "INSERT INTO availability VALUES (?, ?, ?, ?)",
                (owner, slot.get("day"), slot.get("start"), slot.get("end")),
            )
        conn.commit()
    finally:
        conn.close()
