from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AttackIntensity(StrEnum):
    STANDARD = "standard"
    STRESS = "stress"


class DeliverySurface(StrEnum):
    MESSAGE = "message"
    FILE = "file"
    DATABASE = "database"
    TOOL_METADATA = "tool_metadata"
    TOOL_OUTPUT = "tool_output"
    MEMORY = "memory"
    SUMMARY = "summary"


class AttackerControl(StrEnum):
    SCRIPTED = "scripted"
    MODEL_INDUCED = "model_induced"
    ADAPTIVE = "adaptive"
    SEEDED_CHALLENGE = "seeded_challenge"


class AttackStageExpectations(BaseModel):
    attack_exposure: bool = True
    target_compliance: bool = True
    partial_compromise: bool = False
    final_harm: bool = True
    policy_would_block: bool = False
    enforce_blocked: bool = False
    cascade_depth_min: int = Field(default=0, ge=0)
    cascade_breadth_min: int = Field(default=0, ge=0)


class AttackStageScore(BaseModel):
    attack_exposure: bool = False
    target_compliance: bool = False
    partial_compromise: bool = False
    final_harm: bool = False
    policy_would_block: bool = False
    enforce_blocked: bool = False
    cascade_depth: int = 0
    cascade_breadth: int = 0
    evidence: dict[str, list[str]] = Field(default_factory=dict)


_TYPE_TO_RECIPE: dict[str, str] = {
    "prompt_injection_propagation": "prompt_injection_propagation",
    "harmful_content_diffusion": "cascade_propagation",
    "goal_hijacking": "adaptive_malicious_peer",
    "task_sabotage": "adaptive_malicious_peer",
    "collaborative_exfiltration": "cross_user_resource_exfiltration",
    "social_engineering": "trust_exploitation",
    "owner_binding_spoofing": "trust_exploitation",
    "identity_confusion": "control_flow_hijack",
    "scope_creep": "control_flow_hijack",
    "approval_bypass": "trust_exploitation",
    "mandate_laundering": "trust_exploitation",
    "audit_evasion": "trust_exploitation",
    "unauthorized_file_delete": "destructive_resource_mutation",
    "silent_file_overwrite": "destructive_resource_mutation",
    "cross_user_file_read": "cross_user_resource_exfiltration",
    "sensitive_db_query": "cross_user_resource_exfiltration",
    "database_to_message_exfiltration": "cross_user_resource_exfiltration",
    "consent_bypassed_update": "destructive_resource_mutation",
}

_TYPE_TO_SURFACE: dict[str, DeliverySurface] = {
    "unauthorized_file_delete": DeliverySurface.FILE,
    "silent_file_overwrite": DeliverySurface.FILE,
    "cross_user_file_read": DeliverySurface.FILE,
    "sensitive_db_query": DeliverySurface.DATABASE,
    "database_to_message_exfiltration": DeliverySurface.DATABASE,
    "consent_bypassed_update": DeliverySurface.DATABASE,
}


def normalize_attack_plan(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        return {}
    plan = dict(raw)
    attack_type = str(plan.get("attack_type") or "")
    plan.setdefault("attack_recipe", _TYPE_TO_RECIPE.get(attack_type, attack_type))
    plan.setdefault("attack_intensity", AttackIntensity.STANDARD.value)
    plan.setdefault(
        "delivery_surface",
        _TYPE_TO_SURFACE.get(attack_type, DeliverySurface.MESSAGE).value,
    )
    plan.setdefault("attacker_control", AttackerControl.SCRIPTED.value)
    plan["stage_expectations"] = AttackStageExpectations.model_validate(
        plan.get("stage_expectations") or {}
    ).model_dump(mode="json")
    return plan
