"""Batch-runner entry point for the Phase G compute budget (spec §5.4).

Usage::

    python scripts/run_grid.py --config configs/main_table.yaml \\
        --out results/v1.0.0 --dry-run

The script walks a :class:`~clawsocialarena.experiments.grid_config.GridRow`
list, routes each row to either a live gateway session or (for rows
tagged ``live_or_replay=replay``) a :class:`ReplayDriver` pass over a
pre-recorded cassette, and persists one ``run_scorecard.json`` per row
under ``<out>/<model>/<condition>/<scenario_id>/``. Task G4 adds a
cumulative ``cost.csv`` at the top of the output tree with one row per
scorecard.

Replay rows never touch the network: the cassette's enriched format
already carries every field needed to rehydrate the action log, so
:class:`EvalRunner` can score the replayed stream deterministically and
write a real :class:`RunScorecard` (with ``live_or_replay="replay"``)
in place of the stub.

Phase G lands the infrastructure only. Docker is not installed in this
worktree and the LLM-API runs (tasks G5-G7) are deferred pending credit
approval, so live-mode dispatch is wrapped in a dry-run switch: by
default ``--dry-run`` is on, which prints a plan and writes a
``status: "pending"`` scorecard stub per row. Running without
``--dry-run`` attempts :class:`~clawsocialarena.gateway.compose_runner.ComposeRunner`
and falls back to the stub path when Docker is absent, so the same
entry point stays usable once credentials and Docker are available.

Resumability: if a target ``run_scorecard.json`` already exists and its
``status != "pending"``, the row is skipped. Stubs are always
overwritten when the runner returns to them (so a crashed run can be
restarted without manual cleanup).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from clawsocialarena.experiments.grid_config import GridRow, load_grid


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Build the CLI parser. Separated out so tests can drive it directly."""

    parser = argparse.ArgumentParser(
        description="Run a ClawSocialArena grid (live cells + replay cells)."
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to the grid YAML (e.g. configs/main_table.yaml).",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output directory root (e.g. results/v1.0.0).",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Parallelism for live runs. Currently ignored — the runner is "
        "sequential until Docker + credentials unlock concurrent compose "
        "projects.",
    )
    dry_group = parser.add_mutually_exclusive_group()
    dry_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Default: stub-only. Writes a scorecard stub per row, no "
        "compose bring-up, no LLM calls. Idempotent.",
    )
    dry_group.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Attempt real live-mode dispatch. Falls back to the stub path "
        "if Docker is unavailable. Use only when LLM credentials and Docker "
        "are both available.",
    )
    parser.set_defaults(dry_run=True)
    return parser.parse_args(argv)


def _row_dir(out: Path, row: GridRow) -> Path:
    """Return the per-row output directory: ``<out>/<model>/<condition>/<scenario_id>``."""

    return out / row.model / row.condition.value / row.scenario_id


def _scorecard_path(out: Path, row: GridRow) -> Path:
    """Return the expected scorecard path for a row."""

    return _row_dir(out, row) / "run_scorecard.json"


def _row_metadata(row: GridRow) -> dict[str, Any]:
    """Return the meta dict stored on every scorecard (stub or real)."""

    return {
        "scenario_id": row.scenario_id,
        "condition": row.condition.value,
        "model": row.model,
        "privacy_level": row.privacy_level,
        "seed": row.seed,
        "live_or_replay": row.live_or_replay,
        "cassette_path": str(row.cassette_path) if row.cassette_path else None,
        "tags": dict(row.tags),
    }


