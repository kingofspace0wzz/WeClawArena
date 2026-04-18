"""RunScorecard pydantic schema.

Phase F / Task F4 introduces the v2 schema. The v2 schema preserves every
field v1 carried and adds four runtime-provenance fields so the analysis
pipeline can split results by gateway posture, cassette identity, and
episode-graph membership:

- ``gateway_invariant_passed`` — did the gateway's own invariants (egress,
  hash-chain, shadow-log parity) hold through the whole run? Stage 1 of
  the v2 EvalRunner writes this.
- ``cassette_hash`` — sha256 of the ``cassette.jsonl`` file the run
  consumed (live or replay); lets downstream code detect silent cassette
  drift between scorecard and CI fixtures.
- ``live_or_replay`` — ``"live"`` when the scorecard was emitted from a
  fresh gateway session; ``"replay"`` when it was derived via
  :mod:`clawsocialarena.gateway.replay` from a recorded cassette.
- ``episode_graph_id`` — stable id for the episode graph this scorecard
  belongs to, or ``None`` for single-scenario runs.

Phase F.5 / Fix 3 adds :class:`EpisodeGraphScorecard`: a thin wrapper
emitted by :class:`clawsocialarena.eval.episode_graph_runner.EpisodeGraphEvalRunner`
holding a graph id, per-episode :class:`RunScorecard`s, and a
:class:`~clawsocialarena.eval.cumulative.CumulativeTrajectory` computed
from the ordered episode summaries.

Backward compatibility: :meth:`RunScorecard.from_v1_dict` reads a v1
scorecard JSON and fills the four new fields with sensible defaults
(invariant_passed=True, live, no cassette hash, no episode graph). This
keeps stored v1 scorecards consumable by v2 tooling without a migration
script.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field


if TYPE_CHECKING:
    from clawsocialarena.eval.cumulative import CumulativeTrajectory


class SAFDimsPayload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    dims: dict[str, float]
    passes: dict[str, bool]
    overall: float


class TaskScorecard(BaseModel):
    tsr: float = 1.0
    partial_credit: dict[str, float] = Field(default_factory=dict)


class PrivacyScorecard(BaseModel):
    leak_rates: dict[str, float] = Field(default_factory=dict)


class SecurityScorecard(BaseModel):
    asr: float = 0.0
    prop_depth: float = 0.0
    tiua: float = 1.0


class RunScorecard(BaseModel):
    scenario_id: str
    saf: SAFDimsPayload
    task: TaskScorecard = Field(default_factory=TaskScorecard)
    privacy: PrivacyScorecard = Field(default_factory=PrivacyScorecard)
    security: SecurityScorecard = Field(default_factory=SecurityScorecard)
    diagnostics: dict = Field(default_factory=dict)
    evaluator_version: str = "eval_v2.0.0"
    meta: dict = Field(default_factory=dict)

    # v2 runtime-provenance fields (Phase F / Task F4).
    gateway_invariant_passed: bool = True
    """Did the gateway's stage-1 invariants hold across the whole run?"""

    cassette_hash: str = ""
    """sha256 hex of the cassette.jsonl consumed by this run. Empty means
    no cassette was hashed (e.g., legacy v1 scorecards)."""

    live_or_replay: Literal["live", "replay"] = "live"
    """Source of the run: live gateway session or cassette replay."""

    episode_graph_id: str | None = None
    """Stable id of the episode graph this scorecard belongs to, or
    ``None`` for single-scenario runs."""

    @classmethod
    def from_v1_dict(cls, data: dict[str, Any]) -> "RunScorecard":
        """Load a v1 scorecard dict, filling v2 fields with defaults.

        The compatibility shim accepts any dict shaped like a v1
        scorecard: the new fields default to ``gateway_invariant_passed
        = True``, ``cassette_hash = ""``, ``live_or_replay = "live"``,
        and ``episode_graph_id = None``. Missing ``evaluator_version``
        is tagged ``eval_v1.0.0`` so aggregation code can tell which
        generation emitted the row.

        Any already-populated v2 field in ``data`` is preserved; this
        method is safe to call on a dict that already round-tripped
        through v2, making it idempotent for use as a generic loader.
        """

        filled = dict(data)
        filled.setdefault("gateway_invariant_passed", True)
        filled.setdefault("cassette_hash", "")
        filled.setdefault("live_or_replay", "live")
        filled.setdefault("episode_graph_id", None)
        filled.setdefault("evaluator_version", "eval_v1.0.0")
        return cls.model_validate(filled)


@dataclass
class EpisodeGraphScorecard:
    """Bundled result for a multi-episode evaluation (spec §4.7, Fix 3).

    Attributes:
        graph_id: Stable identifier for the episode graph. Matches the
            ``episode_graph_id`` stamped on each underlying
            :class:`RunScorecard`.
        per_episode: Ordered per-episode scorecards; index aligns with
            the episode order supplied to :class:`EpisodeGraphEvalRunner`.
        trajectory: Cumulative trajectory (Social Recall / Precision /
            TLR / CPR) indexed by episode. Same length as ``per_episode``.
        meta: Free-form provenance (model, condition, seed) shared
            across episodes in this graph.
    """

    graph_id: str
    per_episode: list[RunScorecard] = field(default_factory=list)
    trajectory: "CumulativeTrajectory | None" = None
    meta: dict[str, Any] = field(default_factory=dict)
