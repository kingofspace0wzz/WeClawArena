"""Aggregator - reads run_scorecard JSON files, emits long-format CSV.

One row per (scenario_id, condition, model, metric_family, metric_name, value).
Scorecard metadata (condition, model, seed, privacy_level) comes from the
scorecard's ``meta`` dict, populated by the batch runner (Phase 6.1).
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path


def iter_scorecards(root: Path) -> Iterator[tuple[Path, dict]]:
    """Yield (path, scorecard_dict) for every ``run_scorecard.json`` under root."""
    for path in sorted(Path(root).rglob("run_scorecard.json")):
        with path.open() as f:
            yield path, json.load(f)


def scorecard_to_rows(scorecard: dict) -> list[dict]:
    """Flatten a single scorecard into long-format rows."""
    meta = scorecard.get("meta", {}) or {}
    common = {
        "scenario_id": scorecard["scenario_id"],
        "condition": meta.get("condition", "unknown"),
        "model": meta.get("model", "unknown"),
        "seed": meta.get("seed", 0),
        "privacy_level": meta.get("privacy_level", ""),
    }
    rows: list[dict] = []

    # SAF per-dim + overall
    saf = scorecard.get("saf", {}) or {}
    for dim, value in (saf.get("dims") or {}).items():
        rows.append(
            {**common, "metric_family": "saf", "metric_name": dim, "value": value}
        )
    rows.append(
        {
            **common,
            "metric_family": "saf",
            "metric_name": "overall",
            "value": saf.get("overall", 0.0),
        }
    )

    # Task success rate
    task = scorecard.get("task", {}) or {}
    rows.append(
        {
            **common,
            "metric_family": "task",
            "metric_name": "tsr",
            "value": task.get("tsr", 0.0),
        }
    )

    # Privacy (flat leak_rates dict — one row per keyed leak type)
    privacy = scorecard.get("privacy", {}) or {}
    for lk_name, lk_val in (privacy.get("leak_rates") or {}).items():
        rows.append(
            {
                **common,
                "metric_family": "privacy",
                "metric_name": lk_name,
                "value": lk_val,
            }
        )

    # Security (flat top-level metrics)
    sec = scorecard.get("security", {}) or {}
    for name in ("asr", "prop_depth", "tiua"):
        rows.append(
            {
                **common,
                "metric_family": "security",
                "metric_name": name,
                "value": sec.get(name, 0.0),
            }
        )

    return rows


def aggregate_to_csv(root: Path, out_csv: Path) -> int:
    """Aggregate all scorecards under ``root`` to long-format CSV.

    Returns the number of rows written (excluding the header).
    """
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    for _path, sc in iter_scorecards(root):
        all_rows.extend(scorecard_to_rows(sc))

    fieldnames = [
        "scenario_id",
        "condition",
        "model",
        "seed",
        "privacy_level",
        "metric_family",
        "metric_name",
        "value",
    ]
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)
    return len(all_rows)
