"""Phase F / Task F2: Attribution F1 scorer over MSWM-built DAGs.

Each test frames a hand-crafted produced + GT DAG so the F1 math is
transparent. The scorer must:

- Skip annotation nodes (``label="policy"``) per the Phase C.5 decision
  from the AttributionGraphBuilder.
- Score each label class (L0, L1, LX, LR, LF) via both edge-set F1 and
  node-label-set F1.
- Obey the chains-of-length->=2 rule: scenarios with no chain edges in
  the GT are degenerate (singletons excluded from the tau denominator).
"""

from __future__ import annotations

from clawsocialarena.saf.scorers import attribution_dag


def _dag(nodes: list[tuple[str, str]], edges: list[tuple[str, str, str]]) -> dict:
    """Build a DAG dict from (id, label) pairs and (src, dst, label) triples."""

    return {
        "nodes": [{"id": nid, "label": lbl, "agent_id": nid} for nid, lbl in nodes],
        "edges": [{"src": s, "dst": d, "label": lbl} for s, d, lbl in edges],
    }


def test_policy_annotation_nodes_excluded_from_node_set():
    """A produced DAG with policy_decision annotations must not inflate
    the node F1 denominator. The GT has 2 labelled nodes + 1 edge; the
    produced matches exactly on chain content but adds a policy node."""

    gt = _dag(
        nodes=[("t0", "L0"), ("t1", "L1")],
        edges=[("t0", "t1", "L1")],
    )
    produced = _dag(
        nodes=[("t0", "L0"), ("t1", "L1"), ("pol-0", "policy")],
        edges=[("t0", "t1", "L1"), ("t0", "pol-0", "policy")],
    )
    # Perfect match after policy nodes+edges are filtered.
    assert attribution_dag.score(produced_dag=produced, gt_dag=gt) == 1.0


def test_all_five_label_classes_scored():
    """Every SAF label {L0, L1, LX, LR, LF} contributes a node-label
    F1 component. A produced DAG that mislabels one node partially loses
    the node F1."""

    gt = _dag(
        nodes=[
            ("n0", "L0"),
            ("n1", "L1"),
            ("n2", "LX"),
            ("n3", "LR"),
            ("n4", "LF"),
        ],
        edges=[
            ("n0", "n1", "L1"),
            ("n1", "n2", "LX"),
            ("n0", "n3", "LR"),
        ],
    )
    # Produced DAG matches the edges perfectly but relabels n2 as L1.
    produced = _dag(
        nodes=[
            ("n0", "L0"),
            ("n1", "L1"),
            ("n2", "L1"),  # mislabelled
            ("n3", "LR"),
            ("n4", "LF"),
        ],
        edges=[
            ("n0", "n1", "L1"),
            ("n1", "n2", "LX"),
            ("n0", "n3", "LR"),
        ],
    )
    s = attribution_dag.score(produced_dag=produced, gt_dag=gt)
    # edge_f1 = 1.0 (edges match exactly)
    # node_f1: pred = {(n0,L0),(n1,L1),(n2,L1),(n3,LR),(n4,LF)}
    #          gt   = {(n0,L0),(n1,L1),(n2,LX),(n3,LR),(n4,LF)}
    #          tp = 4, |pred|=5, |gt|=5 -> p=r=0.8 -> F1=0.8
    # mean = (1.0 + 0.8) / 2 = 0.9
    assert abs(s - 0.9) < 1e-9


def test_missing_l0_root_reduces_edge_f1():
    gt = _dag(
        nodes=[("t0", "L0"), ("t1", "L1")],
        edges=[("t0", "t1", "L1")],
    )
    # Produced DAG drops the chain entirely.
    produced = _dag(nodes=[], edges=[])
    # GT has content; produced is empty -> both components collapse to 0.
    assert attribution_dag.score(produced_dag=produced, gt_dag=gt) == 0.0


def test_empty_gt_with_policy_only_produced_is_vacuous_match():
    """If the GT has no chain content AND the produced DAG only emits
    annotation nodes, after filtering both sides are empty -> 1.0."""

    gt = _dag(nodes=[], edges=[])
    produced = _dag(
        nodes=[("pol-0", "policy")],
        edges=[("t-block", "pol-0", "policy")],
    )
    assert attribution_dag.score(produced_dag=produced, gt_dag=gt) == 1.0


def test_spurious_chain_on_empty_gt_is_zero():
    gt = _dag(nodes=[], edges=[])
    produced = _dag(
        nodes=[("n0", "L0"), ("n1", "L1")],
        edges=[("n0", "n1", "L1")],
    )
    assert attribution_dag.score(produced_dag=produced, gt_dag=gt) == 0.0


def test_partial_edge_match_is_mean_of_edge_and_node_f1():
    gt = _dag(
        nodes=[("n0", "L0"), ("n1", "L1"), ("n2", "LX")],
        edges=[("n0", "n1", "L1"), ("n1", "n2", "LX")],
    )
    produced = _dag(
        nodes=[("n0", "L0"), ("n1", "L1"), ("n2", "LX")],
        edges=[("n0", "n1", "L1")],  # misses the LX edge
    )
    s = attribution_dag.score(produced_dag=produced, gt_dag=gt)
    # edge_f1: tp=1, p=1.0, r=0.5 -> F1 = 2/3
    # node_f1: all 3 match -> 1.0
    # mean = (2/3 + 1.0) / 2 = 5/6
    assert abs(s - 5 / 6) < 1e-9


def test_wrong_label_on_existing_edge_drops_edge_f1():
    gt = _dag(
        nodes=[("n0", "L0"), ("n1", "LX")],
        edges=[("n0", "n1", "LX")],
    )
    # Produced inserts the same topology but labels the edge L1 instead.
    produced = _dag(
        nodes=[("n0", "L0"), ("n1", "LX")],
        edges=[("n0", "n1", "L1")],
    )
    s = attribution_dag.score(produced_dag=produced, gt_dag=gt)
    # edge_f1: tp=0 -> 0.0
    # node_f1: all match -> 1.0
    # mean = 0.5
    assert abs(s - 0.5) < 1e-9


def test_annotation_edges_also_filtered_from_edge_set():
    """Production DAG with only policy annotation edges + matching chain
    edges should equal GT's chain edges exactly after filtering."""

    gt = _dag(
        nodes=[("n0", "L0"), ("n1", "L1")],
        edges=[("n0", "n1", "L1")],
    )
    produced = _dag(
        nodes=[("n0", "L0"), ("n1", "L1"), ("pol-0", "policy")],
        edges=[
            ("n0", "n1", "L1"),
            ("n0", "pol-0", "policy"),
            ("n1", "pol-0", "policy"),
        ],
    )
    # policy edges + nodes are stripped; result is a perfect match.
    assert attribution_dag.score(produced_dag=produced, gt_dag=gt) == 1.0


def test_out_of_taxonomy_node_label_excluded():
    """Nodes with labels outside the SAF taxonomy are silently dropped
    from the node set: an auxiliary 'info' node should not affect F1."""

    gt = _dag(
        nodes=[("n0", "L0"), ("n1", "L1")],
        edges=[("n0", "n1", "L1")],
    )
    produced = _dag(
        nodes=[("n0", "L0"), ("n1", "L1"), ("aux", "info")],
        edges=[("n0", "n1", "L1")],
    )
    assert attribution_dag.score(produced_dag=produced, gt_dag=gt) == 1.0


def test_empty_both_is_vacuously_one():
    assert attribution_dag.score(
        produced_dag={"nodes": [], "edges": []},
        gt_dag={"nodes": [], "edges": []},
    ) == 1.0
