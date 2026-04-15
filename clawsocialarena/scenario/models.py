from typing import Any

from pydantic import BaseModel, Field


class ScenarioAgent(BaseModel):
    agent_id: str
    user_id: str
    system_prompt_template: str


class Scenario(BaseModel):
    scenario_id: str
    category: str
    task_family: str
    agents: list[ScenarioAgent]
    initial_state: dict[str, Any]
    max_turns: int
    opening_message: dict[str, Any]


class GTBundle(BaseModel):
    scenario_id: str
    canonical_action_stream: list[dict[str, Any]] = Field(default_factory=list)
    phase_schedule: list[dict[str, Any]] = Field(default_factory=list)
    policies: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    attribution_dag: dict[str, Any] = Field(default_factory=dict)
    integrity_requirements: dict[str, int] = Field(default_factory=dict)
    terminal_predicate: dict[str, Any]
    invariants: dict[str, list] = Field(default_factory=dict)
    attack_plan: dict[str, Any] | None = None
