"""Shared protocol + artifact dataclass for stress attack recipes.

A stress recipe describes (a) what gets baked into the variant
bundle on disk and (b) optionally, what an adaptive attacker peer
agent should do at runtime. The orchestrator's variant generator
calls :meth:`StressRecipe.build_variant_artifacts` to produce the
mutations for a given base bundle; the live executor consults
``attacker_peer_prompt`` and ``requires_runtime_peer`` to decide
whether to spin up a second LLM agent role.

Recipe authors must NOT mutate the base bundle in place; instead
they declare their mutations in the returned
:class:`StressVariantArtifacts` and the generator writes them to a
fresh variant directory under ``attack_variants/<axis>/``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable


StressAxis = Literal["security", "privacy", "governance", "collaboration"]


@dataclass
class StressVariantArtifacts:
    """Mutations a stress recipe applies to a base bundle to produce
    an attack variant. The generator writes these out into the
    variant directory; the live executor reads them at runtime.

    Static fields (used by all recipes):

    - ``payload_text``: the canonical attack payload string. Kept in
      ``phase5_variant_metadata.attack.payload_text`` so the heuristic
      and LLM-judge scorers can match against it post-run.
    - ``target_agent_id``: which focal agent the attack targets.
    - ``opening_message_addendum``: text appended to the base
      opening_message's content (default: empty). Use this for
      attacks that need a banner / cover story before the indirect
      payload lands.
    - ``resource_file_writes``: ``{ relative_path: bytes_or_str }`` --
      files to write into the variant's ``resources/`` directory.
      Use this for indirect-prompt-injection-via-file recipes.
    - ``resource_db_inserts``: ``{ (db_relative_path, table): [row_dict, ...] }`` --
      rows to INSERT into the per-resource sqlite databases before
      Session.build. Use this for poisoned-consent-row recipes.
    - ``resource_db_updates``: ``{ (db_relative_path, table, pk_col, pk_val): {col: new_value} }``
      to UPDATE existing rows (e.g., to flip a status column).
    - ``injected_messages``: list of pre-scenario inbox plants
      (legacy single-shot injection, still useful for static stress).
    - ``recipe_metadata``: free-form metadata persisted into
      ``phase5_variant_metadata.attack.metadata``; LLM-judge can
      consume this to interpret the attack semantics.

    Adaptive fields (used by privacy + collaboration stress only):

    - ``requires_runtime_peer``: when True, the live executor spins
      up a second LLM agent role (the attacker peer) that responds
      adaptively each turn. When False, the recipe is fully static
      (resources + opening message baked into the variant on disk).
    - ``attacker_peer_id``: which agent_id the attacker peer occupies
      (a non-focal agent in the bundle's agent graph).
    - ``attacker_peer_prompt``: the system prompt for the attacker
      peer's LLM. Must define the attacker's goal, the focal agent
      to manipulate, and behavioral guardrails (e.g., do not
      explicitly reveal the attack intent in plain text).
    - ``attacker_peer_max_turns``: cap on attacker peer turns; if
      None, the peer runs every turn while the focal agent is alive.
    """

    payload_text: str
    target_agent_id: str
    opening_message_addendum: str = ""
    resource_file_writes: dict[str, str | bytes] = field(default_factory=dict)
    resource_db_inserts: dict[tuple[str, str], list[dict[str, Any]]] = field(
        default_factory=dict
    )
    resource_db_updates: dict[
        tuple[str, str, str, Any], dict[str, Any]
    ] = field(default_factory=dict)
    injected_messages: list[dict[str, Any]] = field(default_factory=list)
    recipe_metadata: dict[str, Any] = field(default_factory=dict)
    requires_runtime_peer: bool = False
    attacker_peer_id: str | None = None
    attacker_peer_prompt: str | None = None
    attacker_peer_max_turns: int | None = None


@runtime_checkable
class StressRecipe(Protocol):
    """Stress attack recipe contract.

    Concrete recipes are simple module-level singletons (frozen
    dataclass instances) that implement :meth:`build_variant_artifacts`.
    The recipe is identified by its ``name`` field, which becomes
    the ``variant_metadata.attack.attack_recipe`` value at generation
    time.
    """

    name: str
    """Canonical recipe name, e.g. ``"indirect_resource_prompt_injection"``."""

    axis: StressAxis
    """Which of the four attack axes the recipe stresses."""

    def build_variant_artifacts(
        self,
        *,
        base_bundle: dict[str, Any],
        family_id: str,
        seed: int,
    ) -> StressVariantArtifacts:
        """Produce the variant mutations for ``base_bundle``.

        ``base_bundle`` is a dict containing the parsed
        ``scenario.json`` + ``scenario.gt.json`` fields the recipe
        needs to introspect (agent graph, resources, governance
        manifest, ...). The recipe must NOT mutate this dict; it
        should return a fresh :class:`StressVariantArtifacts`
        describing the changes for the generator to apply on the
        variant copy.

        ``family_id`` is the family pack identifier (``"tau2_telecom"``,
        ``"wildclaw_social"``, ...). Recipes may dispatch on this to
        produce family-appropriate payloads (e.g., a telecom-flavored
        notice for tau2_telecom, a retail-flavored one for tau2_retail).

        ``seed`` is a per-variant deterministic seed; recipes that
        sample from a pool of payload variants should use this so
        the same base scenario + recipe combination produces the
        same variant bytes across runs.
        """
        ...


__all__ = [
    "StressAxis",
    "StressRecipe",
    "StressVariantArtifacts",
]
