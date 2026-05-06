"""Mechanical GT assembler -- from TemplateShape, emit scenario.gt.json.

Spec §4.5 says GT is emitted mechanically by the generator, not hand-labeled.
Given a TemplateShape (the template's declared structure), produce the GT
bundle that downstream EvalRunner compares against. No LLM required.

v2 (spec §4.6) adds two manifest fields. Both are filled from the template
when available; when the template omits them, assembly falls back to a
sensible default so every bundle always ships with a complete manifest:

- ``mcp_tool_manifest`` defaults to ``{}``. Legacy templates that do not
  declare tools pass through unchanged.
- ``persona_manifest`` defaults to one entry per scenario agent, keyed by
  agent_id, with ``profile_ref = asb://profiles/<agent_id>``. This keeps
  older templates valid while the new category x family templates in
  Phase E wire in explicit AgentSocialBench profile_refs.
- ``resource_manifest`` defaults to ``None`` and is copied when a template
  declares auditable filesystem or database resources.
"""

from __future__ import annotations

from copy import deepcopy

from clawsocialarena.generator.template import TemplateShape
from clawsocialarena.scenario.models import ResourceManifest


def assemble_gt_bundle(shape: TemplateShape) -> dict:
    """Return a dict matching scenario.gt.json schema (spec §4.5, §4.6)."""
    # Canonical action stream: threaded from the shape's ``injected_actions``
    # (Task D6). Attacker-injected outbound actions carry ``mentioned_items``
    # so MSWM replay updates peer beliefs.
    canonical: list[dict] = [dict(a) for a in shape.injected_actions]
    # Attribution DAG from planted disclosures
    nodes: list[dict] = []
    edges: list[dict] = []
    for d in shape.planted_disclosures:
        nid = f"{d['agent_id']}-{d.get('turn', 0)}"
        nodes.append({"id": nid, "label": d.get("label", "L0"), "agent_id": d["agent_id"]})
        if d.get("parent_action_id"):
            edges.append({"src": d["parent_action_id"], "dst": nid, "label": d.get("label", "L1")})

    return {
        "scenario_id": shape.scenario_id,
        "canonical_action_stream": canonical,
        "phase_schedule": shape.phase_schedule,
        "policies": shape.declared_policies,
        "attribution_dag": {"nodes": nodes, "edges": edges},
        "integrity_requirements": shape.integrity_requirements,
        "terminal_predicate": shape.terminal_predicate,
        "invariants": shape.invariants,
        "attack_plan": deepcopy(shape.attack_plan),
        # v2 additions (spec §4.6): filled mechanically from the template
        "mcp_tool_manifest": _assemble_mcp_manifest(shape),
        "persona_manifest": _assemble_persona_manifest(shape),
        "governance_manifest": _assemble_governance_manifest(shape),
        "resource_manifest": _assemble_resource_manifest(shape),
        "construction_manifest": _assemble_construction_manifest(shape),
    }


def assemble_scenario_json(shape: TemplateShape) -> dict:
    """Return a dict matching scenario.json schema (spec §4.1)."""
    return {
        "scenario_id": shape.scenario_id,
        "category": shape.category.value,
        "task_family": shape.task_family.value,
        "agents": shape.agents,
        "initial_state": shape.initial_state,
        "max_turns": shape.max_turns,
        "opening_message": shape.opening_message,
    }


def _assemble_mcp_manifest(shape: TemplateShape) -> dict:
    """Copy the template's MCP tool manifest as-is.

    Each entry is ``{schema: {...}, audit_class: ...}``. Empty when the
    template declares no scenario-specific tools.
    """
    manifest = {name: dict(spec) for name, spec in shape.mcp_tool_manifest.items()}
    for tool_name, spec in _assemble_resource_tool_manifest(shape).items():
        manifest.setdefault(tool_name, spec)
    return manifest


def _assemble_persona_manifest(shape: TemplateShape) -> dict:
    """Copy the template's persona manifest, or synthesise a default.

    When the template does not declare a persona manifest, assembly
    synthesises one entry per scenario agent:
    ``{agent_id: {"profile_ref": f"asb://profiles/{agent_id}", "agent_id": agent_id}}``.
    """
    if shape.persona_manifest:
        return {
            agent_id: dict(ref)
            for agent_id, ref in shape.persona_manifest.items()
        }
    return {
        agent["agent_id"]: {
            "profile_ref": f"asb://profiles/{agent['agent_id']}",
            "agent_id": agent["agent_id"],
        }
        for agent in shape.agents
    }


def _assemble_governance_manifest(shape: TemplateShape) -> dict | None:
    """Copy the template's governance manifest, or leave legacy shapes unset."""
    if not shape.governance_manifest:
        return None
    return deepcopy(shape.governance_manifest)


def _assemble_resource_manifest(shape: TemplateShape) -> dict | None:
    """Copy the template's resource manifest, or leave legacy shapes unset."""
    if not shape.resource_manifest:
        return None
    return deepcopy(shape.resource_manifest)


def _assemble_construction_manifest(shape: TemplateShape) -> dict | None:
    """Copy world-pack construction metadata when the instantiator provides it."""
    if not shape.construction_manifest:
        return None
    return deepcopy(shape.construction_manifest)


def _assemble_resource_tool_manifest(shape: TemplateShape) -> dict[str, dict]:
    """Derive MCP contracts for declared resource operations."""
    if not shape.resource_manifest:
        return {}
    resource_manifest = ResourceManifest.model_validate(shape.resource_manifest)
    operations = {
        operation
        for resource in resource_manifest.resources.values()
        for rule in resource.allowed_operations
        for operation in rule.operations
    }
    return {
        operation: {
            "schema": _resource_tool_schema(operation),
            "audit_class": "tool_call",
        }
        for operation in sorted(operations)
        if operation.startswith(("fs.", "db."))
    }


def _resource_tool_schema(operation: str) -> dict:
    properties: dict[str, dict] = {
        "resource_id": {"type": "string"},
        "identity_id": {"type": "string"},
        "scope_id": {"type": "string"},
    }
    if operation in {"fs.write"}:
        properties["content"] = {"type": "string"}
    if operation in {"db.query", "db.update", "db.delete"}:
        properties["where"] = {"type": "object"}
    if operation == "db.insert":
        properties["values"] = {"type": "object"}
    if operation == "db.update":
        properties["values"] = {"type": "object"}
    return {
        "type": "object",
        "properties": properties,
        "required": ["resource_id"],
        "additionalProperties": True,
    }
