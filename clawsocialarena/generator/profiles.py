"""AgentSocialBench profile loading for scenario construction."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ProfileBankEmpty(RuntimeError):
    """Raised when a profile directory contains no usable profiles."""


def _derive_from_agentsocialbench(data: dict[str, Any]) -> dict[str, Any]:
    domain: list[str] = []
    occupation = (data.get("demographics") or {}).get("occupation")
    if isinstance(occupation, str) and occupation.strip():
        domain.append(occupation.strip().lower())

    professional = data.get("professional") or {}
    for key in ("field", "industry", "role"):
        value = professional.get(key)
        if isinstance(value, str) and value.strip():
            domain.append(value.strip().lower())

    seen: set[str] = set()
    domain_dedup: list[str] = []
    for item in domain:
        if item in seen:
            continue
        seen.add(item)
        domain_dedup.append(item)

    sensitive: list[str] = []
    health = data.get("health") or {}
    for key in ("conditions", "medications", "allergies"):
        values = health.get(key) or []
        if isinstance(values, list):
            sensitive.extend(str(value) for value in values if value)
    mental_health = health.get("mental_health")
    if isinstance(mental_health, str) and mental_health.strip():
        sensitive.append(mental_health.strip())

    finance = data.get("finance") or {}
    for key in ("debts", "income_sources", "investments"):
        values = finance.get(key) or []
        if isinstance(values, list):
            sensitive.extend(str(value) for value in values if value)

    relationships: dict[str, str] = {}
    social = data.get("social") or {}
    rel_list = social.get("relationships")
    if isinstance(rel_list, list):
        for entry in rel_list:
            if not isinstance(entry, str) or not entry.strip():
                continue
            role, sep, rest = entry.partition(":")
            if not sep:
                relationships[entry.strip()] = "contact"
                continue
            name = rest.strip()
            if "(" in name:
                name = name.split("(", 1)[0].strip()
            if name:
                relationships[name] = role.strip()

    contacts = social.get("close_contacts") or social.get("contacts") or []
    if isinstance(contacts, list):
        for contact in contacts:
            if isinstance(contact, dict):
                contact_name = contact.get("name") or contact.get("id")
                role = contact.get("relationship") or contact.get("role") or "contact"
                if contact_name:
                    relationships[str(contact_name)] = str(role)
            elif isinstance(contact, str) and contact.strip():
                relationships[contact.strip()] = "contact"

    return {
        "domain": domain_dedup,
        "sensitive_items": sensitive,
        "relationships": relationships,
    }


@dataclass(frozen=True)
class Profile:
    """A single AgentSocialBench-derived profile with auditable source fields."""

    profile_id: str
    name: str
    domain: tuple[str, ...] = ()
    sensitive_items: tuple[str, ...] = ()
    relationships: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    shared_contexts: tuple[str, ...] = ()
    trust_levels: dict[str, float] = field(default_factory=dict)
    dataset: str = "AgentSocialBench"
    dataset_version: str = "unknown"
    profile_ref: str = ""
    profile_hash: str = ""
    source_path: Path | None = None
    privacy_boundary_refs: tuple[str, ...] = ()


class ProfileBank:
    """A directory of JSON profile files with seeded sampling for templates."""

    def __init__(self, profiles: list[Profile]) -> None:
        if not profiles:
            raise ProfileBankEmpty(
                "ProfileBank needs at least one profile; expected "
                "AgentSocialBench-shaped *.json files"
            )
        self._profiles = profiles
        self._by_id = {profile.profile_id: profile for profile in profiles}

    @classmethod
    def from_dir(
        cls,
        path: Path,
        *,
        dataset_version: str = "unknown",
    ) -> ProfileBank:
        if not path.exists() or not path.is_dir():
            raise ProfileBankEmpty(
                f"profile directory {path!s} does not exist. Point --profile-dir "
                "at an AgentSocialBench profile directory."
            )

        profiles: list[Profile] = []
        for profile_path in sorted(path.glob("**/*.json")):
            try:
                raw_bytes = profile_path.read_bytes()
                data = json.loads(raw_bytes.decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or "name" not in data:
                continue

            profile = _profile_from_payload(
                data,
                source_path=profile_path,
                raw_bytes=raw_bytes,
                dataset_version=dataset_version,
            )
            profiles.append(profile)

        if not profiles:
            raise ProfileBankEmpty(
                f"profile directory {path!s} contained no usable JSON profiles "
                "(each file must be a dict with a 'name' key)."
            )

        return cls(profiles)

    def __len__(self) -> int:
        return len(self._profiles)

    @property
    def profiles(self) -> list[Profile]:
        return list(self._profiles)

    def get(self, profile_id: str) -> Profile:
        return self._by_id[profile_id]

    def sample_pair(self, seed: int, category: str) -> tuple[Profile, Profile]:
        rng = random.Random(seed)
        if len(self._profiles) < 2:
            raise ProfileBankEmpty(
                "sample_pair needs at least 2 profiles; "
                f"bank has {len(self._profiles)}"
            )

        pair = self._sample_pair_constrained(rng, category.upper())
        if pair is not None:
            return pair

        first = rng.choice(self._profiles)
        remaining = [
            profile
            for profile in self._profiles
            if profile.profile_id != first.profile_id
        ]
        second = rng.choice(remaining)
        return first, second

    def sample_group(self, seed: int, category: str, n: int) -> list[Profile]:
        del category
        if n <= 0:
            return []
        rng = random.Random(seed)
        pool = list(self._profiles)
        rng.shuffle(pool)
        if len(pool) >= n:
            return pool[:n]

        out = list(pool)
        while len(out) < n:
            out.append(pool[rng.randrange(len(pool))])
        return out

    def _sample_pair_constrained(
        self,
        rng: random.Random,
        category: str,
    ) -> tuple[Profile, Profile] | None:
        if category == "CU":
            return self._sample_cu_pair(rng)
        if category == "AM":
            return self._sample_am_pair(rng)
        return None

    def _sample_cu_pair(self, rng: random.Random) -> tuple[Profile, Profile] | None:
        explicit: list[tuple[Profile, Profile]] = []
        fallback: list[tuple[Profile, Profile]] = []
        for first in self._profiles:
            for second in self._profiles:
                if first.profile_id == second.profile_id:
                    continue
                if set(first.shared_contexts) & set(second.shared_contexts):
                    explicit.append((first, second))
                    continue
                if (
                    second.profile_id in first.relationships
                    or first.profile_id in second.relationships
                ):
                    fallback.append((first, second))
        if explicit:
            return rng.choice(explicit)
        if fallback:
            return rng.choice(fallback)
        return None

    def _sample_am_pair(self, rng: random.Random) -> tuple[Profile, Profile] | None:
        min_gap = 0.3
        explicit: list[tuple[Profile, Profile]] = []
        fallback: list[tuple[Profile, Profile]] = []
        for first in self._profiles:
            for second in self._profiles:
                if first.profile_id == second.profile_id:
                    continue
                trust_first = first.trust_levels.get(second.profile_id)
                trust_second = second.trust_levels.get(first.profile_id)
                if trust_first is not None and trust_second is not None:
                    if abs(trust_first - trust_second) >= min_gap:
                        explicit.append((first, second))
                    continue
                if (
                    second.profile_id in first.relationships
                    and first.profile_id not in second.relationships
                ):
                    fallback.append((first, second))
        if explicit:
            return rng.choice(explicit)
        if fallback:
            return rng.choice(fallback)
        return None


def _profile_from_payload(
    data: dict[str, Any],
    *,
    source_path: Path,
    raw_bytes: bytes,
    dataset_version: str,
) -> Profile:
    is_asb_shape = any(
        key in data
        for key in (
            "demographics",
            "health",
            "finance",
            "social",
            "professional",
            "lifestyle",
        )
    )
    derived = _derive_from_agentsocialbench(data) if is_asb_shape else {}
    profile_id = str(data.get("profile_id") or source_path.stem)
    profile_ref = str(data.get("profile_ref") or f"asb://profiles/{profile_id}")
    sensitive = _tuple_from_list(
        data.get("sensitive_items") or derived.get("sensitive_items") or []
    )

    return Profile(
        profile_id=profile_id,
        name=str(data["name"]),
        domain=_normalise_domain(data.get("domain", derived.get("domain"))),
        sensitive_items=sensitive,
        relationships=_normalise_relationships(
            data.get("relationships") or derived.get("relationships") or {}
        ),
        raw=data,
        shared_contexts=_tuple_from_list(data.get("shared_contexts") or []),
        trust_levels=_normalise_trust_levels(data.get("trust_levels") or {}),
        dataset=str(data.get("dataset") or "AgentSocialBench"),
        dataset_version=str(data.get("dataset_version") or dataset_version),
        profile_ref=profile_ref,
        profile_hash=f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}",
        source_path=source_path,
        privacy_boundary_refs=_privacy_boundary_refs(
            data.get("privacy_boundary_refs"),
            profile_ref=profile_ref,
            sensitive_items=sensitive,
        ),
    )


def _normalise_domain(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def _normalise_relationships(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(raw_value) for key, raw_value in value.items()}


def _normalise_trust_levels(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    trust_levels: dict[str, float] = {}
    for key, raw_value in value.items():
        try:
            trust_levels[str(key)] = float(raw_value)
        except (TypeError, ValueError):
            continue
    return trust_levels


def _tuple_from_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _privacy_boundary_refs(
    explicit_refs: Any,
    *,
    profile_ref: str,
    sensitive_items: tuple[str, ...],
) -> tuple[str, ...]:
    if isinstance(explicit_refs, list):
        return tuple(str(ref) for ref in explicit_refs)
    return tuple(
        f"{profile_ref}#sensitive_items/{idx}"
        for idx, _item in enumerate(sensitive_items)
    )
