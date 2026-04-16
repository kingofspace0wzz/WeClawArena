"""Mechanical GT assembler -- from TemplateShape, emit scenario.gt.json.

Spec Section 4.5 says GT is emitted mechanically by the generator, not
hand-labeled. Given a TemplateShape (the template's declared structure),
produce the GT bundle that downstream EvalRunner compares against. No LLM
required.
"""

from __future__ import annotations

from clawsocialarena.generator.template import TemplateShape


def assemble_gt_bundle(shape: TemplateShape) -> dict:
    """Return a dict matching scenario.gt.json schema (spec Section 4.5)."""
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
    }


def assemble_scenario_json(shape: TemplateShape) -> dict:
    """Return a dict matching scenario.json schema (spec Section 4.1)."""
    return {
        "scenario_id": shape.scenario_id,
        "category": shape.category.value,
        "task_family": shape.task_family.value,
        "agents": shape.agents,
        "initial_state": shape.initial_state,
        "max_turns": shape.max_turns,
        "opening_message": shape.opening_message,
    }
