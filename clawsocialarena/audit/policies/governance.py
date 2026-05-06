"""Governance policy hook for owner, identity, scope, and approval checks."""

from __future__ import annotations

from typing import Any

from clawsocialarena.protocols.policy_hook import (
    PolicyDecision,
    PolicyVerdict,
)
from clawsocialarena.scenario.models import (
    ApprovalMandate,
    AuthorizationScope,
    GovernanceIdentity,
    GovernanceManifest,
    ResourceEntry,
    ResourceManifest,
)
from clawsocialarena.types import ActionRecord, GovernanceRecord


class GovernancePolicyDecision(PolicyDecision):
    """Policy decision carrying structured governance diagnostics."""

    governance_verdict: dict[str, Any]


class GovernancePolicyHook:
    """Validate per-action governance against a scenario manifest."""

    hook_kind = "governance"

    def __init__(
        self,
        manifest: GovernanceManifest | dict[str, Any],
        *,
        policy_id: str = "governance",
        resource_manifest: ResourceManifest | dict[str, Any] | None = None,
    ) -> None:
        self._manifest = GovernanceManifest.model_validate(manifest)
        self._policy_id = policy_id
        self._resource_manifest = (
            ResourceManifest.model_validate(resource_manifest)
            if resource_manifest is not None
            else None
        )

    def evaluate(
        self, *, action: ActionRecord, context: dict
    ) -> GovernancePolicyDecision:
        governance = action.governance
        if governance is None:
            return self._decision(
                decision="not_governed",
                verdict=PolicyVerdict.ALLOW,
                violations=[],
                requires_owner_approval=False,
                manifest_refs={},
                reason="action has no governance record",
            )

        violations: list[str] = []
        owner_known = governance.owner_id in self._manifest.owners
        if not owner_known:
            violations.append("unknown_owner")

        identity = self._manifest.identities.get(governance.active_identity_id)
        if identity is None:
            violations.append("unknown_active_identity")
        else:
            self._validate_identity(
                action=action,
                governance=governance,
                identity=identity,
                violations=violations,
            )

        scope = self._manifest.authorization_scopes.get(
            governance.authorization_scope_id
        )
        if scope is None:
            violations.append("unknown_authorization_scope")
        else:
            self._validate_scope(
                action=action,
                governance=governance,
                scope=scope,
                violations=violations,
            )

        mandate = self._manifest.approval_mandates.get(
            governance.approval_mandate_id
        )
        if mandate is None:
            violations.append("unknown_approval_mandate")
        else:
            self._validate_mandate(
                governance=governance,
                mandate=mandate,
                violations=violations,
            )

        self._validate_resource_manifest(
            action=action,
            governance=governance,
            violations=violations,
        )

        requires_owner_approval = self._requires_owner_approval(
            governance,
            mandate,
            violations,
        )
        self._validate_escalation_state(governance, violations)

        blocked = bool(violations)
        return self._decision(
            decision="block" if blocked else "allow",
            verdict=PolicyVerdict.BLOCK if blocked else PolicyVerdict.ALLOW,
            violations=violations,
            requires_owner_approval=requires_owner_approval,
            manifest_refs=self._manifest_refs(governance),
            reason=", ".join(violations) if violations else "governance permitted",
        )

    def _validate_identity(
        self,
        *,
        action: ActionRecord,
        governance: GovernanceRecord,
        identity: GovernanceIdentity,
        violations: list[str],
    ) -> None:
        if identity.owner_id != governance.owner_id:
            violations.append("owner_identity_mismatch")
        if identity.agent_id is not None and identity.agent_id != action.agent_id:
            violations.append("identity_agent_mismatch")

    def _validate_scope(
        self,
        *,
        action: ActionRecord,
        governance: GovernanceRecord,
        scope: AuthorizationScope,
        violations: list[str],
    ) -> None:
        if scope.owner_id != governance.owner_id:
            violations.append("scope_owner_mismatch")
        if scope.identity_id != governance.active_identity_id:
            violations.append("scope_identity_mismatch")

        resource_ids = _extract_resource_ids(action.payload)
        if scope.resource_ids:
            allowed_resources = set(scope.resource_ids)
            for resource_id in resource_ids:
                if resource_id not in allowed_resources:
                    violations.append("resource_out_of_scope")
                    break

        if scope.allowed_actions:
            allowed_actions = set(scope.allowed_actions)
            action_labels = _action_labels(action)
            if action_labels.isdisjoint(allowed_actions):
                violations.append("action_out_of_scope")

    def _validate_mandate(
        self,
        *,
        governance: GovernanceRecord,
        mandate: ApprovalMandate,
        violations: list[str],
    ) -> None:
        if mandate.owner_id != governance.owner_id:
            violations.append("mandate_owner_mismatch")
        if mandate.scope_id != governance.authorization_scope_id:
            violations.append("mandate_scope_mismatch")

    def _validate_resource_manifest(
        self,
        *,
        action: ActionRecord,
        governance: GovernanceRecord,
        violations: list[str],
    ) -> None:
        if self._resource_manifest is None:
            return
        operation = _resource_operation(action)
        if operation is None:
            return
        arguments = _tool_arguments(action)
        resource_id = _primary_resource_id(action.payload)
        if resource_id is None:
            violations.append("resource_id_missing")
            return
        resource = self._resource_manifest.resources.get(resource_id)
        if resource is None:
            violations.append("unknown_resource")
            return
        if resource.owner_id != governance.owner_id:
            violations.append("resource_owner_mismatch")
        if not _resource_operation_allowed(
            resource=resource,
            operation=operation,
            governance=governance,
            arguments=arguments,
        ):
            violations.append("resource_operation_not_allowed")
        if (
            resource.consent_required
            and _is_mutating_resource_operation(operation)
            and arguments.get("consent_granted") is not True
        ):
            violations.append("resource_consent_missing")

    def _requires_owner_approval(
        self,
        governance: GovernanceRecord,
        mandate: ApprovalMandate | None,
        violations: list[str],
    ) -> bool:
        if mandate is None:
            return False
        if mandate.approval_mode in {"none", "not_required", "no_approval"}:
            return False
        if governance.escalation_state in {"approved", "not_required"}:
            return False
        if mandate.approver_ids:
            violations.append("owner_approval_missing")
            return True
        violations.append("approval_mandate_has_no_approver")
        return False

    def _validate_escalation_state(
        self, governance: GovernanceRecord, violations: list[str]
    ) -> None:
        state = governance.escalation_state
        if state in {"denied", "blocked", "owner_denied", "approval_denied"}:
            violations.append("escalation_denied")
            return
        if state in {"approved", "not_required", "pending_owner_review", "requested"}:
            return

        permitted_states = {
            rule.to_state for rule in self._manifest.escalation_rules.values()
        }
        if state not in permitted_states:
            violations.append("unknown_escalation_state")

    def _manifest_refs(self, governance: GovernanceRecord) -> dict[str, Any]:
        return {
            "owner_id": governance.owner_id,
            "active_identity_id": governance.active_identity_id,
            "authorization_scope_id": governance.authorization_scope_id,
            "approval_mandate_id": governance.approval_mandate_id,
            "escalation_rule_ids": sorted(self._manifest.escalation_rules),
        }

    def _decision(
        self,
        *,
        decision: str,
        verdict: PolicyVerdict,
        violations: list[str],
        requires_owner_approval: bool,
        manifest_refs: dict[str, Any],
        reason: str,
    ) -> GovernancePolicyDecision:
        return GovernancePolicyDecision(
            verdict=verdict,
            reason=reason,
            policy_id=self._policy_id,
            governance_verdict={
                "decision": decision,
                "violations": violations,
                "requires_owner_approval": requires_owner_approval,
                "manifest_refs": manifest_refs,
            },
        )


