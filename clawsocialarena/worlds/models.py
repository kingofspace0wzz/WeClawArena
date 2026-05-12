from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ResourceRole(StrEnum):
    TASK_RELEVANT = "task_relevant"
    PRIVACY_SENSITIVE = "privacy_sensitive"
    GOVERNANCE_BOUND = "governance_bound"
    ATTACK_TARGET = "attack_target"
    AUDIT_EVIDENCE = "audit_evidence"


class PersonaSpec(BaseModel):
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    goals: list[str] = Field(min_length=1)
    risk_tolerance: str = Field(default="medium", min_length=1)


class ProfileSourceSpec(BaseModel):
    dataset: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    profile_ref: str = Field(min_length=1)
    profile_hash: str = Field(min_length=1)
    privacy_boundary_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_source_ref(self) -> ProfileSourceSpec:
        if self.dataset == "AgentSocialBench" and not self.profile_ref.startswith(
            "asb://profiles/"
        ):
            raise ValueError(
                "AgentSocialBench profile_ref must start with asb://profiles/"
            )
        if not self.profile_hash.startswith("sha256:"):
            raise ValueError("profile_hash must start with sha256:")
        return self


class RelationshipSpec(BaseModel):
    other_user_id: str = Field(min_length=1)
    relationship: str = Field(min_length=1)
    trust_level: str = Field(min_length=1)


class UserSpec(BaseModel):
    user_id: str = Field(min_length=1)
    profile_source: ProfileSourceSpec
    persona: PersonaSpec
    relationships: list[RelationshipSpec] = Field(default_factory=list)


class TableSpec(BaseModel):
    columns: dict[str, str] = Field(min_length=1)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class _ResourceSpec(BaseModel):
    resource_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sensitivity: str = Field(min_length=1)
    roles: list[ResourceRole] = Field(min_length=1)
    allowed_operations: list[str] = Field(min_length=1)
    expected_final_state: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_safe_relative_path(self) -> _ResourceSpec:
        _validate_relative_safe_path(self.path)
        return self


class FileResourceSpec(_ResourceSpec):
    content: str = ""


class DatabaseResourceSpec(_ResourceSpec):
    tables: dict[str, TableSpec] = Field(min_length=1)


class ResourceCollectionSpec(BaseModel):
    files: list[FileResourceSpec] = Field(default_factory=list)
    databases: list[DatabaseResourceSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_resource_ids(self) -> ResourceCollectionSpec:
        seen: set[str] = set()
        for resource in [*self.files, *self.databases]:
            if resource.resource_id in seen:
                raise ValueError(f"duplicate resource_id {resource.resource_id!r}")
            seen.add(resource.resource_id)
        return self

    @property
    def resource_ids(self) -> set[str]:
        return {
            resource.resource_id
            for resource in [*self.files, *self.databases]
        }


class OwnerPolicySpec(BaseModel):
    owner_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)


class WorldPolicySpec(BaseModel):
    owners: dict[str, OwnerPolicySpec] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_owner_keys(self) -> WorldPolicySpec:
        for key, owner in self.owners.items():
            if owner.owner_id != key:
                raise ValueError(f"owners[{key!r}].owner_id must match key")
        return self


class SensitiveItemSpec(BaseModel):
    item_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    harm_category: str = Field(min_length=1)
    text: str = Field(min_length=1)


class LegitimateUseCaseSpec(BaseModel):
    use_case_id: str = Field(min_length=1)
    task_family: str = Field(min_length=1)
    resource_ids: list[str] = Field(min_length=1)
    description: str = Field(min_length=1)


class AttackSurfaceSpec(BaseModel):
    attack_surface_id: str = Field(min_length=1)
    attack_type: str = Field(min_length=1)
    resource_ids: list[str] = Field(min_length=1)
    harm_categories: list[str] = Field(min_length=1)


class UserWorldPack(BaseModel):
    world_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    users: list[UserSpec] = Field(min_length=1)
    resources: ResourceCollectionSpec = Field(default_factory=ResourceCollectionSpec)
    policies: WorldPolicySpec = Field(default_factory=WorldPolicySpec)
    sensitive_items: list[SensitiveItemSpec] = Field(default_factory=list)
    legitimate_use_cases: list[LegitimateUseCaseSpec] = Field(default_factory=list)
    attack_surfaces: list[AttackSurfaceSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_references(self) -> UserWorldPack:
        user_ids = {user.user_id for user in self.users}
        owner_ids = set(self.policies.owners)
        resource_ids = self.resources.resource_ids

        if len(user_ids) != len(self.users):
            raise ValueError("duplicate user_id in world pack")

        for resource in [*self.resources.files, *self.resources.databases]:
            if resource.user_id not in user_ids:
                raise ValueError(
                    f"resource {resource.resource_id!r} references unknown user "
                    f"{resource.user_id!r}"
                )
            if owner_ids and resource.owner_id not in owner_ids:
                raise ValueError(
                    f"resource {resource.resource_id!r} references unknown owner "
                    f"{resource.owner_id!r}"
                )

        owner_user_ids = {owner.user_id for owner in self.policies.owners.values()}
        for user_id in user_ids:
            if user_id not in owner_user_ids:
                raise ValueError(f"user {user_id!r} has no owner policy")
            has_resource = any(
                resource.user_id == user_id
                for resource in [*self.resources.files, *self.resources.databases]
            )
            if not has_resource:
                raise ValueError(f"user {user_id!r} has no file or database resource")

        for item in self.sensitive_items:
            if item.resource_id not in resource_ids:
                raise ValueError(
                    f"sensitive item {item.item_id!r} references unknown resource "
                    f"{item.resource_id!r}"
                )
            if owner_ids and item.owner_id not in owner_ids:
                raise ValueError(
                    f"sensitive item {item.item_id!r} references unknown owner "
                    f"{item.owner_id!r}"
                )

        for use_case in self.legitimate_use_cases:
            _validate_resource_refs(
                use_case.resource_ids,
                resource_ids,
                f"legitimate use case {use_case.use_case_id!r}",
            )

        for surface in self.attack_surfaces:
            _validate_resource_refs(
                surface.resource_ids,
                resource_ids,
                f"attack surface {surface.attack_surface_id!r}",
            )

        for user in self.users:
            for relationship in user.relationships:
                if relationship.other_user_id not in user_ids:
                    raise ValueError(
                        f"user {user.user_id!r} relationship references unknown user "
                        f"{relationship.other_user_id!r}"
                    )

        return self


def _validate_resource_refs(
    refs: list[str],
    resource_ids: set[str],
    context: str,
) -> None:
    unknown = sorted(ref for ref in refs if ref not in resource_ids)
    if unknown:
        raise ValueError(f"{context} references unknown resource {unknown[0]!r}")


def _validate_relative_safe_path(path: str) -> None:
    posix_path = PurePosixPath(path)
    if (
        posix_path.is_absolute()
        or not path.strip()
        or path.startswith("~")
        or any(part in {"", ".", ".."} for part in posix_path.parts)
    ):
        raise ValueError(f"path must be a relative safe path, got {path!r}")
