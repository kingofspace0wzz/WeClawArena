"""Grid config schema for the Phase G batch runner.

A ``GridRow`` captures one cell of the run grid: a specific scenario /
audit condition / model / privacy level / seed combination plus a tag
recording whether the cell is a live or replay run. Grid YAML files
(``configs/main_table.yaml`` and ``configs/ablations.yaml``) list rows
directly; the batch runner loads them via :func:`load_grid`.

The schema is intentionally narrow: everything the batch runner needs
to decide (a) which scenario bundle to load, (b) how to bring the
compose up, (c) which model plugin to wire, and (d) whether to replay
a pre-recorded cassette instead of going live. Fields that vary per
scenario (max turns, attack plan, etc.) are already captured in the
scenario bundle; fields that vary per cell but are orthogonal to the
grid dimensions (analysis tags, RNG seeds for sub-components) can ride
along via the optional ``tags`` free-form mapping.

Validation is type-level only: mandatory fields must be present and of
the right type, ``live_or_replay`` must be one of ``{"live", "replay"}``,
``condition`` must be one of the three :class:`AuditCondition` values,
``seed`` must be a non-negative integer. Scenario existence and model
reachability are deliberately not validated here — those are runtime
concerns the batch runner surfaces when it tries to load / dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from clawsocialarena.types import AuditCondition


VALID_LIVE_OR_REPLAY: frozenset[str] = frozenset({"live", "replay"})


@dataclass(frozen=True)
class GridRow:
    """One cell of the run grid.

    Attributes:
        scenario_id: Stable identifier of the scenario to run. The batch
            runner resolves this against a scenarios directory supplied
            via CLI; missing scenarios raise at dispatch time.
        condition: Audit condition (``baseline`` / ``passive`` / ``enforce``).
            Stored as :class:`AuditCondition` so downstream code gets a
            typed value without re-parsing strings.
        model: Model identifier, e.g. ``claude-sonnet-4-6`` or
            ``gpt-5-mini``. Looked up against the rate table for cost
            estimation and handed to the provider plugin when dispatching
            a live run.
        privacy_level: AgentSocialBench L0-L4 ladder selector
            (``"L0"``/``"L1"``/.../``"L4"``). Scenarios interpret the
            level via their persona manifest; the runner just passes it
            through.
        seed: RNG seed; distinct seeds for the same
            ``(scenario_id, condition, model, privacy_level)`` produce
            the seed-variance spot-check stratum.
        live_or_replay: ``"live"`` runs a fresh gateway session under a
            real (or mocked) LLM; ``"replay"`` drives
            :class:`~clawsocialarena.gateway.replay.ReplayDriver` against
            a pre-recorded cassette.
        cassette_path: For replay rows, the filesystem path to the
            cassette.jsonl to replay (relative paths resolve against the
            YAML file's parent directory). Ignored for live rows.
        tags: Free-form string-to-string map for analysis provenance
            (e.g. ``{"bucket": "main_table", "stratum": "headline"}``).
            Written through to the scorecard's ``meta`` field.
    """

    scenario_id: str
    condition: AuditCondition
    model: str
    privacy_level: str
    seed: int
    live_or_replay: Literal["live", "replay"]
    cassette_path: Path | None = None
    tags: dict[str, str] = field(default_factory=dict)


def _coerce_row(
    raw: dict[str, Any], *, row_index: int, base_dir: Path | None
) -> GridRow:
    """Validate one row dict and return a typed :class:`GridRow`.

    ``row_index`` feeds into error messages so a malformed YAML pinpoints
    the offending entry. ``base_dir`` is the directory of the YAML file,
    used to resolve relative ``cassette_path`` values.
    """

    def _require(key: str, type_: type) -> Any:
        if key not in raw:
            raise ValueError(
                f"grid row #{row_index}: missing required field {key!r}"
            )
        value = raw[key]
        if not isinstance(value, type_):
            raise TypeError(
                f"grid row #{row_index}: field {key!r} must be "
                f"{type_.__name__}, got {type(value).__name__}"
            )
        return value

    scenario_id = _require("scenario_id", str)
    condition_raw = _require("condition", str)
    try:
        condition = AuditCondition(condition_raw)
    except ValueError as exc:
        raise ValueError(
            f"grid row #{row_index}: condition must be one of "
            f"{[c.value for c in AuditCondition]}, got {condition_raw!r}"
        ) from exc

    model = _require("model", str)
    privacy_level = _require("privacy_level", str)

    seed = _require("seed", int)
    if isinstance(seed, bool):  # bool is a subclass of int — reject explicitly
        raise TypeError(
            f"grid row #{row_index}: field 'seed' must be int, got bool"
        )
    if seed < 0:
        raise ValueError(
            f"grid row #{row_index}: field 'seed' must be non-negative, got {seed}"
        )

    lor = _require("live_or_replay", str)
    if lor not in VALID_LIVE_OR_REPLAY:
        raise ValueError(
            f"grid row #{row_index}: field 'live_or_replay' must be one of "
            f"{sorted(VALID_LIVE_OR_REPLAY)}, got {lor!r}"
        )

    cassette_path: Path | None = None
    cassette_raw = raw.get("cassette_path")
    if cassette_raw is not None:
        if not isinstance(cassette_raw, str):
            raise TypeError(
                f"grid row #{row_index}: field 'cassette_path' must be str, "
                f"got {type(cassette_raw).__name__}"
            )
        candidate = Path(cassette_raw)
        if not candidate.is_absolute() and base_dir is not None:
            candidate = (base_dir / candidate).resolve()
        cassette_path = candidate

    tags_raw = raw.get("tags", {}) or {}
    if not isinstance(tags_raw, dict):
        raise TypeError(
            f"grid row #{row_index}: field 'tags' must be a mapping, "
            f"got {type(tags_raw).__name__}"
        )
    tags: dict[str, str] = {}
    for k, v in tags_raw.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise TypeError(
                f"grid row #{row_index}: 'tags' entries must be str->str"
            )
        tags[k] = v

    if lor == "replay" and cassette_path is None:
        raise ValueError(
            f"grid row #{row_index}: replay rows must declare 'cassette_path'"
        )

    return GridRow(
        scenario_id=scenario_id,
        condition=condition,
        model=model,
        privacy_level=privacy_level,
        seed=seed,
        live_or_replay=lor,  # type: ignore[arg-type]
        cassette_path=cassette_path,
        tags=tags,
    )


def load_grid(path: Path | str) -> list[GridRow]:
    """Load and validate a grid YAML into a list of :class:`GridRow`.

    The YAML file must be a list (top-level) of mappings. An empty list
    is legal and returns ``[]`` (useful for programmatic grid generation
    that writes the file first and populates it later). Paths inside
    rows resolve relative to the YAML file's parent directory.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        ValueError: on structural errors (missing keys, bad enum values,
            relative cassette paths with no anchor, etc.).
        TypeError: on type mismatches.
    """

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"grid config not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(
            f"grid config {p} must be a YAML list at top level, got "
            f"{type(data).__name__}"
        )

    rows: list[GridRow] = []
    for idx, raw in enumerate(data):
        if not isinstance(raw, dict):
            raise ValueError(
                f"grid row #{idx} in {p} must be a mapping, got "
                f"{type(raw).__name__}"
            )
        rows.append(_coerce_row(raw, row_index=idx, base_dir=p.parent))
    return rows
