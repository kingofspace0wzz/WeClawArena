"""Scenario template framework.

A Template describes the category x task-family structure for generating a
single scenario instance. Templates declare their shape; the generator
assembles scenario.json + scenario.gt.json from that shape deterministically
(for the MVP) or via an LLM-assisted instantiation layer (future).

Per spec Section 4.2, each category uses 2 task families. This module declares
the protocol; individual templates live under templates/.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class CategoryCode(StrEnum):
    CD = "CD"  # Cross-Domain
    MC = "MC"  # Mediated Communication
    CU = "CU"  # Cross-User A2A
    MG = "MG"  # Multi-Party Group
    HS = "HS"  # Hub-and-Spoke
    CM = "CM"  # Competitive
    AM = "AM"  # Affinity-Modulated


class TaskFamily(StrEnum):
    # v2 task families (spec §4.3). These are the four verifiable families
    # covered by the benchmark plus the two hard-stratum soft-halo families.
    SCHEDULING = "scheduling"
    CONSENSUS = "consensus"
    COALITION = "coalition"
    INFERENCE = "inference"
    CODE_REVIEW = "code_review"
    DOC_EDITING = "doc_editing"
    # v1 legacy values retained for stored bundles and older planning helpers.
    AGGREGATION = "aggregation"
    TRANSACTION = "transaction"
    DECISION = "decision"


class TemplateShape(BaseModel):
    """Declarative skeleton a template produces. The generator consumes this."""

    scenario_id: str
    category: CategoryCode
    task_family: TaskFamily
    agents: list[dict]         # [{agent_id, user_id, system_prompt_template}, ...]
    initial_state: dict
    max_turns: int
    opening_message: dict      # {"from", "to", "content"}
    phase_schedule: list[dict]  # [{"phase", "start_turn", "end_turn"}, ...]
    declared_policies: dict    # {"flat": [...], "phase_scoped": [...]}
    terminal_predicate: dict   # {"type", ...}
    invariants: dict           # {"privacy_must_not_cross": [...], ...}
    integrity_requirements: dict[str, int]
    # Planted provenance (used to construct GT attribution DAG)
    planted_disclosures: list[dict]  # [{"turn", "agent_id", "item", "parent_action_id"?, "label"}]
    # v2 additions (spec §4.6). Templates populate these for scenarios that
    # ship scenario-specific MCP tools and/or AgentSocialBench profile
    # bindings. Default empty so v1 templates keep working.
    mcp_tool_manifest: dict[str, dict[str, Any]] = Field(default_factory=dict)
    persona_manifest: dict[str, dict[str, Any]] = Field(default_factory=dict)
    governance_manifest: dict[str, Any] = Field(default_factory=dict)
    resource_manifest: dict[str, Any] = Field(default_factory=dict)
    resource_fixtures: dict[str, Any] = Field(default_factory=dict)
    construction_manifest: dict[str, Any] = Field(default_factory=dict)
    attack_plan: dict[str, Any] | None = None
    # Task D6: scripted attacker actions threaded into canonical_action_stream
    # by ``gt_assembly``. Each entry is an ActionRecord-shaped dict; the
    # critical payload key for MSWM updates is ``mentioned_items``.
    injected_actions: list[dict[str, Any]] = Field(default_factory=list)


@runtime_checkable
class Template(Protocol):
    category: CategoryCode
    task_family: TaskFamily

    def build(self, *, seed: int, scenario_id: str) -> TemplateShape:
        """Produce a TemplateShape for this (category, task_family) with a given seed."""
        ...
