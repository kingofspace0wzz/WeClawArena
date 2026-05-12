"""Phase 5 run-batch specs (S4 step 1).

Defines the five non-overlapping slices of the 680-row manifest that
the Phase-5 pilot's incremental review loop executes. Each batch
adds new scenarios on top of the previous batch's cumulative
coverage; the union is the full pilot.

    Batch 1 (smoke):              14 cells × 5 modes × 1 task × tier 1 =  70
    Batch 2 (task diversity):     14 cells × 5 modes × 2 tasks × tier 1 = 140
    Batch 3 (tier-2 realistic):   14 cells × 5 modes × 3 tasks × tier 2 = 210
    Batch 4 (tier-3 stress):      14 cells × 5 modes × 3 tasks × tier 3 = 210
    Batch 5 (supplementary):                                              50
    -----------------------------------------------------------------------
    Total:                                                                680

Note: Batch 2 covers task indices 1 and 2 at tier 1 (Batch 1 already
covered task_index=0 at tier 1). The cumulative tier-1 coverage
after Batches 1+2 is the full 210-row tier 1 slice. This avoids
double-counting any row across batches.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from clawsocialarena.generator.phase5_manifest import select_rows


@dataclass(frozen=True)
class RunBatchSpec:
    """One Phase-5 run-batch: a named slice of the 680-row manifest."""

    batch_number: int  # 1..5
    name: str  # short_label
    description: str  # human-readable explanation
    expected_rows: int  # the count we lock as a regression assertion
    selector_fn: Callable[[dict[str, Any]], list[dict[str, Any]]] = field(
        repr=False
    )

    def select(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the manifest rows that belong to this batch.

        Raises ``ValueError`` if the resulting count does not match
        ``expected_rows`` so a drift in the manifest schema breaks
        the orchestrator immediately rather than silently
        under- or over-running a batch.
        """
        rows = self.selector_fn(manifest)
        if len(rows) != self.expected_rows:
            raise ValueError(
                f"run-batch {self.batch_number} ({self.name}) expected "
                f"{self.expected_rows} rows, selector returned {len(rows)}"
            )
        return rows


# ---------- Selector functions -----------------------------------------


def _select_smoke(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch 1: smoke. One task variant (index 0) at tier 1, all 5 modes."""
    return select_rows(manifest, stratum="main", tier_index=1, task_index=0)


def _select_task_diversity(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Batch 2: task diversity. The remaining two task variants at tier 1."""
    rows: list[dict[str, Any]] = []
    for task_index in (1, 2):
        rows.extend(
            select_rows(
                manifest,
                stratum="main",
                tier_index=1,
                task_index=task_index,
            )
        )
    return rows


def _select_tier_2(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch 3: full tier 2 (realistic). All task indices, all modes."""
    return select_rows(manifest, stratum="main", tier_index=2)


def _select_tier_3(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch 4: full tier 3 (stress). All task indices, all modes."""
    return select_rows(manifest, stratum="main", tier_index=3)


def _select_supplementary(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Batch 5: every row in the supplementary stratum."""
    return select_rows(manifest, stratum="supplementary")


# ---------- The canonical 5-batch table --------------------------------

PHASE5_RUN_BATCHES: tuple[RunBatchSpec, ...] = (
    RunBatchSpec(
        batch_number=1,
        name="smoke",
        description=(
            "14 cells × 5 attack modes × 1 task variant × tier 1 (easy)."
        ),
        expected_rows=70,
        selector_fn=_select_smoke,
    ),
    RunBatchSpec(
        batch_number=2,
        name="task_diversity",
        description=(
            "14 cells × 5 attack modes × 2 new task variants × tier 1 "
            "(easy). Cumulative tier-1 coverage after this batch = 210."
        ),
        expected_rows=140,
        selector_fn=_select_task_diversity,
    ),
    RunBatchSpec(
        batch_number=3,
        name="tier_2_realistic",
        description=(
            "14 cells × 5 attack modes × 3 task variants × tier 2 (realistic)."
        ),
        expected_rows=210,
        selector_fn=_select_tier_2,
    ),
    RunBatchSpec(
        batch_number=4,
        name="tier_3_stress",
        description=(
            "14 cells × 5 attack modes × 3 task variants × tier 3 (stress)."
        ),
        expected_rows=210,
        selector_fn=_select_tier_3,
    ),
    RunBatchSpec(
        batch_number=5,
        name="supplementary",
        description=(
            "Hard-verification (25) + episode-graph (20) + named audit (5)."
        ),
        expected_rows=50,
        selector_fn=_select_supplementary,
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
    """Sum the per-batch expected_rows; should equal the manifest total (680)."""
    return sum(spec.expected_rows for spec in PHASE5_RUN_BATCHES)