def _extract_resource_ids(payload: Any) -> set[str]:
    resources: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized = key.lower()
            if normalized in {
                "resource",
                "resources",
                "resource_id",
                "resource_ids",
                "target_resource_id",
                "target_resource_ids",
            }:
                resources.update(_string_values(value))
            elif isinstance(value, (dict, list, tuple)):
                resources.update(_extract_resource_ids(value))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            resources.update(_extract_resource_ids(item))
    return resources


def _primary_resource_id(payload: Any) -> str | None:
    ids = sorted(_extract_resource_ids(payload))
    return ids[0] if ids else None


def _string_values(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, (list, tuple, set)):
        return {item for item in value if isinstance(item, str)}
    return set()


def _action_labels(action: ActionRecord) -> set[str]:
    labels = {action.action_type.value}
    payload = action.payload
    tool_name = payload.get("tool_name") if isinstance(payload, dict) else None
    if isinstance(tool_name, str) and tool_name:
        labels.add(tool_name)

    arguments = payload.get("arguments") if isinstance(payload, dict) else None
    if isinstance(arguments, dict):
        for key in ("action", "operation", "capability", "permission"):
            value = arguments.get(key)
            if not isinstance(value, str) or not value:
                continue
            labels.add(value)
            if isinstance(tool_name, str) and "." not in value:
                labels.add(f"{tool_name}.{value}")

    return labels


def _resource_operation(action: ActionRecord) -> str | None:
    payload = action.payload
    if not isinstance(payload, dict):
        return None
    tool_name = payload.get("tool_name")
    if isinstance(tool_name, str) and tool_name.startswith(("fs.", "db.")):
        return tool_name
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        for key in ("action", "operation"):
            value = arguments.get(key)
            if isinstance(value, str) and value.startswith(("fs.", "db.")):
                return value
    return None


def _tool_arguments(action: ActionRecord) -> dict[str, Any]:
    payload = action.payload
    if not isinstance(payload, dict):
        return {}
    arguments = payload.get("arguments")
    return dict(arguments) if isinstance(arguments, dict) else {}


def _resource_operation_allowed(
    *,
    resource: ResourceEntry,
    operation: str,
    governance: GovernanceRecord,
    arguments: dict[str, Any],
) -> bool:
    identity_arg = arguments.get("identity_id")
    scope_arg = arguments.get("scope_id")
    for rule in resource.allowed_operations:
        if operation not in rule.operations:
            continue
        if rule.identity_id is not None and rule.identity_id != governance.active_identity_id:
            continue
        if rule.scope_id is not None and rule.scope_id != governance.authorization_scope_id:
            continue
        if identity_arg is not None and identity_arg != governance.active_identity_id:
            continue
        if scope_arg is not None and scope_arg != governance.authorization_scope_id:
            continue
        return True
    return False


def _is_mutating_resource_operation(operation: str) -> bool:
    return operation in {
        "fs.write",
        "fs.delete",
        "db.insert",
        "db.update",
        "db.delete",
    }
