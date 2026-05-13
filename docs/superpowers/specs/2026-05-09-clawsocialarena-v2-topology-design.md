# ClawSocialArena v2 Topology Design

**Status:** Current canonical topology and scenario-composition reference as of 2026-05-09.

**Read with:** `AGENTS.md`, `AGENTS.local.md`, `CLAUDE.md`, `agents/codex.md`, `docs/project_status.md`, `docs/DOCUMENTATION_INDEX.md`, `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md`, `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md`, `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md`, and `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md`.

This document defines the topology layer that controls how scenarios are composed: how many agents, who talks to whom, and what relationships hold between them. It replaces the per-category Python templates (`templates/cd_*.py`, `templates/hs_coalition.py`, `templates/mg_coalition.py`, and similar) with a config-driven model adopted from MARBLE [1]. Task-contract design (evaluation_criteria, predicate dispatch) lives in `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md`. Per-family content (fixtures, governance manifests, attack payloads) lives in `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md`.

## 1. Motivation

Construction batch 0074 surfaced two structural defects that are not bugs in any single template but properties of the per-category template approach itself. The HS and MG coalition templates duplicated the same persona across multiple agents with the same owner identity, weakening identity-boundary realism for `hs-coalition-stress-task-01314-*` and `mg-coalition-stress-task-01305-*`. The MC, CD, and CU rows carried personal resources unrelated to the task domain because resource selection in the legacy world-pack instantiation path was keyed off category labels rather than the actual scenario shape. Each category had its own way to break.

Adding ad-hoc guards inside each template would patch instances. The deeper repair is to move topology from Python templates into declarative config, validate the config against shape constraints, and have the emitters consume the config. This eliminates the class of bug rather than fixing instances.

## 2. Coordination Modes

The four coordination modes are adopted from `marble/engine/engine.py:200-573` as a static topology declaration only. We do not adopt MARBLE's runtime coordination loop; the ClawSocialArena audit gateway remains the runtime coordinator.

| Mode | Shape | Maps to current categories |
|---|---|---|
| `chain` | Sequential delegation: agent_1 -> agent_2 -> ... -> agent_n | Mediated Communication (when the relay is sequential) |
| `tree` | Hierarchical with one root and depth-2+ children | Hub-and-Spoke (multi-tier) |
| `graph` | Peer pairwise relationships, no fixed root | Multi-Party Group, Cross-User agent-to-agent |
| `star` | Single hub with leaf participants | Hub-and-Spoke (single-tier), Mediated Communication (when mediation is hub-shaped) |

The category-to-mode mapping is many-to-many. A category may use different modes across families, and the family-pack spec specifies which mode each (category, family) cell uses.

## 3. Agent Graph Schema

Each scenario declares an `agent_graph` field in `scenario.json`. The graph is a typed structure with nodes and edges.

```json
{
  "coordination_mode": "graph",
  "agent_graph": {
    "nodes": [
      {
        "agent_id": "alice_assistant",
        "owner_id": "alice",
        "persona_source": "personas/alice.system.md",
        "role_label": "primary_account_holder",
        "active_identity": "alice@household",
        "scope": ["read:household_orders", "write:household_orders"],
        "approval_mandate": "self"
      },
      {
        "agent_id": "bob_assistant",
        "owner_id": "bob",
        "persona_source": "personas/bob.system.md",
        "role_label": "secondary_account_holder",
        "active_identity": "bob@household",
        "scope": ["read:household_orders"],
        "approval_mandate": "primary_holder_required"
      }
    ],
    "edges": [
      {
        "source": "alice_assistant",
        "target": "bob_assistant",
        "relationship": "shares_account_with",
        "channel": "household_dm"
      }
    ]
  }
}
```

Node fields. `agent_id` is unique within the scenario. `owner_id` names the human principal. `persona_source` is a path to the persona prompt inside the bundle. `role_label` is human-readable. `active_identity` is the gateway-recognized identity string used in governance scoring. `scope` is the list of permitted operations against gateway-mediated tools. `approval_mandate` declares the governance state for actions originating from this agent.

Edge fields. `source` and `target` are valid `agent_id` values. `relationship` is a typed enum: `shares_account_with`, `reports_to`, `collaborates_with`, `negotiates_against`, `mediates_for`, `delegates_to`, `peer_of`. `channel` names the gateway-mediated channel the edge corresponds to.

The MARBLE relationship triple format `[agent1, agent2, relationship_label]` corresponds directly to `(edges[i].source, edges[i].target, edges[i].relationship)`.

## 4. Validation Rules

The scenario validator enforces shape constraints on `agent_graph` at construction time. Failures block the scenario from entering a batch bundle.

| Rule | Failure mode prevented |
|---|---|
| `node.agent_id` unique within the scenario | Two nodes with the same agent_id |
| `node.owner_id` is unique unless `coordination_mode` allows shared ownership | Duplicate persona-to-agent (the Camila aliasing seen in batch 0074) |
| `node.persona_source` resolves to a file in the bundle | Missing persona prompts |
| `node.scope` items use the canonical scope vocabulary defined in the governance manifest | Unrecognized scope strings |
| `edge.source` and `edge.target` reference valid `agent_id` values | Dangling edges |
| `edge.channel` exists in the gateway channel manifest | Channel mismatch between graph and compose |
| `coordination_mode == "chain"` requires the edges to form a single path | Mode-shape mismatch |
| `coordination_mode == "tree"` requires a single root and acyclic edges | Mode-shape mismatch |
| `coordination_mode == "star"` requires exactly one hub and all other nodes connect only to the hub | Mode-shape mismatch |
| `coordination_mode == "graph"` allows any connected graph but warns on disconnected components | Disconnected agents |

