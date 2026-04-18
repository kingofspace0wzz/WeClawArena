import warnings
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScenarioAgent(BaseModel):
    """Agent record inside a scenario.json (spec §4.1).

    ``allowed_tools`` (Phase D.5 Fix 4) scopes per-agent MCP access: when
    set, the generator emits only that subset into the agent's
    ``.tools.json`` so delegation and privacy scenarios can keep tools
    out of the hands of agents that should not call them. ``None``
    (the default) is equivalent to "allow every tool declared in the
    scenario's ``mcp_tool_manifest``", which keeps legacy templates
    valid without any code changes.
    """

    agent_id: str
    user_id: str
    system_prompt_template: str
    allowed_tools: list[str] | None = None


class Scenario(BaseModel):
    scenario_id: str
    category: str
    task_family: str
    agents: list[ScenarioAgent]
    initial_state: dict[str, Any]
    max_turns: int
    opening_message: dict[str, Any]


# `schema` is a deprecated helper on pydantic.BaseModel. Using it as a field
# name (required by spec §4.6) triggers a UserWarning at class-definition
# time. Suppress it locally; we never call `.schema()` on McpToolSpec.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r'Field name "schema" in "McpToolSpec".*',
        category=UserWarning,
    )

    class McpToolSpec(BaseModel):
        """Per-tool entry in the GT bundle's `mcp_tool_manifest` (spec §4.6).

        - `schema`: **advisory** JSON Schema describing the tool's input
          payload. The gateway's :class:`McpHost` does *not* validate
          incoming tool calls against it today; the field documents the
          intended contract so downstream tooling (analysis pipelines,
          attacker-model generators) can still lean on it. Phase F may
          add gateway-side JSON-Schema validation, at which point this
          field becomes enforced rather than advisory.
        - `audit_class`: one of the ActionRecord action classes
          (`outbound_message`, `side_channel`, ...). Tells the gateway which
          integrity-level requirement applies when this tool is invoked.
        """

        model_config = ConfigDict(protected_namespaces=())

        schema: dict[str, Any] = Field(default_factory=dict)
        audit_class: str


class PersonaRef(BaseModel):
    """Per-agent entry in the GT bundle's `persona_manifest` (spec §4.6).

    - `profile_ref`: stable identifier for the AgentSocialBench persona the
      agent is instantiated from (typically an `asb://profiles/...` URI).
    - `agent_id`: the scenario-local agent id this profile is bound to. Kept
      explicit so manifest entries round-trip without implicit identity rules.
    """

    profile_ref: str
    agent_id: str


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
    # v2 additions (spec §4.6)
    mcp_tool_manifest: dict[str, McpToolSpec] = Field(default_factory=dict)
    persona_manifest: dict[str, PersonaRef] = Field(default_factory=dict)
