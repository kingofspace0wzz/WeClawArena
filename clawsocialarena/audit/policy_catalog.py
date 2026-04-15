"""PolicyCatalog: maps named policy kinds to predicate factories.

Scenario GT bundles declare policies by (policy_id, kind, params, required_fields).
The catalog turns a kind + params into a concrete predicate callable.
"""

from __future__ import annotations

from typing import Callable

from clawsocialarena.audit.policy_registry import FlatPolicy, PhaseScopedPolicy
from clawsocialarena.types import ActionRecord, SocialPhase


def _get_field(r: ActionRecord, field_path: str):
    obj: object = r.model_dump()
    for part in field_path.split("."):
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            return None
    return obj


_KINDS: dict[str, Callable[[dict], Callable[[ActionRecord, dict], bool]]] = {
    "does_not_contain": lambda params: (
        lambda a, ctx: (params["substring"]).lower() not in str(
            _get_field(a, params.get("field", "payload.content")) or ""
        ).lower()
    ),
    "contains": lambda params: (
        lambda a, ctx: (params["substring"]).lower() in str(
            _get_field(a, params.get("field", "payload.content")) or ""
        ).lower()
    ),
    "always_true": lambda params: (lambda a, ctx: True),
    "always_false": lambda params: (lambda a, ctx: False),
}


class PolicyCatalog:
    def __init__(
        self,
        kinds: dict[str, Callable[[dict], Callable[[ActionRecord, dict], bool]]]
        | None = None,
    ) -> None:
        self._kinds = dict(kinds) if kinds is not None else dict(_KINDS)

    def flat_from_dict(self, p: dict) -> FlatPolicy:
        kind = p.get("kind", "always_true")
        if kind not in self._kinds:
            raise KeyError(f"unknown policy kind: {kind}")
        factory = self._kinds[kind]
        return FlatPolicy(
            policy_id=p["policy_id"],
            predicate=factory(p.get("params", {})),
            required_fields=set(p.get("required_fields", [])),
        )

    def phase_scoped_from_dict(self, p: dict) -> PhaseScopedPolicy:
        kind = p.get("kind", "always_true")
        if kind not in self._kinds:
            raise KeyError(f"unknown policy kind: {kind}")
        factory = self._kinds[kind]
        return PhaseScopedPolicy(
            policy_id=p["policy_id"],
            phase=SocialPhase(p["phase"]),
            predicate=factory(p.get("params", {})),
            required_fields=set(p.get("required_fields", [])),
        )