Validation runs in the new `clawsocialarena/generator/scenario_validator.py` module, invoked by `scripts/generate_benchmark_scaffold.py` and the family-pack loader before any bundle materialization.

## 5. Construction Pipeline Changes

The construction flow under the new model.

```text
family-pack loader
  -> emits coordination_mode + agent_graph + family_id + family_inputs
scenario_validator
  -> blocks invalid graphs
scenario_world_builder
  -> resolves persona_source for each node
  -> selects task-relevant resources via family_id, not category_label
governance_emitter
  -> reads node.scope, node.approval_mandate, edge.relationship
  -> emits governance manifest
compose_emitter
  -> reads agent_graph.nodes
  -> emits one OpenClaw container per node, plus the gateway container
mcp_emitter
  -> emits per-agent MCP manifests with scope-restricted tool surfaces
persona_emitter
  -> emits per-agent persona files including role_label and active_identity
```

The emitters become thinner because the agent count, channel topology, and persona-to-agent mapping are read from one place (`agent_graph`) rather than reconstructed from category-specific Python in each template module.

## 6. Scenario-World Resource Selection

Resource selection (filesystem files, personal-database rows) is rekeyed from category to family. Each family-pack entry declares which resource categories are task-relevant. The scenario-world builder queries the family entry rather than the scenario's category label, then writes only the selected resources into the bundle-local `scenario_world`.

```python
# Old (broken in batch 0074): keyed off category, no domain check
resources = select_resources(category=scenario.category, harm_axis=scenario.harm_axis)

# New: keyed off family, with declared resource categories
resources = select_resources(
    family_id=scenario.family_id,
    resource_categories=family_pack[scenario.family_id].resource_categories,
    harm_axis=scenario.harm_axis,
)
```

This removes the decoupled-resources defect (MC-inference rows about PR review carrying custody / health notes) by construction. The family-pack spec lists the resource categories per family.

## 7. Migration

Files retired:

- `clawsocialarena/generator/templates/cd_*.py` (all CD templates)
- `clawsocialarena/generator/templates/hs_coalition.py`
- `clawsocialarena/generator/templates/mg_coalition.py`
- `clawsocialarena/generator/templates/mc_*.py`
- `clawsocialarena/generator/templates/cu_*.py`
- Other category-specific templates that produce home-grown families

Files refactored:

- `clawsocialarena/generator/world_pack_instantiation.py` is retired or kept only as a compatibility wrapper around the scenario-world builder
- `clawsocialarena/generator/scenario_world_builder.py` consumes `family_id` and family resource declarations instead of category-specific paths
- `clawsocialarena/generator/compose_emitter.py` consumes `agent_graph.nodes`
- `clawsocialarena/generator/governance_emitter.py` consumes `agent_graph` for owner / identity / scope fields
- `clawsocialarena/generator/persona_emitter.py` consumes `agent_graph.nodes[].persona_source`

Files added:

- `clawsocialarena/generator/scenario_validator.py` (new)
- `clawsocialarena/generator/coordination_modes.py` (mode-shape validation helpers)
- `clawsocialarena/generator/scenario_world_builder.py` (bundle-local persona, filesystem, database, and governance fixture assembly)

Files unchanged:

- `clawsocialarena/simulation/*` (gateway, docker runner)
- `clawsocialarena/eval/*` (eval pipeline; task-contract changes live in the task-contract spec)
- `clawsocialarena/saf/*` (SAF scoring)
- `clawsocialarena/generator/attack_injection.py` (attack-injection schema; per-family payloads live in the family-pack spec)

## 8. Backward Compatibility

Older batch directories (batch-0061 through batch-0074) remain on the previous template-driven format. They are diagnostic only per `docs/DOCUMENTATION_INDEX.md`; no migration is needed.

The `scenario.json` schema gains two new top-level fields: `coordination_mode` and `agent_graph`. The category field is retained for the hybrid category model described in the family-pack spec. The schema is forward-compatible: bundles that lack the new fields fail validation rather than silently using legacy paths.

## 9. Open Questions

- Whether to support nested agent_graphs (an agent that delegates to a subgraph). Deferred. The current model assumes a flat graph; if a delegation pattern requires nesting, the family-pack spec will flag it.
- Whether `edge.channel` should be a typed enum or a free-form string. Current proposal: free-form string that must match a channel registered in the compose template; the gateway channel manifest validates the binding.
- How the named audit-bypass challenge cases (5 of the 680 pilot variants) declare graphs that bypass the standard scope validation. Likely an explicit `validation_overrides` field with a written justification, audited at gate time.

## Sources

[1] [MARBLE: Multi-agent coordination Bench](https://arxiv.org/abs/2503.13499). The static topology data structure (AgentGraph, relationship triples, the four mode labels) is borrowed; the runtime coordination loop is not.
