"""Smoke tests for vendored modules from clawsocialos.

Confirms that:
  - error_chains imports cleanly and exposes the expected ErrorLabel enum.
  - graph.topology imports cleanly and exposes a generator entrypoint.

The former SEM roundtrip / per-agent-isolation tests were removed in
Phase B (task B5) together with the SEM stub; MSWM lands in Phase C and
will get its own dedicated test module.
"""


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
