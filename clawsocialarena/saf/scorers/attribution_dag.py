"""SAF dim 3: Inference-Chain Responsibility Attribution.

F1 between produced DAG and GT DAG on edge-with-label triples.
Empty GT + empty produced = 1.0 (trivially correct).
Empty GT + non-empty produced = 0.0 (false positives).
"""


def _f1(pred: set[tuple], gt: set[tuple]) -> float:
    if not pred and not gt:
        return 1.0
    if not pred or not gt:
        return 0.0
    tp = len(pred & gt)
    p = tp / len(pred)
    r = tp / len(gt)
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def score(*, produced_dag: dict, gt_dag: dict) -> float:
    pred_edges = {
        (e["src"], e["dst"], e.get("label", ""))
        for e in produced_dag.get("edges", [])
    }
    gt_edges = {
        (e["src"], e["dst"], e.get("label", ""))
        for e in gt_dag.get("edges", [])
    }
    if not gt_edges:
        return 1.0 if not pred_edges else 0.0
    return _f1(pred_edges, gt_edges)
