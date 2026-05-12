"""Generic task-success evaluator for the Phase-5 pilot.

A Phase-5 GT bundle's ``evaluation_criteria`` block carries three
distinct check kinds, after the Stream A redesign:

1. ``actions``: a list of ``{agent_id, tool_name, compare_args}``
   entries the agent loop must dispatch. ``compare_args`` is a
   list of argument keys; the values supplied at dispatch time
   must match the values the canonical action stream baked in.
2. ``env_assertions``: a list of ``{predicate, args}`` checks
   evaluated against the post-run world state (resource sqlite
   dbs). Predicate names resolve through
   ``clawsocialarena.eval.predicates.<family_id>.PREDICATE_REGISTRY``.
   This is the tau2-bench-style scoring path: predicates inspect
   the post-run DB state directly, replacing the earlier R-B 2
   ``must_say`` substring surrogate.
3. ``communicate_info``: a list of ``{agent_id, must_say}``
   entries requiring substring matches against that agent's
   outbound messages. Retained as a LOGGED METRIC ONLY (does NOT
   gate ``task_success``); use it for analyzing whether agents
   announce completion socially without forcing them to.

``task_success`` formula::

    task_success = action_passes_ok AND predicates_ok

where ``predicates_ok = (predicate_failures == [] AND
predicate_passes != [])`` when env_assertions are declared, or
``True`` when none are declared (some bundles only check actions).

``communicate_info`` is captured but never gates the verdict.
"""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clawsocialarena.eval.env_state_builder import build_env_state
from clawsocialarena.eval.predicates.types import EnvState
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.types import ActionRecord, ActionType


_FAMILY_PREDICATE_MODULE: dict[str, str] = {
    "marble_research": "clawsocialarena.eval.predicates.marble_research",
    "marble_bargaining": "clawsocialarena.eval.predicates.marble_bargaining",
    "tau2_airline": "clawsocialarena.eval.predicates.tau2_airline",
    "tau2_retail": "clawsocialarena.eval.predicates.tau2_retail",
    "tau2_telecom": "clawsocialarena.eval.predicates.tau2_telecom",
    "wildclaw_social": "clawsocialarena.eval.predicates.wildclaw_social",
}


def _resolve_predicate_registry(family_id: str | None) -> dict[str, Any]:
    """Import ``PREDICATE_REGISTRY`` for ``family_id``. Empty dict on
    unknown / import error so the evaluator can record per-entry
    failures without crashing the whole row.
    """
    if not family_id or family_id not in _FAMILY_PREDICATE_MODULE:
        return {}
    try:
        module = importlib.import_module(_FAMILY_PREDICATE_MODULE[family_id])
    except Exception:  # noqa: BLE001
        return {}
    return getattr(module, "PREDICATE_REGISTRY", {}) or {}


@dataclass
class EnvAssertionResult:
    """Verdict for one ``evaluation_criteria`` evaluation."""

    task_success: bool
    canonical_actions_dispatched: list[str] = field(default_factory=list)
    """Tool names actually dispatched in the agent loop. Used by
    the collaboration-axis attack scorer to detect "agents never
    even tried the canonical task"."""

    required_canonical_tools: list[str] = field(default_factory=list)
    """Tool names the bundle declares as canonical via
    ``evaluation_criteria.actions[*].tool_name``. Surfaced
    separately from ``gt.canonical_action_stream`` (which Phase-5
    bundles leave empty); the collaboration-axis attack scorer
    needs an authoritative list of required tools regardless of
    which schema location the generator filled in.
    """

    action_passes: list[dict[str, Any]] = field(default_factory=list)
    action_failures: list[dict[str, Any]] = field(default_factory=list)

    # ``communicate_info`` results are logged but NEVER gate
    # ``task_success`` in the Stream A design. Reported as a social
    # metric in the result row's ``extra.communicate_info_metric``.
    communicate_passes: list[dict[str, Any]] = field(default_factory=list)
    communicate_failures: list[dict[str, Any]] = field(default_factory=list)

    # Predicate evaluation (tau2-bench-style) replaces the prior
    # must_say surrogate. Each entry is
    # ``{"predicate": "<name>", "args": {...}, "reason": "<reason>",
    #   "diagnostics": {...}}``. ``predicate_failures`` is non-empty
    # iff at least one predicate returned ``passed=False`` OR the
    # predicate was declared but could not be resolved.
    predicate_passes: list[dict[str, Any]] = field(default_factory=list)
    predicate_failures: list[dict[str, Any]] = field(default_factory=list)

    diagnostics: dict[str, Any] = field(default_factory=dict)


