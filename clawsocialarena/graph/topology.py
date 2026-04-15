# Vendored from clawsocialos/clawsocialos/graph/topology.py on 2026-04-15; modified.
"""Topology generators for social graphs.

Phase 2 vendor scope: only the Watts-Strogatz generator is needed by the
forthcoming scenario generator (Phase 5). The upstream module imports
`RelationshipType`, `UserProfile`, `GraphConfig`, and `SocialGraph` from
`clawsocialos.core.types` / `clawsocialos.graph.social_graph`. None of
those exist in ClawSocialArena yet, so they are stubbed inline as
minimal local types just rich enough to keep the generator importable
and exercisable. Phase 5 will replace these stubs with arena-native
graph + profile types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import networkx as nx
import numpy as np


# --------------------------------------------------------------------------
# Local stubs (replace the upstream clawsocialos.core.types / social_graph
# imports that ClawSocialArena does not yet have).
# --------------------------------------------------------------------------


class RelationshipType(Enum):
    FRIEND = "friend"
    COLLEAGUE = "colleague"
    FAMILY = "family"
    ACQUAINTANCE = "acquaintance"


@dataclass
class UserProfile:
    user_id: str
    name: str = ""


@dataclass
class GraphConfig:
    topology: str = "watts_strogatz"
    mean_degree: int = 2
    rewiring_probability: float = 0.3
    relationship_types: dict = field(default_factory=lambda: {"friend": 1.0})
    initial_trust: dict = field(default_factory=lambda: {"friend": 0.5})


@dataclass
class _Edge:
    relationship: RelationshipType
    trust: float
    interaction_count: int = 0


@dataclass
class _UserNode:
    user_id: str
    profile: UserProfile


class SocialGraph:
    """Minimal directed social graph stub.

    Only the subset used by `TopologyGenerator.watts_strogatz` is
    implemented (`add_user`, `add_edge`, `nodes`, `edges`). Phase 5 will
    swap this for the full arena-native graph type.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, _UserNode] = {}
        self.edges: dict[tuple[str, str], _Edge] = {}

    def add_user(self, user_id: str, profile: UserProfile) -> None:
        self.nodes[user_id] = _UserNode(user_id=user_id, profile=profile)

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        rel: RelationshipType,
        trust: float,
    ) -> None:
        self.edges[(from_id, to_id)] = _Edge(
            relationship=rel,
            trust=max(0.0, min(1.0, trust)),
        )


# --------------------------------------------------------------------------
# Topology generators
# --------------------------------------------------------------------------


class TopologyGenerator:
    """Static methods that create pre-wired SocialGraph instances."""

    @staticmethod
    def watts_strogatz(
        profiles: list[UserProfile],
        config: GraphConfig,
        rng: Any,
    ) -> SocialGraph:
        """Generate a Watts-Strogatz small-world graph.

        Parameters
        ----------
        profiles : list[UserProfile]
            One profile per node.
        config : GraphConfig
            Contains *mean_degree*, *rewiring_probability*,
            *relationship_types* (mapping to probabilities),
            and *initial_trust* (mapping to default trust values).
        rng : numpy or stdlib random generator
            Used for reproducible relationship-type assignment.
            Must support ``random()`` and ``choices(population, weights)``.
        """
        n = len(profiles)
        k = config.mean_degree
        p = config.rewiring_probability

        # Derive a deterministic integer seed from the rng so that the
        # networkx graph is reproducible given the same rng state.
        # Support both stdlib random.Random and numpy RNGs
        if hasattr(rng, "randrange"):
            nx_seed = rng.randrange(2**31)
        else:
            nx_seed = int(rng.integers(2**31))
        nx_graph = nx.watts_strogatz_graph(n, k, p, seed=nx_seed)

        # --- Prepare relationship distribution --------------------------------
        rel_types: list[RelationshipType] = []
        rel_weights: list[float] = []
        for key, weight in config.relationship_types.items():
            if isinstance(key, RelationshipType):
                rel_types.append(key)
            else:
                rel_types.append(RelationshipType(key))
            rel_weights.append(weight)

        # --- Build initial-trust lookup (normalise keys) ----------------------
        initial_trust_map: dict[RelationshipType, float] = {}
        for key, val in config.initial_trust.items():
            if isinstance(key, RelationshipType):
                initial_trust_map[key] = val
            else:
                initial_trust_map[RelationshipType(key)] = val

        # --- Populate the SocialGraph -----------------------------------------
        graph = SocialGraph()

        for i, profile in enumerate(profiles):
            graph.add_user(profile.user_id, profile)

        for u, v in nx_graph.edges():
            if hasattr(rng, "choices"):
                rel = rng.choices(rel_types, weights=rel_weights, k=1)[0]
            else:
                # numpy RNG: normalize weights and use choice
                w = np.array(rel_weights, dtype=float)
                w /= w.sum()
                rel = rel_types[int(rng.choice(len(rel_types), p=w))]
            trust_val = initial_trust_map.get(rel, 0.5)

            uid_u = profiles[u].user_id
            uid_v = profiles[v].user_id

            # Bidirectional edges share the same relationship type and
            # initial trust.
            graph.add_edge(uid_u, uid_v, rel, trust_val)
            graph.add_edge(uid_v, uid_u, rel, trust_val)

        return graph
