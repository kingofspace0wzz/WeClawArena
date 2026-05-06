"""Aggregator — reads v2 ``run_scorecard.json`` trees, emits long-format CSV.

Phase H rewrites the aggregator so the downstream Phase H analysis pipeline
sees one **row per run** with every headline metric flattened into typed
columns. Earlier revisions emitted one row per (scenario, metric_family,
metric_name) triple; that shape served Phase 6 but forces every table /
figure to re-reshape the CSV before reading it. v2 instead materialises
a wide row with:

    - keys:       scenario_id, category, family, model, condition,
                  privacy_level, seed, live_or_replay
    - metrics:    tsr, psi, tau, sigma, phi, s, saf_overall,
                  cdlr, culr, mplr, halr, cslr, asr
    - provenance: evaluator_version, cassette_hash, gateway_invariant_passed

Pending stubs (``status: "pending"`` rows written by the Phase G dry-run
path in ``scripts/run_grid.py``) are silently skipped so an in-flight grid
does not poison the analysis output.

Back-compat: the long-format emitter is kept as ``scorecard_to_long_rows``
so any legacy Phase-6 caller can still walk a scorecard into ``(family,
name, value)`` triples.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any


# Long-format rows kept for Phase 6 consumers (tables.py legacy paths).
_LEGACY_LONG_FIELDS: tuple[str, ...] = (
    "scenario_id",
    "condition",
    "model",
    "seed",
    "privacy_level",
    "metric_family",
    "metric_name",
    "value",
)

GOVERNANCE_ATTACK_TYPES: tuple[str, ...] = (
    "owner_binding_spoofing",
    "identity_confusion",
    "scope_creep",
    "approval_bypass",
    "mandate_laundering",
    "audit_evasion",
)

GOVERNANCE_COMPONENT_FIELDS: tuple[str, ...] = tuple(
    f"{attack_type}_rate" for attack_type in GOVERNANCE_ATTACK_TYPES
)

# Wide-format canonical row for Phase H / I (tables / figures / stats / prereg).
WIDE_FIELDS: tuple[str, ...] = (
    # Keys
    "scenario_id",
    "category",
    "family",
    "attack_axis",
    "attack_type",
    "model",
    "condition",
    "privacy_level",
    "seed",
    "live_or_replay",
    # SAF per-dim (greek-letter shorthand from spec §3).
    "s",  # SAF overall σ (kept as ``s`` to avoid clobbering ``sigma``).
    "saf_overall",
    "recoverability",
    "policy_checkability",
    "attribution",
    "evidence_integrity",
    "phase_scoped_policy",
    "identity_governance",
    "psi",  # policy_checkability
    "tau",  # attribution
    "sigma",  # recoverability (σ here is per-dim; SAF overall kept separate as ``s``).
    "phi",  # phase_scoped_policy
    "gamma",  # identity_governance
    "vaa_overall",  # Vanilla-AA audit score when the evaluator emits one.
    # Task / privacy / security / governance
    "tsr",
    "privacy_leak",  # Primary leak rate for the scenario's category (max of
                     # the per-category rates + flat ``leak_rate`` fallback).
    "cdlr",
    "culr",
    "mplr",
    "halr",
    "cslr",
    "asr",
    "governance_violation_rate",
    *GOVERNANCE_COMPONENT_FIELDS,
    # Provenance
    "evaluator_version",
    "cassette_hash",
    "gateway_invariant_passed",
)


def iter_scorecards(root: Path) -> Iterator[tuple[Path, dict]]:
    """Yield (path, scorecard_dict) for every ``run_scorecard.json`` under root."""
    for path in sorted(Path(root).rglob("run_scorecard.json")):
        with path.open() as f:
            yield path, json.load(f)


def _is_pending(scorecard: dict) -> bool:
    """True when a scorecard is a Phase G ``status: "pending"`` stub."""

    return scorecard.get("status") == "pending"


def _primary_leak(leaks: dict) -> float:
    """Collapse the category-specific leak-rate dict into one primary rate.

    Chooses the max across (CDLR, CULR, MPLR, HALR, CSLR). Falls back to
    the flat ``leak_rate`` entry if no category-specific rate is set;
    returns 0.0 when nothing is present. This gives downstream code a
    single numeric privacy column it can pair across conditions.
    """

    values = [
        float(leaks.get(key, 0.0) or 0.0)
        for key in ("CDLR", "CULR", "MPLR", "HALR", "CSLR")
    ]
    top = max(values, default=0.0)
    if top > 0.0:
        return top
    return float(leaks.get("leak_rate", 0.0) or 0.0)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    """Return ``value`` as a mapping when possible, else an empty mapping."""

    if isinstance(value, Mapping):
        return value
    return {}


def _to_float(value: Any, *, default: float = 0.0) -> float:
    """Best-effort scalar conversion used for permissive scorecard loading."""

    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_float(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> float:
    """Read the first present numeric field from ``mapping``."""

    for key in keys:
        if key in mapping:
            return _to_float(mapping[key])
    return 0.0


def _tag(meta: dict, key: str, default: str = "") -> str:
    """Read ``meta.tags[key]`` with safe fallbacks for missing/flat metas."""

    tags = meta.get("tags") or {}
    if isinstance(tags, dict) and key in tags:
        return str(tags[key])
    # Some legacy scorecards store category/family directly on meta.
    if key in meta:
        return str(meta[key])
    return default


def _attack_meta(scorecard: dict, meta: dict) -> tuple[str, str]:
    """Return ``(attack_axis, attack_type)`` with legacy fallbacks."""

    attack_plan = _as_mapping(scorecard.get("attack_plan") or meta.get("attack_plan"))

    attack_axis = (
        _tag(meta, "attack_axis")
        or str(
            attack_plan.get("attack_axis")
            or attack_plan.get("axis")
            or attack_plan.get("family")
            or ""
        )
        or _tag(meta, "category")
    )
    attack_type = (
        _tag(meta, "attack_type")
        or str(attack_plan.get("attack_type") or "")
    )
    return attack_axis, attack_type


def _governance_rates(scorecard: dict) -> dict[str, float]:
    """Flatten top-level governance metrics, defaulting legacy rows to zero."""

    governance = _as_mapping(scorecard.get("governance"))
    component_rates = _as_mapping(
        governance.get("component_rates")
        or governance.get("attack_type_rates")
        or governance.get("components")
    )
    rows = {
        "governance_violation_rate": _first_float(
            governance,
            (
                "governance_violation_rate",
                "violation_rate",
                "governance_failure_rate",
            ),
        )
    }
    for attack_type, field in zip(
        GOVERNANCE_ATTACK_TYPES, GOVERNANCE_COMPONENT_FIELDS
    ):
        rows[field] = _first_float(
            governance,
            (
                field,
                f"{attack_type}_violation_rate",
            ),
        )
        if rows[field] == 0.0:
            rows[field] = _first_float(
                component_rates,
                (
                    attack_type,
                    field,
                    f"{attack_type}_violation_rate",
                ),
            )
    return rows


def scorecard_to_wide_row(scorecard: dict) -> dict[str, Any]:
    """Flatten one v2 scorecard into a single wide row."""

    meta = scorecard.get("meta") or {}
    saf = scorecard.get("saf") or {}
    saf_dims = saf.get("dims") or {}
    task = scorecard.get("task") or {}
    privacy = scorecard.get("privacy") or {}
    leaks = privacy.get("leak_rates") or {}
    security = scorecard.get("security") or {}
    attack_axis, attack_type = _attack_meta(scorecard, meta)

    saf_overall = float(saf.get("overall", 0.0) or 0.0)
    recoverability = _to_float(saf_dims.get("recoverability"))
    policy_checkability = _to_float(saf_dims.get("policy_checkability"))
    attribution = _to_float(saf_dims.get("attribution"))
    evidence_integrity = _to_float(saf_dims.get("evidence_integrity"))
    phase_scoped_policy = _to_float(saf_dims.get("phase_scoped_policy"))
    identity_governance = _to_float(saf_dims.get("identity_governance"))

    return {
        "scenario_id": scorecard.get("scenario_id", ""),
        "category": _tag(meta, "category"),
        "family": _tag(meta, "family"),
        "attack_axis": attack_axis,
        "attack_type": attack_type,
        "model": meta.get("model", "unknown"),
        "condition": meta.get("condition", "unknown"),
        "privacy_level": meta.get("privacy_level", ""),
        "seed": int(meta.get("seed", 0) or 0),
        "live_or_replay": (
            meta.get("live_or_replay")
            or scorecard.get("live_or_replay")
            or "live"
        ),
        # SAF: overall + per-dim (greek shorthand).
        "s": saf_overall,
        "saf_overall": saf_overall,
        "recoverability": recoverability,
        "policy_checkability": policy_checkability,
        "attribution": attribution,
        "evidence_integrity": evidence_integrity,
        "phase_scoped_policy": phase_scoped_policy,
        "identity_governance": identity_governance,
        "psi": policy_checkability,
        "tau": attribution,
        "sigma": recoverability,
        "phi": phase_scoped_policy,
        "gamma": identity_governance,
        "vaa_overall": float(saf_dims["vanilla_aa_overall"])
        if "vanilla_aa_overall" in saf_dims
        else float("nan"),
        # Task / privacy / security.
        "tsr": float(task.get("tsr", 0.0) or 0.0),
        "privacy_leak": _primary_leak(leaks),
        "cdlr": float(leaks.get("CDLR", 0.0) or 0.0),
        "culr": float(leaks.get("CULR", 0.0) or 0.0),
        "mplr": float(leaks.get("MPLR", 0.0) or 0.0),
        "halr": float(leaks.get("HALR", 0.0) or 0.0),
        "cslr": float(leaks.get("CSLR", 0.0) or 0.0),
        "asr": float(security.get("asr", 0.0) or 0.0),
        **_governance_rates(scorecard),
        # Provenance.
        "evaluator_version": scorecard.get("evaluator_version", ""),
        "cassette_hash": scorecard.get("cassette_hash", ""),
        "gateway_invariant_passed": bool(
            scorecard.get("gateway_invariant_passed", True)
        ),
    }


def scorecard_to_long_rows(scorecard: dict) -> list[dict]:
    """Legacy long-format emitter (kept for Phase 6 callers).

    Emits one row per (metric_family, metric_name) pair. Phase H code
    prefers :func:`scorecard_to_wide_row`; this helper stays alive so the
    old ``model_comparison_table`` / ``headline_table`` call sites that
    group by ``(metric_family, metric_name)`` keep working unchanged.
    """

    if _is_pending(scorecard):
        return []

    meta = scorecard.get("meta") or {}
    common = {
        "scenario_id": scorecard["scenario_id"],
        "condition": meta.get("condition", "unknown"),
        "model": meta.get("model", "unknown"),
        "seed": int(meta.get("seed", 0) or 0),
        "privacy_level": meta.get("privacy_level", ""),
    }
    rows: list[dict] = []

    # SAF per-dim + overall.
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

    # Task success rate.
    task = scorecard.get("task", {}) or {}
    rows.append(
        {
            **common,
            "metric_family": "task",
            "metric_name": "tsr",
            "value": task.get("tsr", 0.0),
        }
    )

    # Privacy: flat leak_rates dict — one row per keyed leak type.
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

    # Security: flat top-level metrics.
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


def aggregate_to_csv(root: Path, out_csv: Path, *, wide: bool = True) -> int:
    """Aggregate every scorecard under ``root`` into a CSV at ``out_csv``.

    When ``wide=True`` (Phase H default) the CSV holds one row per
    scorecard, columns enumerated in :data:`WIDE_FIELDS`. When
    ``wide=False`` the legacy long-format flattening is used so any
    Phase-6-era caller keeps its existing column set.

    Returns the number of rows written (excluding header). Pending
    (``status: "pending"``) stubs are skipped.
    """

    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    if wide:
        rows = [
            scorecard_to_wide_row(sc)
            for _path, sc in iter_scorecards(root)
            if not _is_pending(sc)
        ]
        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(WIDE_FIELDS))
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    long_rows: list[dict] = []
    for _path, sc in iter_scorecards(root):
        long_rows.extend(scorecard_to_long_rows(sc))
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(_LEGACY_LONG_FIELDS))
        writer.writeheader()
        writer.writerows(long_rows)
    return len(long_rows)
