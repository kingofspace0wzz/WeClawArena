"""Shared types for the new predicate registry.

See ``docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md``
section 3 for the contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class EnvState:
    """Post-run environment snapshot exposed to predicate callables.

    The wrapper carries the final database state, filesystem snapshot,
    and message log. Predicates are pure functions over this state.

    Extended fields (added for tau2_retail multi-archetype predicates):

    ``outbound_messages``
        Ordered list of ``{ts, agent_id, content, ...}`` dicts produced by
        the orchestrator from the agent trajectory. Used by
        ``user_confirmation_recorded_before``.

    ``tool_dispatches``
        Ordered list of ``{caller_owner_id, tool_name, arguments,
        resource_path, observation, ...}`` dicts from the gateway audit
        layer. Used by ``spoke_request_not_read_cross_spoke`` and
        ``transfer_to_human_called_for_out_of_scope``.

    ``metadata``
        Archetype-specific runtime hints (e.g., ``hub_owner_id`` for
        hub_aggregator scenarios). Used by
        ``spoke_request_not_read_cross_spoke``.
    """

    db: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    files: Mapping[str, str] = field(default_factory=dict)
    messages: list[Mapping[str, Any]] = field(default_factory=list)
    outbound_messages: list[Mapping[str, Any]] = field(default_factory=list)
    tool_dispatches: list[Mapping[str, Any]] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PredicateResult:
    """Outcome of one predicate evaluation.

    Pass / fail with a reason string. Optional ``diagnostics`` carries
    structured context the QC report aggregator can surface.
    """

    passed: bool
    reason: str
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


PredicateFn = Callable[..., PredicateResult]