def evaluate_evaluation_criteria(
    *,
    gt_bundle: GTBundle,
    action_log: list[ActionRecord],
    outbound_messages: list[dict[str, Any]],
    evaluation_criteria_override: dict[str, Any] | None = None,
    resources_dir: Path | str | None = None,
    family_id: str | None = None,
) -> EnvAssertionResult:
    """Score the bundle's ``evaluation_criteria`` against a trajectory.

    Returns an :class:`EnvAssertionResult` whose ``task_success``
    is ``True`` iff every required action was dispatched with
    matching arg identities AND every ``must_say`` string landed
    in the right agent's outbound stream.

    The pydantic :class:`GTBundle` model does not declare
    ``evaluation_criteria`` as a field, so the family-pack loaders
    attach it on the raw JSON dict outside the validator's view.
    Callers that already hold the raw dict can pass
    ``evaluation_criteria_override`` to skip the extraction step
    (this is how :func:`evaluate_from_bundle_dir` and the live
    executor wire it through).
    """
    if evaluation_criteria_override is not None:
        criteria = dict(evaluation_criteria_override)
    else:
        criteria = _read_evaluation_criteria(gt_bundle)
    action_checks = list(criteria.get("actions") or [])
    communicate_checks = list(criteria.get("communicate_info") or [])
    env_assertions = list(criteria.get("env_assertions") or [])

    # Index tool calls by agent_id + tool_name for fast lookup,
    # but ONLY when a matching TOOL_OBSERVATION_RETURN follows
    # (i.e., the mcp_host dispatch did not raise). The agent loop
    # records the TOOL_CALL row before dispatch, so a logged call
    # without an observation indicates an MCP failure. Counting
    # those would let task_success fire on rows where the canonical
    # tool errored.
    pending_calls: dict[str, dict[str, Any]] = {}
    tool_calls_by_agent: dict[tuple[str, str], list[dict[str, Any]]] = {}
    canonical_tools_dispatched: list[str] = []
    for record in action_log:
        if record.action_type == ActionType.TOOL_CALL:
            pending_calls[record.action_id] = {
                "agent_id": record.agent_id,
                "tool_name": str(record.payload.get("tool_name") or ""),
                "arguments": dict(record.payload.get("arguments") or {}),
            }
            continue
        if record.action_type != ActionType.TOOL_OBSERVATION_RETURN:
            continue
        # Match the observation back to the prior TOOL_CALL row.
        # The observation's payload carries the originating
        # action_id under either ``tool_call_action_id`` (preferred)
        # or ``call_action_id`` (legacy); fall back to popping the
        # most recent pending call if neither is present.
        ref_id = record.payload.get(
            "tool_call_action_id"
        ) or record.payload.get("call_action_id")
        call_meta = None
        if isinstance(ref_id, str) and ref_id in pending_calls:
            call_meta = pending_calls.pop(ref_id)
        elif pending_calls:
            last_id = next(reversed(pending_calls))
            call_meta = pending_calls.pop(last_id)
        if call_meta is None:
            continue
        tool_name = call_meta["tool_name"]
        if not tool_name:
            continue
        # Skip observations marked as errored. The agent loop
        # stores the handler's response as a JSON-stringified
        # ``observation`` field inside the payload, e.g.
        # ``{"observation": "{\\"ok\\": false, \\"error\\": ...}", ...}``,
        # so we have to look inside that string when deciding
        # whether the dispatch actually committed. Synthetic
        # failure observations written by the dispatch-feedback
        # patch carry ``{"ok": false, "error": "..."}`` and must
        # NOT credit the canonical action.
        if _observation_indicates_failure(record.payload):
            continue
        key = (call_meta["agent_id"], tool_name)
        tool_calls_by_agent.setdefault(key, []).append(call_meta["arguments"])
        if tool_name not in canonical_tools_dispatched:
            canonical_tools_dispatched.append(tool_name)

    canonical_action_stream = list(gt_bundle.canonical_action_stream or [])
    canonical_args_index = _index_canonical_args(canonical_action_stream)

    action_passes: list[dict[str, Any]] = []
    action_failures: list[dict[str, Any]] = []
    for check in action_checks:
        agent_id = str(check.get("agent_id") or "")
        tool_name = str(check.get("tool_name") or "")
        compare_args = list(check.get("compare_args") or [])
        observed_calls = tool_calls_by_agent.get((agent_id, tool_name), [])
        if not observed_calls:
            action_failures.append(
                {
                    "agent_id": agent_id,
                    "tool_name": tool_name,
                    "reason": "no_call_dispatched",
                }
            )
            continue
        expected_args = canonical_args_index.get((agent_id, tool_name)) or {}
        match_found = False
        first_mismatch: dict[str, Any] | None = None
        for observed in observed_calls:
            mismatched = _arg_mismatch(
                observed=observed,
                expected=expected_args,
                compare_keys=compare_args,
            )
            if not mismatched:
                match_found = True
                break
            if first_mismatch is None:
                first_mismatch = mismatched
        if match_found:
            action_passes.append(
                {
                    "agent_id": agent_id,
                    "tool_name": tool_name,
                    "compare_args": compare_args,
                }
            )
        else:
            action_failures.append(
                {
                    "agent_id": agent_id,
                    "tool_name": tool_name,
                    "compare_args": compare_args,
                    "first_mismatch": first_mismatch,
                }
            )

    outbound_by_agent: dict[str, list[str]] = {}
    for msg in outbound_messages:
        sender = str(msg.get("from") or "")
        content = str(msg.get("content") or "")
        outbound_by_agent.setdefault(sender, []).append(content)

    communicate_passes: list[dict[str, Any]] = []
    communicate_failures: list[dict[str, Any]] = []
    for check in communicate_checks:
        agent_id = str(check.get("agent_id") or "")
        must_say = [str(s) for s in (check.get("must_say") or [])]
        if not must_say:
            communicate_passes.append({"agent_id": agent_id, "must_say": []})
            continue
        contents = outbound_by_agent.get(agent_id) or []
        joined = "\n".join(contents)
        missing = [s for s in must_say if s not in joined]
        if missing:
            communicate_failures.append(
                {
                    "agent_id": agent_id,
                    "must_say": must_say,
                    "missing": missing,
                }
            )
        else:
            communicate_passes.append(
                {"agent_id": agent_id, "must_say": must_say}
            )

    predicate_passes, predicate_failures, predicate_diagnostics = _evaluate_predicates(
        env_assertions=env_assertions,
        resources_dir=resources_dir,
        family_id=family_id,
    )

    actions_ok = (
        not action_failures and (
            bool(action_passes) or not action_checks
        )
    )
    predicates_ok = (
        not predicate_failures and (
            bool(predicate_passes) or not env_assertions
        )
    )
    has_any_check = bool(action_checks) or bool(env_assertions)
    task_success = bool(has_any_check and actions_ok and predicates_ok)

    required_canonical_tools = sorted({
        str(check.get("tool_name") or "")
        for check in action_checks
        if check.get("tool_name")
    })
    return EnvAssertionResult(
        task_success=task_success,
        canonical_actions_dispatched=canonical_tools_dispatched,
        required_canonical_tools=required_canonical_tools,
        action_passes=action_passes,
        action_failures=action_failures,
        communicate_passes=communicate_passes,
        communicate_failures=communicate_failures,
        predicate_passes=predicate_passes,
        predicate_failures=predicate_failures,
        diagnostics={
            "action_checks_count": len(action_checks),
            "communicate_checks_count": len(communicate_checks),
            "env_assertions_count": len(env_assertions),
            "has_any_check": has_any_check,
            **predicate_diagnostics,
        },
    )


