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
    """

    db: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    files: Mapping[str, str] = field(default_factory=dict)
    messages: list[Mapping[str, Any]] = field(default_factory=list)


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
