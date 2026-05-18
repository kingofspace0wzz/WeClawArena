from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    default_owner_id: str | None = Field(default=None, min_length=1)
    default_identity_id: str | None = Field(default=None, min_length=1)


class CoordinationMode(StrEnum):
    """Static topology shape adopted from MARBLE engine.engine.py (lines 200-573).

    Borrowed as a scenario-spec format only; the runtime coordinator is
    the ClawSocialArena audit gateway, not the MARBLE engine. See the
    topology design spec at
    docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md
    for the shape definitions and mode-to-category mappings.
    """

    CHAIN = "chain"
    TREE = "tree"
    GRAPH = "graph"
    STAR = "star"


class AgentGraphNode(BaseModel):
    """One participant in the scenario's agent graph.

    Replaces the implicit persona-to-agent mapping inside per-category
    template Python files. The validator (see
    clawsocialarena/generator/scenario_validator.py) catches duplicate
    persona-to-agent mappings (the Camila aliasing seen in batch 0074)
    by checking owner_id uniqueness.
    """

    agent_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    persona_source: str = Field(min_length=1)
    role_label: str = Field(min_length=1)
    active_identity: str = Field(min_length=1)
    scope: list[str] = Field(default_factory=list)
    approval_mandate: str = Field(default="self", min_length=1)


class AgentGraphEdge(BaseModel):
    """One typed relationship between two agent_graph nodes.

    The relationship triple format (source, target, relationship)
    corresponds to MARBLE's relationship-triple representation. The
    channel field binds the edge to a specific gateway-mediated channel.
    """

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relationship: str = Field(min_length=1)
    channel: str = Field(min_length=1)


class AgentGraph(BaseModel):
    """Typed declaration of the scenario's topology.

    Replaces the per-category Python templates with declarative config.
    Consumed by compose_emitter (container layout), governance_emitter
    (owner / identity / scope fields), persona_emitter (per-agent
    persona source resolution), and world_pack_instantiation (resource
    selection by family_id instead of category label).
    """

    nodes: list[AgentGraphNode] = Field(default_factory=list)
    edges: list[AgentGraphEdge] = Field(default_factory=list)


class Scenario(BaseModel):
    scenario_id: str
    category: str
    task_family: str
    agents: list[ScenarioAgent]
    initial_state: dict[str, Any]
    max_turns: int
    opening_message: dict[str, Any]
    injected_messages: list[dict[str, Any]] = Field(default_factory=list)
    # Topology fields added in 2026-05-09. Backward compatible: bundles
    # produced before the topology refactor lack these fields and use the
    # legacy per-category template path. Bundles produced by family-pack
    # loaders populate both fields and route through scenario_validator.
    coordination_mode: CoordinationMode | None = Field(default=None)
    agent_graph: AgentGraph | None = Field(default=None)
    family_id: str | None = Field(default=None, min_length=1)


class McpToolSpec(BaseModel):
    """Per-tool entry in the GT bundle's `mcp_tool_manifest` (spec §4.6).

    The serialized JSON field remains ``schema`` for compatibility with
    existing scenario bundles. The Python attribute is ``input_schema`` so
    static type checkers do not see a field overriding ``BaseModel.schema()``.
    """

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    input_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
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