def _evaluate_predicates(
    *,
    env_assertions: list[dict[str, Any]],
    resources_dir: Path | str | None,
    family_id: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Run every declared env_assertion predicate against the post-run
    resource state. Returns ``(passes, failures, diagnostics)``.

    Each pass / fail entry carries the predicate name, the args
    supplied at evaluation, and the predicate's reason + diagnostics.
    Unresolved predicate names land in ``failures`` with a
    ``reason="predicate_not_registered"`` entry. Missing
    ``resources_dir`` lands every predicate in ``failures`` with
    ``reason="resources_dir_unavailable"`` so the run reports a clean
    fail rather than silently passing on missing state.
    """
    if not env_assertions:
        return [], [], {"predicate_pass_count": 0, "predicate_fail_count": 0}
    if resources_dir is None:
        failures = [
            {
                "predicate": str(item.get("predicate") or ""),
                "args": dict(item.get("args") or {}),
                "reason": "resources_dir_unavailable",
            }
            for item in env_assertions
        ]
        return [], failures, {
            "predicate_pass_count": 0,
            "predicate_fail_count": len(failures),
            "predicate_error": "resources_dir_unavailable",
        }
    state = build_env_state(resources_dir=Path(resources_dir))
    registry = _resolve_predicate_registry(family_id)
    passes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for item in env_assertions:
        pred_name = str(item.get("predicate") or "")
        args = dict(item.get("args") or {})
        fn = registry.get(pred_name)
        if fn is None:
            failures.append(
                {
                    "predicate": pred_name,
                    "args": args,
                    "reason": "predicate_not_registered",
                    "diagnostics": {"family_id": family_id},
                }
            )
            continue
        try:
            result = fn(state, **args)
        except Exception as exc:  # noqa: BLE001
            failures.append(
                {
                    "predicate": pred_name,
                    "args": args,
                    "reason": "predicate_raised",
                    "diagnostics": {
                        "exc_type": type(exc).__name__,
                        "exc_msg": str(exc),
                    },
                }
            )
            continue
        entry = {
            "predicate": pred_name,
            "args": args,
            "reason": getattr(result, "reason", ""),
            "diagnostics": dict(getattr(result, "diagnostics", {}) or {}),
        }
        if getattr(result, "passed", False):
            passes.append(entry)
        else:
            failures.append(entry)
    return passes, failures, {
        "predicate_pass_count": len(passes),
        "predicate_fail_count": len(failures),
    }


def evaluate_from_bundle_dir(
    *,
    bundle_dir: Path | str,
    action_log: list[ActionRecord],
    outbound_messages: list[dict[str, Any]],
    family_id: str | None = None,
) -> EnvAssertionResult:
    """Load ``scenario.gt.json`` from a bundle dir and evaluate.

    Convenience wrapper for the live executor: the executor knows
    the bundle directory but not the parsed :class:`GTBundle`. The
    bundle dir's ``resources/`` subtree carries the post-run sqlite
    state predicates score against; passing the bundle dir lets the
    evaluator infer the resources path without an extra parameter.
    """
    bundle_path_dir = Path(bundle_dir)
    bundle_path = bundle_path_dir / "scenario.gt.json"
    if not bundle_path.is_file():
        return EnvAssertionResult(
            task_success=False,
            diagnostics={"error": f"missing bundle at {bundle_path}"},
        )
    try:
        raw = json.loads(bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return EnvAssertionResult(
            task_success=False,
            diagnostics={"error": f"invalid GT json: {exc}"},
        )
    try:
        gt = GTBundle.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        return EnvAssertionResult(
            task_success=False,
            diagnostics={"error": f"GTBundle validation: {exc}"},
        )
    criteria = raw.get("evaluation_criteria") if isinstance(raw, dict) else None
    resources_dir = bundle_path_dir / "resources"
    return evaluate_evaluation_criteria(
        gt_bundle=gt,
        action_log=action_log,
        outbound_messages=outbound_messages,
        evaluation_criteria_override=(
            criteria if isinstance(criteria, dict) else None
        ),
        resources_dir=resources_dir if resources_dir.is_dir() else None,
        family_id=family_id,
    )


# ---------- Helpers ----------------------------------------------------


def _observation_indicates_failure(payload: dict[str, Any]) -> bool:
    """Return True iff the TOOL_OBSERVATION_RETURN payload signals
    a dispatch failure.

    The agent loop's payload layout is
    ``{"observation": "<json string>", "tool_call_action_id": ...,
    "tool_name": ...}``. The handler's actual response (success or
    synthetic-failure dict) lives inside the JSON-stringified
    ``observation`` field. We parse it and inspect ``ok`` /
    ``error`` keys there. Older payloads that happened to expose
    ``ok`` / ``error`` at the top level are also handled.
    """
    if payload.get("error"):
        return True
    if payload.get("ok") is False:
        return True
    obs = payload.get("observation")
    if isinstance(obs, str):
        try:
            decoded = json.loads(obs)
        except json.JSONDecodeError:
            return False
        if isinstance(decoded, dict):
            if decoded.get("error"):
                return True
            if decoded.get("ok") is False:
                return True
    elif isinstance(obs, dict):
        if obs.get("error"):
            return True
        if obs.get("ok") is False:
            return True
    return False


def _read_evaluation_criteria(gt: GTBundle) -> dict[str, Any]:
    """Pull ``evaluation_criteria`` out of the GT bundle.

    ``GTBundle`` does not declare ``evaluation_criteria`` as a
    Pydantic field; the family-pack loaders attach it directly to
    the underlying dict. The bundle's model exposes ``model_extra``
    when configured to allow extras; for compatibility we inspect
    both ``model_extra`` and the bundle's serialized dict.
    """
    extras = getattr(gt, "model_extra", None) or {}
    if "evaluation_criteria" in extras:
        ec = extras["evaluation_criteria"]
        return dict(ec) if isinstance(ec, dict) else {}
    try:
        dumped = gt.model_dump(mode="json")
    except Exception:  # noqa: BLE001
        return {}
    ec = dumped.get("evaluation_criteria") if isinstance(dumped, dict) else None
    return dict(ec) if isinstance(ec, dict) else {}


def _index_canonical_args(
    canonical_action_stream: list[Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Index canonical-action-stream arguments by (agent_id, tool_name)."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for step in canonical_action_stream:
        if not isinstance(step, dict):
            continue
        agent_id = str(step.get("agent_id") or "")
        tool_name = str(step.get("tool_name") or step.get("tool") or "")
        if not (agent_id and tool_name):
            continue
        args = step.get("arguments") or step.get("args") or {}
        if isinstance(args, dict):
            out[(agent_id, tool_name)] = dict(args)
    return out


def _arg_mismatch(
    *,
    observed: dict[str, Any],
    expected: dict[str, Any],
    compare_keys: list[str],
) -> dict[str, Any] | None:
    """Return a ``{key, observed, expected}`` dict for the first
    mismatched compare key, or ``None`` when every compare key
    matches. When ``expected`` is empty, the check is treated as
    "any call counts" and returns ``None``.
    """
    if not expected:
        return None
    for key in compare_keys:
        if key not in expected:
            continue
        observed_value = observed.get(key)
        expected_value = expected.get(key)
        if str(observed_value) != str(expected_value):
            return {
                "key": key,
                "observed": observed_value,
                "expected": expected_value,
            }
    return None


__all__ = [
    "EnvAssertionResult",
    "evaluate_evaluation_criteria",
    "evaluate_from_bundle_dir",
]
