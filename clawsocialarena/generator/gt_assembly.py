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
"""

from __future__ import annotations

from clawsocialarena.generator.template import TemplateShape


def assemble_gt_bundle(shape: TemplateShape) -> dict:
    """Return a dict matching scenario.gt.json schema (spec §4.5, §4.6)."""
    # Canonical action stream: empty for now (LLM-assisted scenarios may populate later).
    canonical: list[dict] = []
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
        "attack_plan": None,
        # v2 additions (spec §4.6): filled mechanically from the template
        "mcp_tool_manifest": _assemble_mcp_manifest(shape),
        "persona_manifest": _assemble_persona_manifest(shape),
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
    return {name: dict(spec) for name, spec in shape.mcp_tool_manifest.items()}


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