class ResourceType(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    SQLITE_DB = "sqlite_db"
    TABLE = "table"
    ROW_SET = "row_set"


class ResourceAccessRule(BaseModel):
    """Declared resource operations allowed for one identity/scope pair."""

    identity_id: str | None = Field(
        default=None,
        min_length=1,
        exclude_if=lambda v: v is None,
    )
    scope_id: str | None = Field(
        default=None,
        min_length=1,
        exclude_if=lambda v: v is None,
    )
    operations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_scope(self) -> "ResourceAccessRule":
        if self.identity_id is None and self.scope_id is None:
            raise ValueError("resource access rules require identity_id or scope_id")
        return self


class ResourceEntry(BaseModel):
    """Auditable file/database resource declared by a scenario bundle."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    resource_id: str = Field(min_length=1)
    resource_type: ResourceType = Field(alias="type")
    owner_id: str = Field(min_length=1)
    sensitivity: str = Field(default="internal", min_length=1)
    path: str | None = Field(
        default=None,
        min_length=1,
        exclude_if=lambda v: v is None,
    )
    table: str | None = Field(
        default=None,
        min_length=1,
        exclude_if=lambda v: v is None,
    )
    row_filter: dict[str, Any] = Field(
        default_factory=dict,
        exclude_if=lambda v: not v,
    )
    consent_required: bool = Field(default=False, exclude_if=lambda v: not v)
    allowed_operations: list[ResourceAccessRule] = Field(min_length=1)
    initial_digest: str | None = Field(
        default=None,
        min_length=1,
        exclude_if=lambda v: v is None,
    )
    expected_final_digest: str | None = Field(
        default=None,
        min_length=1,
        exclude_if=lambda v: v is None,
    )
    protected_content: list[str] = Field(
        default_factory=list,
        exclude_if=lambda v: not v,
    )
    protected_content_patterns: list[str] = Field(
        default_factory=list,
        exclude_if=lambda v: not v,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        exclude_if=lambda v: not v,
    )


class ResourceManifest(BaseModel):
    """Scenario-local resources whose access or mutation can be audited."""

    resources: dict[str, ResourceEntry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_references(self) -> "ResourceManifest":
        for key, resource in self.resources.items():
            if resource.resource_id != key:
                raise ValueError(
                    f"resources[{key!r}].resource_id must match the manifest key"
                )
        return self


class GovernanceOwner(BaseModel):
    owner_id: str = Field(min_length=1)
    user_id: str | None = Field(default=None, min_length=1)
    display_name: str | None = Field(default=None, min_length=1)


class GovernanceIdentity(BaseModel):
    identity_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    agent_id: str | None = Field(default=None, min_length=1)
    label: str | None = Field(default=None, min_length=1)


class AuthorizationScope(BaseModel):
    scope_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    identity_id: str = Field(min_length=1)
    resource_ids: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class ApprovalMandate(BaseModel):
    mandate_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)
    approver_ids: list[str] = Field(default_factory=list)
    approval_mode: str = Field(default="owner_explicit", min_length=1)


class EscalationRule(BaseModel):
    rule_id: str = Field(min_length=1)
    from_state: str = Field(min_length=1)
    to_state: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    required_actor_id: str | None = Field(default=None, min_length=1)


class GovernedAction(BaseModel):
    """Declared action that must carry decidable governance evidence.

    ``governed_actions`` in :class:`GovernanceManifest` is keyed by the
    expected ``action_id``. Each entry declares the actor, logical governed
    action, resource, required authorization scope, and optional expected
    owner/identity used by the Identity-Governance SAF scorer.
    """

    action_id: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    required_scope_id: str = Field(min_length=1)
    requires_approval: bool = False
    expected_owner_id: str | None = Field(default=None, min_length=1)
    expected_identity_id: str | None = Field(default=None, min_length=1)
    attack_family: str | None = Field(default=None, min_length=1)
    attack_type: str | None = Field(default=None, min_length=1)
    expected_violations: list[str] = Field(default_factory=list)


class GovernanceManifest(BaseModel):
    owners: dict[str, GovernanceOwner] = Field(default_factory=dict)
    identities: dict[str, GovernanceIdentity] = Field(default_factory=dict)
    authorization_scopes: dict[str, AuthorizationScope] = Field(default_factory=dict)
    approval_mandates: dict[str, ApprovalMandate] = Field(default_factory=dict)
    escalation_rules: dict[str, EscalationRule] = Field(default_factory=dict)
    governed_actions: dict[str, GovernedAction] = Field(
        default_factory=dict,
        exclude_if=lambda v: not v,
    )

    @model_validator(mode="after")
    def _validate_references(self) -> "GovernanceManifest":
        for key, owner in self.owners.items():
            if owner.owner_id != key:
                raise ValueError(
                    f"owners[{key!r}].owner_id must match the manifest key"
                )
        for key, identity in self.identities.items():
            if identity.identity_id != key:
                raise ValueError(
                    f"identities[{key!r}].identity_id must match the manifest key"
                )
            if identity.owner_id not in self.owners:
                raise ValueError(
                    f"identities[{key!r}].owner_id references unknown owner "
                    f"{identity.owner_id!r}"
                )
        for key, scope in self.authorization_scopes.items():
            if scope.scope_id != key:
                raise ValueError(
                    f"authorization_scopes[{key!r}].scope_id must match the manifest key"
                )
            if scope.owner_id not in self.owners:
                raise ValueError(
                    f"authorization_scopes[{key!r}].owner_id references unknown "
                    f"owner {scope.owner_id!r}"
                )
            if scope.identity_id not in self.identities:
                raise ValueError(
                    f"authorization_scopes[{key!r}].identity_id references unknown "
                    f"identity {scope.identity_id!r}"
                )
        for key, mandate in self.approval_mandates.items():
            if mandate.mandate_id != key:
                raise ValueError(
                    f"approval_mandates[{key!r}].mandate_id must match the manifest key"
                )
            if mandate.owner_id not in self.owners:
                raise ValueError(
                    f"approval_mandates[{key!r}].owner_id references unknown owner "
                    f"{mandate.owner_id!r}"
                )
            if mandate.scope_id not in self.authorization_scopes:
                raise ValueError(
                    f"approval_mandates[{key!r}].scope_id references unknown scope "
                    f"{mandate.scope_id!r}"
                )
        for key, rule in self.escalation_rules.items():
            if rule.rule_id != key:
                raise ValueError(
                    f"escalation_rules[{key!r}].rule_id must match the manifest key"
                )
        for key, action in self.governed_actions.items():
            if action.action_id != key:
                raise ValueError(
                    f"governed_actions[{key!r}].action_id must match the manifest key"
                )
            if action.required_scope_id not in self.authorization_scopes:
                raise ValueError(
                    f"governed_actions[{key!r}].required_scope_id references "
                    f"unknown scope {action.required_scope_id!r}"
                )
            if (
                action.expected_owner_id is not None
                and action.expected_owner_id not in self.owners
            ):
                raise ValueError(
                    f"governed_actions[{key!r}].expected_owner_id references "
                    f"unknown owner {action.expected_owner_id!r}"
                )
            if (
                action.expected_identity_id is not None
                and action.expected_identity_id not in self.identities
            ):
                raise ValueError(
                    f"governed_actions[{key!r}].expected_identity_id references "
                    f"unknown identity {action.expected_identity_id!r}"
                )
        return self


class ConstructionProfileSource(BaseModel):
    user_id: str = Field(min_length=1)
    agent_id: str | None = Field(default=None, min_length=1)
    dataset: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    profile_ref: str = Field(min_length=1)
    profile_hash: str = Field(min_length=1)
    privacy_boundary_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_profile_source(self) -> "ConstructionProfileSource":
        if self.dataset == "AgentSocialBench" and not self.profile_ref.startswith(
            "asb://profiles/"
        ):
            raise ValueError(
                "AgentSocialBench profile_ref must start with asb://profiles/"
            )
        if not self.profile_hash.startswith("sha256:"):
            raise ValueError("profile_hash must start with sha256:")
        return self


class ConstructionResourceSource(BaseModel):
    resource_id: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    materialized_path: str | None = Field(default=None, min_length=1)


class NaturalizationManifest(BaseModel):
    method: str = Field(min_length=1)
    llm_model: str | None = Field(default=None, min_length=1)
    notes: list[str] = Field(default_factory=list)


class TaskActor(BaseModel):
    agent_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    visibility: list[str] = Field(default_factory=list)


class TaskInitialization(BaseModel):
    data: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    message_history: list[str] = Field(default_factory=list)


class ConsensusRules(BaseModel):
    required_roles: list[str] = Field(default_factory=list)
    minimum_confirmations: int = Field(default=1, ge=0)
    forbidden_deciders: list[str] = Field(default_factory=list)


class BenignTaskObjective(BaseModel):
    type: str = Field(min_length=1)
    required_outcome: str = Field(min_length=1)


class TaskSuccessSpec(BaseModel):
    completion_mode: str = Field(min_length=1)
    terminal_predicate_type: str = Field(min_length=1)
    required_evidence: list[str] = Field(default_factory=list)
    reward_basis: list[str] = Field(default_factory=list)
    invalidating_conditions: list[str] = Field(default_factory=list)


class AuditEventSpec(BaseModel):
    event: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    visibility: list[str] = Field(default_factory=list)
    required_log_level: str | None = Field(default=None, min_length=1)


class SourcePattern(BaseModel):
    benchmark: str = Field(min_length=1)
    path: str = Field(min_length=1)
    motif: str = Field(min_length=1)
    adaptation: str = Field(default="structural_motif_only", min_length=1)


class ConstructionManifest(BaseModel):
    construction_mode: str = Field(min_length=1)
    world_id: str = Field(min_length=1)
    world_schema_version: str = Field(min_length=1)
    task_schema_version: str | None = Field(default=None, min_length=1)
    designed_difficulty_tier: str | None = Field(default=None, min_length=1)
    actors: list[TaskActor] = Field(default_factory=list)
    initialization: TaskInitialization = Field(default_factory=TaskInitialization)
    consensus_rules: ConsensusRules | None = None
    benign_task_objective: BenignTaskObjective | None = None
    task_success_spec: TaskSuccessSpec | None = None
    expected_task_failure_modes: list[str] = Field(default_factory=list)
    audit_events: list[AuditEventSpec] = Field(default_factory=list)
    source_pattern: SourcePattern | None = None
    profile_sources: list[ConstructionProfileSource] = Field(min_length=1)
    resource_sources: list[ConstructionResourceSource] = Field(default_factory=list)
    naturalization: NaturalizationManifest
    realism_status: str = Field(default="worldpack_draft", min_length=1)


class GTBundle(BaseModel):
    scenario_id: str
    canonical_action_stream: list[dict[str, Any]] = Field(default_factory=list)
    phase_schedule: list[dict[str, Any]] = Field(default_factory=list)
    policies: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    attribution_dag: dict[str, Any] = Field(default_factory=dict)
    integrity_requirements: dict[str, int] = Field(default_factory=dict)
    terminal_predicate: dict[str, Any]
    evaluation_criteria: dict[str, Any] = Field(default_factory=dict)
    invariants: dict[str, Any] = Field(default_factory=dict)
    attack_plan: dict[str, Any] | None = None
    # v2 additions (spec §4.6)
    mcp_tool_manifest: dict[str, McpToolSpec] = Field(default_factory=dict)
    persona_manifest: dict[str, PersonaRef] = Field(default_factory=dict)
    governance_manifest: GovernanceManifest | None = None
    resource_manifest: ResourceManifest | None = None
    construction_manifest: ConstructionManifest | None = None
