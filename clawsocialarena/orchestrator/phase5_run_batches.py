"""Phase 5 run-batch specs (S4 step 1, T12 redesign).

Defines the five non-overlapping (by intent) slices of the manifest that
the Phase-5 pilot's incremental review loop executes. With the
difficulty-tier dimension dropped in v2 (T1-T3), batches are now
attack-regime-based rather than tier-based.

marble_research redesign (8 tasks per cell) changes main counts:
    3 × 8 × 5 = 120  (marble_research)
    2 × 3 × 5 = 30   (marble_bargaining)
    9 × 3 × 5 = 135  (other families)
    Total: 285 main rows

    Batch 1 (smoke_v2):      1 row per (family, mode) = 6 families x 5 modes = 30
    Batch 2 (standard):      all 285 main rows
    Batch 3 (stress):        non-baseline rows = 57 bases x 4 modes = 228
    Batch 4 (cross_model):   same 285 main rows; orchestrator overrides agent model
    Batch 5 (supplementary): 50 supplementary rows
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class RunBatchSpec:
    """One Phase-5 run-batch: a named slice of the manifest."""

    batch_number: int  # 1..5
    name: str  # short_label
    description: str  # human-readable explanation
    expected_rows: int  # the primary count we lock as a regression assertion
    selector_fn: Callable[[dict[str, Any]], list[dict[str, Any]]] = field(
        repr=False
    )
    expected_rows_alternatives: tuple[int, ...] = ()

    def select(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the manifest rows that belong to this batch.

        Raises ``ValueError`` if the resulting count does not match
        ``expected_rows`` or any of ``expected_rows_alternatives`` so a
        drift in the manifest schema breaks the orchestrator immediately
        rather than silently under- or over-running a batch.
        """
        rows = self.selector_fn(manifest)
        valid = {self.expected_rows, *self.expected_rows_alternatives}
        if len(rows) not in valid:
            raise ValueError(
                f"run-batch {self.batch_number} ({self.name}) expected one of "
                f"{sorted(valid)} rows, selector returned {len(rows)}"
            )
        return rows


# ---------- Selector functions -----------------------------------------


def _select_smoke_v2(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch 1: smoke. One row per (family_id, attack_mode).

    6 families x 5 modes = 30 rows at spec-1 scale. Used for fast
    sanity runs that surface attacker and family issues with minimal
    compute.
    """
    rows = manifest.get("main") or []
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        key = (str(r.get("family_id")), str(r.get("attack_mode")))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _select_standard(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch 2: all main-stratum rows.

    14 cells x 3 tasks x 5 attack modes = 210 rows at spec-1 scale.
    """
    return list(manifest.get("main") or [])


def _select_stress(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch 3: non-baseline rows scored with stress-recipe overlays.

    4 non-baseline attack modes x 42 bases = 168 rows at spec-1 scale.
    """
    rows = manifest.get("main") or []
    return [r for r in rows if str(r.get("attack_mode")) != "no_attacker"]


def _select_cross_model(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch 4: same row set as standard; orchestrator overrides agent model."""
    return _select_standard(manifest)


def _select_supplementary_v2(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch 5: every row in the supplementary stratum."""
    return list(manifest.get("supplementary") or [])


# ---------- The canonical 5-batch table --------------------------------

PHASE5_RUN_BATCHES: tuple[RunBatchSpec, ...] = (
    RunBatchSpec(
        batch_number=1,
        name="smoke_v2",
        description=(
            "One row per (family, mode). Sanity run. "
            "6 families x 5 modes = 30 rows at spec-1 scale."
        ),
        expected_rows=30,
        expected_rows_alternatives=(35, 42),
        selector_fn=_select_smoke_v2,
    ),
    RunBatchSpec(
        batch_number=2,
        name="standard",
        description=(
            "All main-stratum rows with standard attack recipes (or no_attacker). "
            "57 base bundles x 5 modes = 285 rows."
        ),
        expected_rows=285,
        expected_rows_alternatives=(210, 425, 630),
        selector_fn=_select_standard,
    ),
    RunBatchSpec(
        batch_number=3,
        name="stress",
        description=(
            "Non-baseline rows scored with stress-recipe overlays. "
            "4 stress axes x 57 bases = 228 rows."
        ),
        expected_rows=228,
        expected_rows_alternatives=(168, 340, 504),
        selector_fn=_select_stress,
    ),
    RunBatchSpec(
        batch_number=4,
        name="cross_model",
        description=(
            "Same row set as R-B 2; agent model overridden for cross-model eval."
        ),
        expected_rows=285,
        expected_rows_alternatives=(210, 425, 630),
        selector_fn=_select_cross_model,
    ),
    RunBatchSpec(
        batch_number=5,
        name="supplementary",
        description=(
            "Hard-verification + episode-graph + named-audit rows. 50 rows."
        ),
        expected_rows=50,
        selector_fn=_select_supplementary_v2,
    ),
)


def run_batch_for(batch_number: int) -> RunBatchSpec:
    """Return the spec for the given 1..5 batch_number or raise ValueError."""
    for spec in PHASE5_RUN_BATCHES:
        if spec.batch_number == batch_number:
            return spec
    raise ValueError(
        f"unknown run-batch number={batch_number}; "
        f"supported: {[s.batch_number for s in PHASE5_RUN_BATCHES]}"
    )


def total_expected_rows() -> int:
    """Sum the per-batch primary expected_rows values.

    Note: batches 2 and 4 share the same row set (cross-model reuse), so
    the sum does not represent unique pilot rows. The unique row count is
    285 main + 50 supplementary = 335.
    """
    return sum(spec.expected_rows for spec in PHASE5_RUN_BATCHES)
