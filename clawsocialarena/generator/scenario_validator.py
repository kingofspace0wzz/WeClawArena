"""Scenario validator for the topology-refactored construction pipeline.

Enforces the shape constraints declared in
docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md
section 4 against a Scenario's agent_graph and coordination_mode.

Validation runs at construction time, before any bundle materialization,
so structural defects (duplicate persona-to-agent, missing persona path,
dangling edges, mode-shape mismatches) are caught before a batch ships.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from clawsocialarena.generator.coordination_modes import (
    ShapeViolation,
    validate_mode_shape,
)
from clawsocialarena.scenario.models import (
    AgentGraph,
    CoordinationMode,
    Scenario,
)


@dataclass(frozen=True)
class ValidationError:
    """One structural failure detected on a Scenario."""

    rule: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of running the validator on one scenario."""

    scenario_id: str
    errors: tuple[ValidationError, ...]
    warnings: tuple[ValidationError, ...]

    @property
    def passed(self) -> bool:
        return not self.errors


def validate_scenario(
    scenario: Scenario,
    *,
    bundle_root: Path | str | None = None,
    channel_manifest: Iterable[str] | None = None,
    scope_vocabulary: Iterable[str] | None = None,
    allow_shared_ownership: bool = False,
) -> ValidationResult:
    """Run all topology validation rules against the scenario.

    A scenario without an agent_graph passes vacuously (legacy template
    path remains valid until family-pack loaders replace it). A scenario
    that declares an agent_graph but no coordination_mode (or vice
    versa) is an error.

    Parameters used by the optional rules:
    - bundle_root: when set, rule 'persona_source_exists' resolves
      persona_source paths against this root.
    - channel_manifest: when set, rule 'edge_channel_registered' checks
      that each edge.channel is registered in the compose template.
    - scope_vocabulary: when set, rule 'scope_vocabulary' checks each
      node.scope item against the canonical vocabulary.
    - allow_shared_ownership: when True, rule 'owner_id_unique' is
      skipped (some family modes legitimately have multiple agents
      sharing an owner; for example, a primary holder running two
      automation assistants).
    """

    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    graph = scenario.agent_graph
    mode = scenario.coordination_mode

    # Both fields must be present together, or both absent.
    if graph is None and mode is None:
        return ValidationResult(
            scenario_id=scenario.scenario_id,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )
    if graph is None or mode is None:
        errors.append(
            ValidationError(
                rule="topology_fields_paired",
                message=(
                    "coordination_mode and agent_graph must be set together; "
                    f"coordination_mode={mode!r}, "
                    f"agent_graph={'set' if graph else 'None'}"
                ),
            )
        )
        return ValidationResult(
            scenario_id=scenario.scenario_id,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    # Shape rules covered by the mode-shape helper.
    for violation in validate_mode_shape(mode, graph):
        errors.append(
            ValidationError(
                rule=f"mode_shape:{violation.kind}",
                message=violation.message,
            )
        )

    # Node-level rules.
    errors.extend(_validate_unique_agent_ids(graph))
    if not allow_shared_ownership:
        errors.extend(_validate_unique_owner_ids(graph))
    if bundle_root is not None:
        errors.extend(_validate_persona_sources(graph, Path(bundle_root)))
    if scope_vocabulary is not None:
        errors.extend(_validate_scope_vocabulary(graph, set(scope_vocabulary)))

    # Edge-level rules.
    errors.extend(_validate_edge_endpoints(graph))
    if channel_manifest is not None:
        errors.extend(_validate_edge_channels(graph, set(channel_manifest)))

    return ValidationResult(
        scenario_id=scenario.scenario_id,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _validate_unique_agent_ids(graph: AgentGraph) -> list[ValidationError]:
    seen: dict[str, int] = {}
    for node in graph.nodes:
        seen[node.agent_id] = seen.get(node.agent_id, 0) + 1
    duplicates = [aid for aid, count in seen.items() if count > 1]
    if not duplicates:
        return []
    return [
        ValidationError(
            rule="agent_id_unique",
            message=(
                "agent_graph contains duplicate agent_id values: "
                f"{sorted(duplicates)}"
            ),
        )
    ]


def _validate_unique_owner_ids(graph: AgentGraph) -> list[ValidationError]:
    """Catches the persona-aliasing defect from batch 0074.

    When two graph nodes share an owner_id (the human principal), they
    represent the same person speaking through two different agents,
    which weakens identity-boundary realism. This rule rejects such
    shapes unless the caller passes allow_shared_ownership=True.
    """
    seen: dict[str, list[str]] = {}
    for node in graph.nodes:
        seen.setdefault(node.owner_id, []).append(node.agent_id)
    duplicates = {oid: agents for oid, agents in seen.items() if len(agents) > 1}
    if not duplicates:
        return []
    return [
        ValidationError(
            rule="owner_id_unique",
            message=(
                "agent_graph nodes share owner_id; this is the persona-"
                f"aliasing defect from batch 0074: {dict(duplicates)}"
            ),
        )
    ]


def _validate_persona_sources(
    graph: AgentGraph,
    bundle_root: Path,
) -> list[ValidationError]:
    missing: list[str] = []
    for node in graph.nodes:
        path = bundle_root / node.persona_source
        if not path.is_file():
            missing.append(f"{node.agent_id}={node.persona_source}")
    if not missing:
        return []
    return [
        ValidationError(
            rule="persona_source_exists",
            message=f"persona_source files missing under {bundle_root}: {missing}",
        )
    ]


def _validate_scope_vocabulary(
    graph: AgentGraph,
    vocabulary: set[str],
) -> list[ValidationError]:
    unknown: list[str] = []
    for node in graph.nodes:
        for scope_item in node.scope:
            if scope_item not in vocabulary:
                unknown.append(f"{node.agent_id}:{scope_item}")
    if not unknown:
        return []
    return [
        ValidationError(
            rule="scope_vocabulary",
            message=(
                "agent_graph nodes use scope strings outside the governance "
                f"manifest vocabulary: {unknown}"
            ),
        )
    ]


def _validate_edge_endpoints(graph: AgentGraph) -> list[ValidationError]:
    valid_ids = {node.agent_id for node in graph.nodes}
    dangling: list[str] = []
    for index, edge in enumerate(graph.edges):
        if edge.source not in valid_ids:
            dangling.append(f"edges[{index}].source={edge.source!r}")
        if edge.target not in valid_ids:
            dangling.append(f"edges[{index}].target={edge.target!r}")
    if not dangling:
        return []
    return [
        ValidationError(
            rule="edge_endpoints",
            message=f"agent_graph contains dangling edge endpoints: {dangling}",
        )
    ]


def _validate_edge_channels(
    graph: AgentGraph,
    manifest: set[str],
) -> list[ValidationError]:
    unknown: list[str] = []
    for index, edge in enumerate(graph.edges):
        if edge.channel not in manifest:
            unknown.append(f"edges[{index}].channel={edge.channel!r}")
    if not unknown:
        return []
    return [
        ValidationError(
            rule="edge_channel_registered",
            message=(
                "agent_graph edges reference channels not in the compose "
                f"channel manifest: {unknown}"
            ),
        )
    ]
