"""Live executor that wires Phase-5 scenarios through real LLM calls.

Two modes:

- ``"naturalization_only"`` (default): Run-Batch 1 contract -- call
  gpt-5.2 to produce a :class:`NaturalizationPatch`, score whether
  the patch validates, and return a :class:`ScenarioResult` whose
  scoring columns are all ``None`` except ``naturalization_success``.

- ``"full"``: Run-Batch 2+ contract -- after naturalization, build a
  :class:`Session` from the variant bundle directory, drive the
  generic gpt-4.1-mini agent loop, score ``evaluation_criteria``
  (canonical actions + must-say strings) for task success, run the
  four per-axis attack-success heuristics for the row's
  ``attack_mode``, and score the SAF 6-dimension card from the
  audit substrate.

The mode is auto-selected by the presence of an ``agent_client``:
when it is ``None``, the executor stays in naturalization-only
mode; when provided, it switches to full mode. Both modes share
the same naturalization stage so a R-B 2 substrate test can
reuse the existing naturalization fixtures.

Per-row failure isolation is preserved: any exception in the
agent loop, env-assertion scoring, attack scoring, or SAF scoring
is captured into ``ScenarioResult.error`` rather than aborting
the batch.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawsocialarena.audit.policy_catalog import PolicyCatalog
from clawsocialarena.gateway.session import Session
from clawsocialarena.generator.family_pack_skeleton import (
    build_family_pack_skeleton,
)
from clawsocialarena.generator.naturalization import (
    NaturalizationPatch,
    NaturalizationValidationError,
    run_naturalization,
)
from clawsocialarena.llm.openai_client import (
    JsonClient,
    OpenAIResponsesJsonClient,
)
from clawsocialarena.orchestrator.phase5_agent_loop import (
    AgentLoopResult,
    discover_tool_docs,
    discover_tool_schemas,
    run_agent_loop,
)
from clawsocialarena.orchestrator.phase5_attack_scoring import (
    AttackScoringInput,
    AttackScoringResult,
    score_attack_axes,
)
from clawsocialarena.orchestrator.phase5_env_assertions import (
    EnvAssertionResult,
    evaluate_evaluation_criteria,
)
from clawsocialarena.orchestrator.phase5_executor import ScenarioResult
from clawsocialarena.orchestrator.phase5_saf_bridge import (
    SAFBridgeResult,
    score_saf_from_session,
)
from clawsocialarena.scenario.models import (
    GovernanceManifest,
    GTBundle,
    ResourceManifest,
)
from clawsocialarena.types import ActionType, AuditCondition


PHASE5_DEFAULT_NATURALIZATION_MODEL = "gpt-5.2"
PHASE5_DEFAULT_AGENT_MODEL = "gpt-4.1-mini"
PHASE5_DEFAULT_MAX_TURNS = 8


@dataclass
class LiveScenarioExecutor:
    """Executor that calls real LLMs to drive a scenario end-to-end.

    Constructor parameters:

    - ``naturalization_model`` / ``agent_model``: model identifiers
      passed to the JsonClient. Default to the spec values
      (gpt-5.2 / gpt-4.1-mini).
    - ``max_turns``: per-scenario agent loop budget. Used by full
      mode; ignored in naturalization-only mode.
    - ``naturalization_client`` / ``agent_client``: pluggable
      :class:`JsonClient` instances. ``naturalization_client``
      defaults to :class:`OpenAIResponsesJsonClient` on first use.
      ``agent_client`` defaults to the same when ``mode="full"``;
      tests inject mock clients for both.
    - ``mode``: ``"naturalization_only"`` (R-B 1) or ``"full"``
      (R-B 2+). ``None`` (the default) auto-selects based on
      whether ``agent_client`` is provided.

    The executor instance is callable across many rows; clients
    and the audit-condition policy are held on the instance and
    reused across calls.
    """

    naturalization_model: str = PHASE5_DEFAULT_NATURALIZATION_MODEL
    agent_model: str = PHASE5_DEFAULT_AGENT_MODEL
    max_turns: int = PHASE5_DEFAULT_MAX_TURNS
    openai_api_key: str | None = None
    naturalization_client: JsonClient | None = None
    agent_client: JsonClient | None = None
    mode: str | None = None
    audit_condition: AuditCondition = AuditCondition.PASSIVE
    store_dir: Path | None = None      # v2 published-scenarios store
    run_dir: Path | None = None        # where per-run variants land

    def __post_init__(self) -> None:
        if self.mode is None:
            self.mode = (
                "full" if self.agent_client is not None
                else "naturalization_only"
            )

    def _resolve_naturalization_client(self) -> JsonClient:
        if self.naturalization_client is None:
            self.naturalization_client = OpenAIResponsesJsonClient()
        return self.naturalization_client

    def _resolve_agent_client(self) -> JsonClient:
        if self.agent_client is None:
            self.agent_client = OpenAIResponsesJsonClient()
        return self.agent_client

    def execute(
        self,
        *,
        row: dict[str, Any],
        base_dir: Path,
    ) -> ScenarioResult:
        """Drive one Phase-5 row through the configured pipeline.

        Supplementary rows (stratum != "main") raise
        :class:`NotImplementedError` because Run-Batch 5 supplies
        the supplementary materializers; the orchestrator's
        per-row try/except converts that into an errored row
        rather than aborting the batch.
        """
        stratum = row.get("stratum", "main")
        if stratum != "main":
            raise NotImplementedError(
                f"supplementary row stratum={stratum!r} is wired by "
                "Run-Batch 5; this executor only handles main-stratum rows."
            )

        started = time.monotonic()

        if self.store_dir is not None and self.run_dir is not None:
            # ----- Store-mode: skip runtime naturalization -----
            # The v2 store holds pre-naturalized bundles. Materialize the
            # per-run variant dir by copying from the store (applying the
            # stress-recipe overlay when attack_mode != "no_attacker").
            from clawsocialarena.attacks.runtime_overlay import (
                materialize_runtime_variant,
            )
            try:
                variant_dir = materialize_runtime_variant(
                    store_dir=self.store_dir,
                    base_id=str(row.get("base_id") or ""),
                    attack_mode=str(row.get("attack_mode") or "no_attacker"),
                    run_dir=self.run_dir,
                )
            except FileNotFoundError as exc:
                elapsed = time.monotonic() - started
                return _errored_result(
                    row=row,
                    started=started,
                    elapsed=elapsed,
                    error=f"store_lookup: {exc}",
                    naturalization_usage={},
                    stage="store_lookup",
                )

            variant_scenario_path = variant_dir / "scenario.json"
            if not variant_scenario_path.is_file():
                elapsed = time.monotonic() - started
                return _errored_result(
                    row=row,
                    started=started,
                    elapsed=elapsed,
                    error=f"store_mode: missing scenario.json at {variant_scenario_path}",
                    naturalization_usage={},
                    stage="store_lookup",
                )

            # Build a passthrough NaturalizationPatch (store is already
            # naturalized; no persona notes are injected at runtime).
            from clawsocialarena.generator.naturalization import (
                NaturalizationMetadata,
                NaturalizedScenarioPatch,
                NaturalizedWorldPatch,
                NaturalizationPatch,
            )
            from clawsocialarena.llm.costing import TokenUsage as _TokenUsage

            scenario_dict_raw = json.loads(
                variant_scenario_path.read_text(encoding="utf-8")
            )
            scenario_id_for_patch = str(
                scenario_dict_raw.get("scenario_id") or row.get("variant_id") or "store"
            )
            opening_msg = scenario_dict_raw.get("opening_message") or {}
            if isinstance(opening_msg, dict):
                opening_text = str(opening_msg.get("content") or "Proceed.")
            else:
                opening_text = str(opening_msg or "Proceed.")
            # Load persona notes from the store's personas/ dir so agents
            # run with the naturalized prose, not the bare scenario template.
            persona_dir = variant_dir / "personas"
            persona_notes_store: dict[str, str] = {}
            if persona_dir.is_dir():
                for agent in scenario_dict_raw.get("agents") or []:
                    agent_id = str(agent.get("agent_id") or "")
                    note_path = persona_dir / f"{agent_id}.system.md"
                    if note_path.is_file():
                        persona_notes_store[agent_id] = note_path.read_text(
                            encoding="utf-8"
                        )
            patch = NaturalizationPatch(
                scenario_id=scenario_id_for_patch,
                world_patch=NaturalizedWorldPatch(files={}, databases={}),
                scenario_patch=NaturalizedScenarioPatch(
                    opening_message=opening_text,
                    persona_notes=persona_notes_store,
                ),
                construction_metadata=NaturalizationMetadata(
                    naturalization_mode="store",
                    naturalization_model="gpt-5.2",
                    prompt_hash="sha256:store",
                    cache_key="sha256:store",
                ),
                usage=_TokenUsage(
                    model="gpt-5.2",
                    input_tokens=0,
                    cached_input_tokens=0,
                    output_tokens=0,
                ),
            )
            naturalization_usage_raw: dict[str, Any] = {}
            naturalization_usage = _adapt_usage_for_aggregator(
                naturalization_usage_raw
            )
            # Store-mode always runs full mode; naturalization_only is N/A.

        else:
            # ----- Legacy mode: runtime naturalization -----
            base_bundle_dir = _base_bundle_dir_for(row=row, base_dir=base_dir)
            try:
                variant_dir, variant_scenario_path = _resolve_variant_paths(
                    row=row, base_dir=base_dir
                )
            except FileNotFoundError as exc:
                elapsed = time.monotonic() - started
                return _errored_result(
                    row=row,
                    started=started,
                    elapsed=elapsed,
                    error=f"variant_paths: {exc}",
                    naturalization_usage={},
                    stage="resolve_paths",
                )

            # ----- Stage 1: naturalization (shared by both modes) -----
            try:
                patch = _naturalize_base_bundle(
                    client=self._resolve_naturalization_client(),
                    base_bundle_dir=base_bundle_dir,
                    row=row,
                    naturalization_model=self.naturalization_model,
                )
            except NaturalizationValidationError as exc:
                elapsed = time.monotonic() - started
                return _errored_result(
                    row=row,
                    started=started,
                    elapsed=elapsed,
                    error=f"NaturalizationValidationError: {exc}",
                    naturalization_usage=exc.usage.model_dump(),
                    stage="naturalization",
                )
            except Exception as exc:  # noqa: BLE001 -- isolate one row
                elapsed = time.monotonic() - started
                return _errored_result(
                    row=row,
                    started=started,
                    elapsed=elapsed,
                    error=f"{type(exc).__name__}: {exc}",
                    naturalization_usage={},
                    stage="naturalization",
                )

            naturalization_usage_raw = patch.usage.model_dump()
            naturalization_usage = _adapt_usage_for_aggregator(
                naturalization_usage_raw
            )

        if self.mode == "naturalization_only" and self.store_dir is None:
            elapsed = time.monotonic() - started
            return _naturalization_only_result(
                row=row,
                patch=patch,
                naturalization_usage=naturalization_usage,
                naturalization_usage_raw=naturalization_usage_raw,
                elapsed=elapsed,
            )

        # ----- Stage 2: build Session + run agent loop -----
        try:
            (
                session,
                scenario_dict,
                gt_bundle,
                evaluation_criteria,
                variant_metadata,
            ) = _materialize_session_for_full_mode(
                row=row,
                variant_dir=variant_dir,
                variant_scenario_path=variant_scenario_path,
                patch=patch,
                audit_condition=self.audit_condition,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            return _errored_result(
                row=row,
                started=started,
                elapsed=elapsed,
                error=f"session_build: {type(exc).__name__}: {exc}",
                naturalization_usage=naturalization_usage_raw,
                stage="session_build",
            )

        loop_result: AgentLoopResult
        try:
            tool_schemas = discover_tool_schemas(
                family_id=row.get("family_id"),
                tool_names=list(session.mcp_host.tools()),
            )
            attacker_peer = _resolve_attacker_peer(
                variant_metadata=variant_metadata,
                scenario=scenario_dict,
            )
            loop_result = asyncio.run(
                run_agent_loop(
                    session=session,
                    scenario=scenario_dict,
                    agent_client=self._resolve_agent_client(),
                    agent_model=self.agent_model,
                    max_turns=self._max_turns_for_row(row),
                    tool_schemas=tool_schemas,
                    evaluation_criteria=evaluation_criteria,
                    attacker_peer=attacker_peer,
                )
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            _close_session(session)
            return _errored_result(
                row=row,
                started=started,
                elapsed=elapsed,
                error=f"agent_loop: {type(exc).__name__}: {exc}",
                naturalization_usage=naturalization_usage_raw,
                stage="agent_loop",
            )

        # ----- Stage 3: scoring (env assertions, attack axes, SAF) -----
        try:
            action_log_records = (
                list(session.action_log.read_all())
                if session.action_log is not None
                else []
            )
            # Resolve the resources/ that actually carries post-run
            # state. Attack variants share the base bundle's resources
            # (see _read_resource_manifest), so walk up if the local
            # dir is empty.
            scoring_resources_dir = variant_dir / "resources"
            if not scoring_resources_dir.is_dir():
                parent_resources = variant_dir.parent.parent / "resources"
                if parent_resources.is_dir():
                    scoring_resources_dir = parent_resources
            env_result = evaluate_evaluation_criteria(
                gt_bundle=gt_bundle,
                action_log=action_log_records,
                outbound_messages=loop_result.messages,
                evaluation_criteria_override=evaluation_criteria,
                resources_dir=scoring_resources_dir,
                family_id=str(row.get("family_id") or ""),
            )
            attack_input = AttackScoringInput(
                row=row,
                variant_metadata=variant_metadata,
                gt_bundle=gt_bundle,
                action_log=action_log_records,
                outbound_messages=loop_result.messages,
                canonical_task_success=env_result.task_success,
                hit_turn_cap=loop_result.hit_turn_cap,
                canonical_actions_dispatched=env_result.canonical_actions_dispatched,
                required_canonical_tools=env_result.required_canonical_tools,
                family_id=str(row.get("family_id") or ""),
            )
            attack_result = score_attack_axes(attack_input)
            saf_result = score_saf_from_session(
                session=session,
                gt=gt_bundle,
                catalog=PolicyCatalog(),
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            _close_session(session)
            return _errored_result(
                row=row,
                started=started,
                elapsed=elapsed,
                error=f"scoring: {type(exc).__name__}: {exc}",
                naturalization_usage=naturalization_usage_raw,
                stage="scoring",
                simulation_usage=_extract_simulation_usage(loop_result),
                turn_count=loop_result.turn_count,
                hit_turn_cap=loop_result.hit_turn_cap,
            )

        tool_call_count = sum(
            1
            for record in action_log_records
            if record.action_type == ActionType.TOOL_CALL
        )
        _close_session(session)
        elapsed = time.monotonic() - started
        return _assemble_full_result(
            row=row,
            patch=patch,
            naturalization_usage=naturalization_usage,
            naturalization_usage_raw=naturalization_usage_raw,
            loop_result=loop_result,
            env_result=env_result,
            attack_result=attack_result,
            saf_result=saf_result,
            elapsed=elapsed,
            tool_call_count=tool_call_count,
        )

    def _max_turns_for_row(self, row: dict[str, Any]) -> int:
        """Resolve the row's max_turns from the manifest, falling back to
        the executor default.
        """
        candidate = row.get("max_turns")
        if isinstance(candidate, int) and candidate > 0:
            return candidate
        return self.max_turns


# ---------- Naturalization helpers ------------------------------------


def _naturalize_base_bundle(
    *,
    client: JsonClient,
    base_bundle_dir: Path,
    row: dict[str, Any],
    naturalization_model: str,
) -> NaturalizationPatch:
    skeleton = build_family_pack_skeleton(
        family_id=row["family_id"],
        bundle_dir=base_bundle_dir,
        cell_id=row.get("cell_id"),
        index_row=row,
    )
    return run_naturalization(
        client=client,
        scenario_id=skeleton.payload["scenario"].get(
            "scenario_id", row["variant_id"]
        ),
        skeleton_payload=skeleton.payload,
        model=naturalization_model,
    )


# ---------- Session materialization (full mode) -----------------------


def _materialize_session_for_full_mode(
    *,
    row: dict[str, Any],
    variant_dir: Path,
    variant_scenario_path: Path,
    patch: NaturalizationPatch,
    audit_condition: AuditCondition,
) -> tuple[Session, dict[str, Any], GTBundle, dict[str, Any], dict[str, Any]]:
    """Build a :class:`Session` for the variant + apply the patch.

    Returns ``(session, patched_scenario_dict, gt_bundle,
    evaluation_criteria, variant_metadata)``. The
    ``evaluation_criteria`` dict is the raw JSON block extracted
    from ``scenario.gt.json``; :class:`GTBundle` does not surface
    it as a Pydantic field, so the executor passes it through to
    :func:`evaluate_evaluation_criteria` as
    ``evaluation_criteria_override``.

    The session is built with :data:`AuditCondition.PASSIVE` so the
    action/shadow logs accrue records but no enforcement-side
    rewrites mask attacker behavior. The SQLite db is materialized
    under ``variant_dir / "phase5_session"``.

    The patched scenario dict is what the agent loop receives:
    the variant's on-disk ``scenario.json`` with the naturalized
    ``persona_notes`` applied to each agent's
    ``system_prompt_template``. The on-disk ``opening_message``
    is left unchanged because for attack variants it already
    contains the injected payload; rewriting it would silently
    drop the attack delivery.
    """
    scenario_dict = json.loads(
        variant_scenario_path.read_text(encoding="utf-8")
    )
    persona_notes = dict(patch.scenario_patch.persona_notes or {})
    if persona_notes:
        for agent in scenario_dict.get("agents") or []:
            agent_id = agent.get("agent_id")
            note = persona_notes.get(agent_id)
            if isinstance(note, str) and note.strip():
                base = str(agent.get("system_prompt_template") or "")
                agent["system_prompt_template"] = (
                    f"{base}\n\n[Persona note]\n{note}".strip()
                )

    gt_path = variant_dir / "scenario.gt.json"
    if not gt_path.is_file():
        # Attack variants live in <base>/attack_variants/<mode>/.
        # The GT bundle stays at <base>/scenario.gt.json so we walk
        # up to find it.
        candidate = variant_dir.parent.parent / "scenario.gt.json"
        if candidate.is_file():
            gt_path = candidate
    gt_raw = json.loads(gt_path.read_text(encoding="utf-8"))
    gt_bundle = _build_lenient_gt_bundle(gt_raw)
    evaluation_criteria = (
        dict(gt_raw["evaluation_criteria"])
        if isinstance(gt_raw, dict) and isinstance(
            gt_raw.get("evaluation_criteria"), dict
        )
        else {}
    )

    governance_manifest = _read_governance_manifest(variant_dir)
    resource_root, resource_manifest = _read_resource_manifest(variant_dir)
    family_pack_context = _read_family_pack_context(variant_dir)

    work_dir = variant_dir / "phase5_session"
    work_dir.mkdir(parents=True, exist_ok=True)
    db_path = work_dir / "session.db"
    # Clean any leftover session artifacts from prior runs against
    # this scaffold. Without this, ``Session.build`` opens the
    # existing sqlite files and ``ActionLog.__init__`` re-uses the
    # schema in place, which means a prior run's shadow log keeps
    # appending across reruns. That was the source of Codex's R-B 2
    # rerun recoverability=0.64 finding: shadow had stale records the
    # current run's primary log did not, so the SAF scorer compared
    # apples (prior run shadow) to oranges (current run primary).
    for residue in (
        db_path,
        work_dir / "session.shadow.db",
        work_dir / "cassette.jsonl",
    ):
        if residue.is_file():
            residue.unlink()
    # Restore mutable resource state from the per-scaffold snapshot
    # so each scenario rerun starts from the same seed state. Without
    # this, ``proposals.citations`` / ``orders.status`` /
    # ``reservations.committed_change`` / etc. accumulate hallucinated
    # rows and partial mutations across reruns, which fed
    # ``get_proposal_status`` confusing observations and made the
    # canonical task untestable. The snapshot lives at
    # ``<variant_dir>/resources_initial`` and is captured once by the
    # scaffold generator (or by ``scripts/freshen_phase5_scaffolds.py``
    # for legacy scaffolds).
    _restore_resources_from_snapshot(variant_dir)

    scenario_id = str(scenario_dict.get("scenario_id") or row["variant_id"])
    session = Session.build(
        scenario_id=scenario_id,
        condition=audit_condition,
        db_path=db_path,
        phase_schedule=gt_bundle.phase_schedule or None,
        work_dir=work_dir,
        hooks=None,
        governance_manifest=governance_manifest,
        resource_root=resource_root,
        resource_manifest=resource_manifest,
        family_id=row["family_id"],
        family_pack_context=family_pack_context,
    )

    variant_metadata = _read_variant_metadata(variant_dir, row)
    return (
        session,
        scenario_dict,
        gt_bundle,
        evaluation_criteria,
        variant_metadata,
    )


def _build_lenient_gt_bundle(raw: dict[str, Any]) -> GTBundle:
    """Load a Phase-5 GT bundle without strict Pydantic validation.

    Phase-5 generated bundles use a thinner schema than the v1
    fixtures :class:`GTBundle` was designed for: resource entries
    skip ``allowed_operations`` and ``construction_manifest``
    omits several required fields. The substrate code only reads
    a handful of attributes (canonical_action_stream, policies,
    phase_schedule, mcp_tool_manifest, resource_manifest,
    governance_manifest, attribution_dag, integrity_requirements,
    terminal_predicate, invariants), so we use
    :meth:`GTBundle.model_construct` to populate those attributes
    without running the strict validators. Sub-models that the
    scorers DO access strictly (governance_manifest entries,
    resource_manifest entries) get a best-effort parse with safe
    defaults filled in.
    """
    governance_manifest = _coerce_governance_manifest(
        raw.get("governance_manifest")
    )
    resource_manifest = _coerce_resource_manifest(raw.get("resource_manifest"))
    mcp_tool_manifest = _coerce_mcp_tool_manifest(raw.get("mcp_tool_manifest"))
    return GTBundle.model_construct(
        scenario_id=str(raw.get("scenario_id") or ""),
        canonical_action_stream=list(raw.get("canonical_action_stream") or []),
        phase_schedule=list(raw.get("phase_schedule") or []),
        policies=dict(raw.get("policies") or {}),
        attribution_dag=dict(raw.get("attribution_dag") or {}),
        integrity_requirements=dict(raw.get("integrity_requirements") or {}),
        terminal_predicate=dict(raw.get("terminal_predicate") or {"type": "none"}),
        invariants=dict(raw.get("invariants") or {}),
        attack_plan=raw.get("attack_plan"),
        mcp_tool_manifest=mcp_tool_manifest,
        persona_manifest={},
        governance_manifest=governance_manifest,
        resource_manifest=resource_manifest,
        construction_manifest=None,
    )


def _coerce_governance_manifest(
    raw: dict[str, Any] | None,
) -> GovernanceManifest | None:
    if not isinstance(raw, dict):
        return None
    try:
        return GovernanceManifest.model_validate(raw)
    except Exception:  # noqa: BLE001
        # Strict validation failed; the substrate only needs
        # ``governed_actions`` to map mutating tools, so fall
        # back to a hand-built minimal manifest with empty maps.
        return GovernanceManifest.model_construct(
            owners={},
            identities={},
            authorization_scopes={},
            approval_mandates={},
            escalation_rules={},
            governed_actions={},
        )


def _coerce_resource_manifest(
    raw: dict[str, Any] | None,
) -> ResourceManifest | None:
    if not isinstance(raw, dict):
        return None
    try:
        return ResourceManifest.model_validate(raw)
    except Exception:  # noqa: BLE001
        from clawsocialarena.scenario.models import (
            ResourceAccessRule,
            ResourceEntry,
        )
        resources_raw = raw.get("resources") or {}
        resources: dict[str, ResourceEntry] = {}
        for resource_id, entry in resources_raw.items():
            if not isinstance(entry, dict):
                continue
            try:
                resources[str(resource_id)] = ResourceEntry.model_validate(
                    {
                        **entry,
                        "allowed_operations": entry.get("allowed_operations")
                        or [{"identity_id": "anyone", "operations": ["read"]}],
                    }
                )
            except Exception:  # noqa: BLE001
                # Drop unparsable entries silently; substrate scorers
                # tolerate an empty resource_manifest.
                continue
        return ResourceManifest.model_construct(resources=resources)


def _coerce_mcp_tool_manifest(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    from clawsocialarena.scenario.models import McpToolSpec

    out: dict[str, Any] = {}
    for tool_name, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        try:
            out[str(tool_name)] = McpToolSpec.model_validate(spec)
        except Exception:  # noqa: BLE001
            out[str(tool_name)] = McpToolSpec.model_construct(
                input_schema=spec.get("schema", {}),
                audit_class=str(spec.get("audit_class", "read_only")),
            )
    return out


def _read_governance_manifest(
    variant_dir: Path,
) -> GovernanceManifest | None:
    path = variant_dir / "governance" / "manifest.json"
    if not path.is_file():
        # Attack variants store governance at the base bundle level.
        candidate = variant_dir.parent.parent / "governance" / "manifest.json"
        if candidate.is_file():
            path = candidate
        else:
            return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return GovernanceManifest.model_validate(raw)


def _read_resource_manifest(
    variant_dir: Path,
) -> tuple[Path | None, ResourceManifest | None]:
    """Resolve ``(resource_root, resource_manifest)`` for a Phase-5 bundle.

    Returns ``resource_root`` whenever a ``resources/`` directory
    exists (under the variant OR the base bundle), even if no
    ``manifest.json`` is present. The root path is what
    ``Session.register_family_pack_tools`` needs to wire its MCP
    handlers; the manifest is only used for the optional
    resource-access logging layer. Conflating the two caused R-B 2
    smoke runs to leave every family-pack tool unregistered for
    bundles whose generator did not emit a ``manifest.json``
    (notably wildclaw_social, where dispatch then returned
    ``Available tools: []``).
    """
    resources_dir = variant_dir / "resources"
    if not resources_dir.is_dir():
        candidate_dir = variant_dir.parent.parent / "resources"
        if candidate_dir.is_dir():
            resources_dir = candidate_dir
        else:
            return None, None
    manifest_path = resources_dir / "manifest.json"
    if not manifest_path.is_file():
        # Resource root exists but no manifest -- registration of
        # the access-logging tools is skipped, but the family-pack
        # handler registration in Session.build still gets the
        # ``resource_root`` it needs to wire the canonical tools.
        return resources_dir, None
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return resources_dir, ResourceManifest.model_validate(raw)


def _read_family_pack_context(variant_dir: Path) -> dict[str, Any] | None:
    path = variant_dir / "family_pack_context.json"
    if not path.is_file():
        candidate = variant_dir.parent.parent / "family_pack_context.json"
        if candidate.is_file():
            path = candidate
        else:
            return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else None


def _read_variant_metadata(
    variant_dir: Path, row: dict[str, Any]
) -> dict[str, Any]:
    """Load the per-variant sidecar with payload_text / target_agent_id.

    Baseline rows (no_attacker) do not have a sidecar; we synthesize
    a stub so the attack-scoring code can treat the inputs uniformly
    (it will short-circuit on ``attack_mode == 'no_attacker'`` before
    touching ``payload_text``).
    """
    if row.get("attack_mode") == "no_attacker":
        return {"attack_mode": "no_attacker", "payload_text": ""}
    path = variant_dir / "phase5_variant_metadata.json"
    if not path.is_file():
        return {"attack_mode": row.get("attack_mode"), "payload_text": ""}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _resolve_attacker_peer(
    *,
    variant_metadata: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any] | None:
    """Build the ``attacker_peer`` dict for adaptive stress recipes.

    Returns None when the variant does not declare an adaptive
    attacker peer (i.e., for standard / static-stress recipes, or
    for baseline rows). For adaptive recipes (privacy /
    collaboration stress), the variant's
    ``phase5_variant_metadata.json`` carries:

        attack.requires_runtime_peer: true
        attack.attacker_peer_id: "<peer agent_id>"
        attack.attacker_peer_prompt: "<peer system prompt>"
        attack.attacker_peer_max_turns: int | null
        attack.target_agent_id: "<focal agent_id>"

    Only adaptive recipes that pass schema validation produce a
    non-None return value; missing fields downgrade silently to None
    so the loop runs as if the recipe were static.
    """
    attack = (variant_metadata or {}).get("attack") or {}
    if not attack.get("requires_runtime_peer"):
        return None
    peer_id = str(attack.get("attacker_peer_id") or "")
    target_id = str(attack.get("target_agent_id") or "")
    prompt = str(attack.get("attacker_peer_prompt") or "")
    if not (peer_id and target_id and prompt):
        return None
    # Sanity: the target must be a real focal agent in the loop. If
    # not, the peer's outbound has nowhere to land and the recipe
    # downgrades to a no-op.
    focal_ids = {
        str(a.get("agent_id") or "") for a in (scenario.get("agents") or [])
    }
    if target_id not in focal_ids:
        return None
    max_turns_raw = attack.get("attacker_peer_max_turns")
    return {
        "attacker_peer_id": peer_id,
        "target_agent_id": target_id,
        "system_prompt": prompt,
        "max_turns": (
            int(max_turns_raw) if max_turns_raw is not None else None
        ),
    }


def _restore_resources_from_snapshot(variant_dir: Path) -> None:
    """Restore the mutable per-scaffold resource state from the
    ``resources_initial/`` snapshot taken at scaffold generation.

    Each family-pack tool handler reads from and writes to per-user
    sqlite databases under ``variant_dir/resources/``. The mutations
    (proposals filled, orders shipped, lines roaming-toggled,
    meetings confirmed, citations recorded) persist across runs
    because the schema is created with ``IF NOT EXISTS`` and never
    truncated. Without restoring the seed state, every rerun starts
    on top of the prior run's mutations and the canonical task
    becomes harder to score.

    Contract: if ``resources_initial/`` exists, mirror it onto
    ``resources/`` (destructive: deletes any prior ``resources/``
    first to drop accumulated SQLite WAL fragments and pollution).
    If the snapshot is missing -- typical for scaffolds generated
    before this commit -- the call is a no-op and the runtime keeps
    the same behavior as before. ``scripts/freshen_phase5_scaffolds.py``
    regenerates the snapshot for legacy scaffolds.
    """
    # Attack variants live two levels under the base bundle (e.g.
    # ``CD-A-marble_research/task1/tier1/attack_variants/collaboration/``)
    # and share the base bundle's ``resources/`` and
    # ``resources_initial/``. Walk up if the per-variant snapshot is
    # missing so the restore still resets the shared state before an
    # attack-variant run.
    snapshot = variant_dir / "resources_initial"
    target = variant_dir / "resources"
    if not snapshot.is_dir():
        parent_snapshot = variant_dir.parent.parent / "resources_initial"
        if not parent_snapshot.is_dir():
            return
        snapshot = parent_snapshot
        target = variant_dir.parent.parent / "resources"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(snapshot, target)


def _close_session(session: Session) -> None:
    """Close any session-owned resources (cassette, logs) best-effort.

    Sessions hold SQLite handles in their logs. We don't currently
    expose a single ``close()``; the logs are flushed on each write
    so dropping the reference is enough, but we still tear down the
    cassette explicitly so its file handle does not linger.
    """
    if session.cassette is not None:
        with contextlib.suppress(Exception):
            session.cassette.close()


def _extract_simulation_usage(loop_result: AgentLoopResult) -> dict[str, int]:
    usage = loop_result.total_usage
    if usage is None:
        return {}
    return {
        "prompt_tokens": int(usage.input_tokens or 0),
        "completion_tokens": int(usage.output_tokens or 0),
        "total_tokens": int(
            (usage.input_tokens or 0) + (usage.output_tokens or 0)
        ),
    }


# ---------- Result assembly -------------------------------------------


def _naturalization_only_result(
    *,
    row: dict[str, Any],
    patch: NaturalizationPatch,
    naturalization_usage: dict[str, int],
    naturalization_usage_raw: dict[str, Any],
    elapsed: float,
) -> ScenarioResult:
    return ScenarioResult(
        variant_id=row["variant_id"],
        base_scenario_id=row["base_scenario_id"],
        cell_id=row["cell_id"],
        family_id=row["family_id"],
        task_index=int(row["task_index"]),
        tier_index=int(v) if (v := row.get("tier_index")) is not None else None,
        attack_mode=row["attack_mode"],
        attack_recipe=row.get("attack_recipe"),
        naturalization_success=True,
        task_success=None,
        attack_success=None,
        governance_violation=None,
        privacy_violation=None,
        compliance_ok=None,
        turn_count=0,
        elapsed_seconds=round(elapsed, 3),
        naturalization_usage=naturalization_usage,
        simulation_usage={},
        error=None,
        transcript_path=None,
        extra={
            "naturalization_metadata": dict(
                patch.construction_metadata.model_dump()
                if hasattr(patch.construction_metadata, "model_dump")
                else patch.construction_metadata
            ),
            "naturalized_scenario_id": patch.scenario_id,
            "raw_usage": naturalization_usage_raw,
            "run_batch_1_scope": "naturalization_only",
        },
    )


def _assemble_full_result(
    *,
    row: dict[str, Any],
    patch: NaturalizationPatch,
    naturalization_usage: dict[str, int],
    naturalization_usage_raw: dict[str, Any],
    loop_result: AgentLoopResult,
    env_result: EnvAssertionResult,
    attack_result: AttackScoringResult,
    saf_result: SAFBridgeResult,
    elapsed: float,
    tool_call_count: int = 0,
) -> ScenarioResult:
    simulation_usage = _extract_simulation_usage(loop_result)
    extra: dict[str, Any] = {
        "naturalization_metadata": dict(
            patch.construction_metadata.model_dump()
            if hasattr(patch.construction_metadata, "model_dump")
            else patch.construction_metadata
        ),
        "naturalized_scenario_id": patch.scenario_id,
        "raw_usage": naturalization_usage_raw,
        "agent_loop": {
            "turn_count": loop_result.turn_count,
            "hit_turn_cap": loop_result.hit_turn_cap,
            "done_agents": list(loop_result.done_agents),
            "message_count": len(loop_result.messages),
        },
        "env_assertions": {
            "action_passes": env_result.action_passes,
            "action_failures": env_result.action_failures,
            "predicate_passes": env_result.predicate_passes,
            "predicate_failures": env_result.predicate_failures,
            "diagnostics": env_result.diagnostics,
        },
        "communicate_info_metric": {
            "passes": env_result.communicate_passes,
            "failures": env_result.communicate_failures,
            "gates_task_success": False,
        },
        "attack_diagnostics": attack_result.diagnostics,
        "saf_diagnostics": {
            "applicable_dims": saf_result.applicable_dims,
            "not_applicable_dims": saf_result.not_applicable_dims,
            "passes": saf_result.passes,
        },
        "run_batch_2_scope": "full_simulation",
    }

    return ScenarioResult(
        variant_id=row.get("variant_id", ""),
        base_scenario_id=row.get("base_scenario_id", ""),
        cell_id=row.get("cell_id", ""),
        family_id=row.get("family_id", ""),
        task_index=int(row.get("task_index", 0)),
        tier_index=int(v) if (v := row.get("tier_index")) is not None else None,
        attack_mode=row.get("attack_mode", "no_attacker"),
        attack_recipe=row.get("attack_recipe"),
        naturalization_success=True,
        task_success=env_result.task_success,
        attack_success_collaboration=attack_result.attack_success_collaboration,
        attack_success_security=attack_result.attack_success_security,
        attack_success_privacy=attack_result.attack_success_privacy,
        attack_success_governance=attack_result.attack_success_governance,
        attack_success=attack_result.attack_success_aggregate,
        governance_violation=attack_result.governance_violation,
        privacy_violation=attack_result.privacy_violation,
        compliance_ok=attack_result.compliance_ok,
        saf_recoverability=saf_result.recoverability,
        saf_policy_checkability=saf_result.policy_checkability,
        saf_attribution=saf_result.attribution,
        saf_evidence_integrity=saf_result.evidence_integrity,
        saf_phase_scoped_policy=saf_result.phase_scoped_policy,
        saf_identity_governance=saf_result.identity_governance,
        saf_overall=saf_result.overall,
        turn_count=loop_result.turn_count,
        hit_turn_cap=loop_result.hit_turn_cap,
        tool_call_count=tool_call_count,
        elapsed_seconds=round(elapsed, 3),
        naturalization_usage=naturalization_usage,
        simulation_usage=simulation_usage,
        error=None,
        transcript_path=None,
        extra=extra,
    )


# ---------- Helpers shared with the naturalization-only path ----------


def _resolve_variant_paths(
    *, row: dict[str, Any], base_dir: Path
) -> tuple[Path, Path]:
    variant_dir = (base_dir / row["bundle_dir"]).resolve()
    scenario_path = variant_dir / "scenario.json"
    if not scenario_path.is_file():
        raise FileNotFoundError(
            f"missing scenario.json for variant {row.get('variant_id')!r} "
            f"at {scenario_path}"
        )
    return variant_dir, scenario_path


def _base_bundle_dir_for(*, row: dict[str, Any], base_dir: Path) -> Path:
    """Map an attack-variant row to its underlying base-bundle dir.

    For baseline rows (``attack_mode == 'no_attacker'``) the bundle
    dir IS the base bundle dir. For attack rows, the bundle dir is
    ``<base>/attack_variants/<mode>/``; the base sits two parents
    up (``<base>`` itself).
    """
    bundle_dir = (base_dir / row["bundle_dir"]).resolve()
    if row.get("attack_mode") == "no_attacker":
        return bundle_dir
    parent = bundle_dir.parent
    grandparent = parent.parent
    if parent.name in {"attack_variants"} or grandparent.name in {
        "attack_variants"
    }:
        return grandparent
    return bundle_dir


def _adapt_usage_for_aggregator(usage_dump: dict[str, Any]) -> dict[str, int]:
    input_tokens = int(usage_dump.get("input_tokens", 0))
    output_tokens = int(usage_dump.get("output_tokens", 0))
    return {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _errored_result(
    *,
    row: dict[str, Any],
    started: float,
    elapsed: float,
    error: str,
    naturalization_usage: dict[str, Any],
    stage: str = "unknown",
    simulation_usage: dict[str, int] | None = None,
    turn_count: int = 0,
    hit_turn_cap: bool = False,
) -> ScenarioResult:
    usage_for_aggregator = _adapt_usage_for_aggregator(
        naturalization_usage if naturalization_usage else {}
    )
    return ScenarioResult(
        variant_id=row.get("variant_id", ""),
        base_scenario_id=row.get("base_scenario_id", ""),
        cell_id=row.get("cell_id", ""),
        family_id=row.get("family_id", ""),
        task_index=int(row.get("task_index", 0)),
        tier_index=int(v) if (v := row.get("tier_index")) is not None else None,
        attack_mode=row.get("attack_mode", "no_attacker"),
        attack_recipe=row.get("attack_recipe"),
        naturalization_success=False if stage == "naturalization" else None,
        task_success=None,
        attack_success=None,
        governance_violation=None,
        privacy_violation=None,
        compliance_ok=None,
        turn_count=turn_count,
        hit_turn_cap=hit_turn_cap,
        elapsed_seconds=round(elapsed, 3),
        naturalization_usage=usage_for_aggregator,
        simulation_usage=dict(simulation_usage or {}),
        error=error,
        transcript_path=None,
        extra={
            "phase5_failure_stage": stage,
            "raw_usage": dict(naturalization_usage)
            if naturalization_usage
            else {},
        },
    )


__all__ = [
    "LiveScenarioExecutor",
    "PHASE5_DEFAULT_AGENT_MODEL",
    "PHASE5_DEFAULT_MAX_TURNS",
    "PHASE5_DEFAULT_NATURALIZATION_MODEL",
]
