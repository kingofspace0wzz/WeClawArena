"""Smoke tests for vendored modules from clawsocialos.

Confirms that:
  - SEM (stubbed) supports a roundtrip and per-agent isolation.
  - error_chains imports cleanly and exposes the expected ErrorLabel enum.
  - graph.topology imports cleanly and exposes a generator entrypoint.
"""

from clawsocialarena.audit.sem import OwnershipState, SEMStore


def test_sem_store_roundtrip():
    s = SEMStore()
    s.set(
        agent_id="agent-a",
        item="medication",
        owner="user-b",
        state=OwnershipState.INFERRED,
    )
    assert (
        s.get(agent_id="agent-a", item="medication", owner="user-b")
        == OwnershipState.INFERRED
    )
    assert (
        s.get(agent_id="agent-a", item="other", owner="user-c")
        == OwnershipState.UNKNOWN
    )


def test_sem_store_per_agent_isolation():
    s = SEMStore()
    s.set(agent_id="a", item="x", owner="u", state=OwnershipState.FULL)
    assert s.get(agent_id="b", item="x", owner="u") == OwnershipState.UNKNOWN


def test_error_chains_imports_and_classifies_root_leak():
    from clawsocialarena.audit.error_chains import (
        ErrorChainClassifier,
        ErrorLabel,
    )

    # Enum values match the labels used by the cumulative evaluator.
    assert {label.value for label in ErrorLabel} >= {"L0", "L1", "LX", "LR", "LF"}

    classifier = ErrorChainClassifier()
    label = classifier.classify_leak(
        leak=("medication", "user-b", "agent-c"),
        prior_disclosures={},
        current_episode=0,
        related_items=None,
    )
    # First-time disclosure of an item the recipient hasn't seen -> L0 root.
    assert label == ErrorLabel.L0.value


def test_graph_topology_imports():
    from clawsocialarena.graph import topology  # noqa: F401
    from clawsocialarena.graph.topology import TopologyGenerator

    assert hasattr(TopologyGenerator, "watts_strogatz")
