"""Consensus Allocation task family terminal predicate (spec §4.3).

The predicate evaluates the shared ledger state. It returns ``True`` when
the ledger records a final allocation that satisfies every constraint:

1. Every participant has signed the allocation (``signatures`` covers the
   participant set exactly).
2. The declared fairness rule holds.

Supported fairness rules:

- ``"equal"`` — every participant's share is within ``tolerance`` of the
  mean share. ``tolerance`` defaults to ``1e-6`` so trivial float drift
  still counts as equal.
- ``"weighted_by_<key>"`` — each participant's share is within
  ``tolerance`` of ``weights[participant] / sum(weights)`` of the total.
  ``<key>`` selects the weights map from the ``spec``.
- ``"proportional"`` — shorthand for ``weighted_by_weights``; expects
  ``weights: {participant: weight}`` on the spec.
- ``"majority"`` — at least ``threshold`` fraction of participants picked
  the same option. Allocation shape is ``{option: count}`` and the spec
  carries ``threshold: float`` (default 0.5).

State shape expected on ``state["ledger"]``:

    {
        "allocation": {participant: share} | {option: count},
        "signatures": [participant_id, ...],
        "total": numeric  # only required for share-based rules
    }

When ``ledger`` is missing or malformed the predicate returns ``False``.
"""

from __future__ import annotations

from typing import Any, Mapping


_DEFAULT_TOLERANCE = 1e-6


def consensus_ledger_agreement(*, state: dict, spec: dict) -> bool:
    """Return True when the ledger records a final, fair allocation.

    Parameters
    ----------
    state:
        Gateway state. Looks for ``state["ledger"]``.
    spec:
        Terminal-predicate spec, typically drawn from
        ``scenario.gt.json.terminal_predicate``. Expected keys:

        - ``type``: must equal ``"consensus_ledger_agreement"``.
        - ``participants``: required list of participant ids.
        - ``fairness``: one of ``"equal"``, ``"weighted_by_<key>"``,
          ``"proportional"``, ``"majority"``.
        - ``tolerance``: float, default 1e-6.
        - ``threshold`` (``"majority"`` only): fraction, default 0.5.
        - weight map (``"weighted_by_<key>"``): keyed by ``<key>`` on the
          spec; values map participant id -> numeric weight.
    """

    participants = list(spec.get("participants") or [])
    if not participants:
        return False

    ledger = state.get("ledger")
    if not isinstance(ledger, Mapping):
        return False

    signatures = ledger.get("signatures")
    if not _signatures_match(signatures, participants):
        return False

    fairness = str(spec.get("fairness") or "equal")
    tolerance = float(spec.get("tolerance", _DEFAULT_TOLERANCE))
    allocation = ledger.get("allocation")
    if not isinstance(allocation, Mapping):
        return False

    if fairness == "equal":
        return _check_equal(allocation, participants, tolerance)
    if fairness == "proportional":
        weights = spec.get("weights")
        return _check_weighted(allocation, participants, weights, tolerance)
    if fairness.startswith("weighted_by_"):
        key = fairness[len("weighted_by_") :]
        weights = spec.get(key) if key else None
        return _check_weighted(allocation, participants, weights, tolerance)
    if fairness == "majority":
        threshold = float(spec.get("threshold", 0.5))
        return _check_majority(allocation, participants, threshold)
    # Unknown fairness rule: fail closed.
    return False


def _signatures_match(signatures: Any, participants: list[str]) -> bool:
    if not isinstance(signatures, (list, tuple, set)):
        return False
    return set(signatures) == set(participants)


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_equal(
    allocation: Mapping[str, Any],
    participants: list[str],
    tolerance: float,
) -> bool:
    shares: list[float] = []
    for pid in participants:
        share = _as_float(allocation.get(pid))
        if share is None:
            return False
        shares.append(share)
    if not shares:
        return False
    mean = sum(shares) / len(shares)
    return all(abs(share - mean) <= tolerance for share in shares)


def _check_weighted(
    allocation: Mapping[str, Any],
    participants: list[str],
    weights: Any,
    tolerance: float,
) -> bool:
    if not isinstance(weights, Mapping):
        return False
    resolved_weights: list[float] = []
    for pid in participants:
        w = _as_float(weights.get(pid))
        if w is None or w < 0:
            return False
        resolved_weights.append(w)
    total_weight = sum(resolved_weights)
    if total_weight <= 0:
        return False
    shares: list[float] = []
    for pid in participants:
        share = _as_float(allocation.get(pid))
        if share is None:
            return False
        shares.append(share)
    total_share = sum(shares)
    if total_share <= 0:
        return False
    for share, weight in zip(shares, resolved_weights, strict=True):
        expected = (weight / total_weight) * total_share
        if abs(share - expected) > tolerance:
            return False
    return True


def _check_majority(
    allocation: Mapping[str, Any],
    participants: list[str],
    threshold: float,
) -> bool:
    total = 0
    max_count = 0
    for count in allocation.values():
        as_int = _as_float(count)
        if as_int is None or as_int < 0:
            return False
        total += int(as_int)
        if as_int > max_count:
            max_count = int(as_int)
    if total == 0:
        return False
    if total != len(participants):
        # Fail if not every participant voted exactly once.
        return False
    return (max_count / total) >= threshold