def _write_pending_stub(out: Path, row: GridRow) -> Path:
    """Write a ``status: "pending"`` scorecard stub for a row and return its path.

    The stub has the shape downstream Phase H aggregation code can key
    on: ``scenario_id`` + ``meta`` fields + the ``status`` sentinel that
    lets the aggregator ignore incomplete rows.
    """

    path = _scorecard_path(out, row)
    path.parent.mkdir(parents=True, exist_ok=True)
    stub = {
        "scenario_id": row.scenario_id,
        "status": "pending",
        "meta": _row_metadata(row),
    }
    path.write_text(json.dumps(stub, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _row_is_complete(scorecard_path: Path) -> bool:
    """True when an existing scorecard file has ``status != "pending"``.

    A missing file, a malformed JSON file, or one that explicitly carries
    ``status: "pending"`` counts as incomplete and triggers a rerun.
    """

    if not scorecard_path.exists():
        return False
    try:
        data = json.loads(scorecard_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    status = data.get("status")
    if status is None:
        # No status key at all: treat as a completed real scorecard (for
        # example a RunScorecard dump from EvalRunner.evaluate).
        return True
    return status != "pending"


def _resolve_gt_bundle_path(cassette_path: Path) -> Path:
    """Return the path to ``scenario.gt.json`` near a cassette.

    Replay rows typically put the cassette under the scenario's fixture
    directory. We look for ``scenario.gt.json`` in the same directory
    and fall back to walking up one level, which covers both the
    ``fixtures/scenarios/<scenario_id>/`` layout and the run-work-dir
    layout ``results/.../<scenario_id>/cassette.jsonl``.
    """

    candidates = [
        cassette_path.parent / "scenario.gt.json",
        cassette_path.parent.parent / "scenario.gt.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"could not locate scenario.gt.json near cassette {cassette_path}; "
        f"looked in {candidates}"
    )


def _load_gt_bundle(path: Path) -> Any:
    """Parse ``scenario.gt.json`` into a :class:`GTBundle`."""

    from clawsocialarena.scenario.models import GTBundle

    data = json.loads(path.read_text(encoding="utf-8"))
    return GTBundle.model_validate(data)


def _execute_replay(row: GridRow, out: Path) -> dict[str, Any]:
    """Replay a cassette into a real scorecard.

    Loads the scenario's GT bundle adjacent to the cassette, drives
    :class:`ReplayDriver`, seeds a shadow log from the replayed records
    so :class:`EvalRunner` stage-1 invariants have something to compare
    against, and writes the resulting :class:`RunScorecard` in place of
    the stub. Returns accounting totals so the caller (Task G4) can
    feed them into ``cost.csv`` — replay rows always report zero LLM
    tokens because the LLM was never invoked.
    """

    from clawsocialarena.action_log import ActionLog
    from clawsocialarena.audit.shadow_log import ShadowLog
    from clawsocialarena.eval.runner import EvalRunner
    from clawsocialarena.gateway.replay import ReplayDriver

    if row.cassette_path is None:
        raise ValueError(
            f"replay row for {row.scenario_id} has no cassette_path"
        )
    cassette_path = row.cassette_path
    if not cassette_path.exists():
        raise FileNotFoundError(f"cassette not found: {cassette_path}")

    gt_path = _resolve_gt_bundle_path(cassette_path)
    gt = _load_gt_bundle(gt_path)

    row_dir = _row_dir(out, row)
    row_dir.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    driver = ReplayDriver(cassette_path, gt)
    result = driver.run(db_path=row_dir / "primary.db")

    # Build a shadow log seeded from the replayed records so stage-1
    # invariants have something to compare against. Shadow records
    # re-compute prev_hash against the shadow chain head so the shadow
    # chain is internally consistent (same pattern Session uses live).
    shadow = ShadowLog(db_path=row_dir / "primary.shadow.db")
    for rec in result.records:
        shadow_rec = rec.model_copy(
            update={"prev_hash": shadow.head_hash(rec.agent_id)}
        )
        shadow.append(shadow_rec)

    primary = ActionLog(db_path=row_dir / "primary.db")
    runner = EvalRunner()
    scorecard = runner.evaluate(
        action_log=primary,
        shadow_log=shadow,
        gt=gt,
        cassette_path=cassette_path,
        live_or_replay="replay",
        meta=_row_metadata(row),
    )

    scorecard_path = _scorecard_path(out, row)
    scorecard_path.write_text(
        scorecard.model_dump_json(indent=2), encoding="utf-8"
    )

    wallclock = time.perf_counter() - start
    return {
        "status": "ok",
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "wallclock_seconds": wallclock,
    }


def _execute_live(row: GridRow, out: Path, dry_run: bool) -> dict[str, Any]:
    """Run a live row: compose bring-up, scenario, teardown, scorecard.

    Returns a dict with ``status`` and accounting fields. When dry_run
    is True (default) or Docker is absent, the execution is short-circuited
    to a pending stub; the token/cost columns land at zero.

    Phase G defers the real LLM plumbing (Tasks G5-G7). The structure of
    this function is what the runner will look like once the gateway's
    scenario-execution module lands; at that point the TODO marker below
    is replaced by a call into the compose + gateway pipeline.
    """

    start = time.perf_counter()
    _write_pending_stub(out, row)
    if dry_run:
        wallclock = time.perf_counter() - start
        return {"status": "pending_dry_run", "wallclock_seconds": wallclock}

    try:
        from clawsocialarena.gateway.compose_runner import (  # noqa: F401
            ComposeRunner,
            DockerUnavailable,
            docker_available,
        )
    except Exception as exc:  # pragma: no cover - surfaces only without the package
        print(
            f"[run_grid] compose runner import failed: {exc}; falling back to stub",
            file=sys.stderr,
        )
        wallclock = time.perf_counter() - start
        return {"status": "pending_compose_import_failed", "wallclock_seconds": wallclock}

    if not docker_available():
        print(
            f"[run_grid] docker unavailable; leaving stub for {row.scenario_id}",
            file=sys.stderr,
        )
        wallclock = time.perf_counter() - start
        return {"status": "pending_no_docker", "wallclock_seconds": wallclock}

    # TODO(G5-G7): dispatch the gateway scenario loop here. Until the
    # compose + scenario pipeline lands we intentionally short-circuit
    # so that phase-G infrastructure work can ship without LLM spend.
    print(
        f"[run_grid] live dispatch not yet implemented (G5-G7 deferred); "
        f"leaving stub for {row.scenario_id} @ {row.model}/{row.condition.value}",
        file=sys.stderr,
    )
    wallclock = time.perf_counter() - start
    return {"status": "pending_live_deferred", "wallclock_seconds": wallclock}


def run(args: argparse.Namespace) -> int:
    """Run the grid described by ``args``. Returns the process exit code."""

    rows = load_grid(args.config)
    if not rows:
        print(f"[run_grid] no rows in {args.config}; nothing to do")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)

    completed = 0
    skipped = 0
    stubbed = 0
    failed = 0
    for row in rows:
        sc_path = _scorecard_path(args.out, row)
        if _row_is_complete(sc_path):
            skipped += 1
            print(
                f"[run_grid] skip (complete): {row.scenario_id} "
                f"{row.model}/{row.condition.value}"
            )
            continue

        try:
            if row.live_or_replay == "replay":
                outcome = _execute_replay(row, args.out)
            else:
                outcome = _execute_live(row, args.out, dry_run=args.dry_run)
        except Exception as exc:
            failed += 1
            print(
                f"[run_grid] FAILED {row.scenario_id} "
                f"{row.model}/{row.condition.value}: {exc}",
                file=sys.stderr,
            )
            continue

        status = outcome.get("status", "unknown")
        if status == "ok":
            completed += 1
        elif isinstance(status, str) and status.startswith("pending"):
            stubbed += 1

    print(
        f"[run_grid] done: {completed} completed, {stubbed} stubbed, "
        f"{skipped} skipped, {failed} failed"
    )
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
