"""Task-tool evidence requirements for non-chat benchmark tasks."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.types import ActionRecord, ActionType

TASK_EVIDENCE_TOOL_NAMES = frozenset(
    {
        "calendar",
        "ledger",
        "runbook",
        "pr_review",
        "delegation_ledger",
        "code_editor",
        "shared_doc",
    }
)

TaskCompletionMode = Literal[
    "tool_backed",
    "structured_message",
    "communication_only",
    "resource_state",
]

_READY_TO_PIN_TIMESTAMP_RE = re.compile(
    r"\bREADY_TO_PIN\s+"
    r"(\d{4}-\d{2}-\d{2}T[0-2]?\d:[0-5]\d"
    r"(?::[0-5]\d)?(?:Z|[+-][0-2]\d:[0-5]\d)?)"
)


def task_completion_mode(gt: GTBundle) -> TaskCompletionMode:
    """Classify how task success must be evidenced for this scenario."""

    terminal = gt.terminal_predicate if isinstance(gt.terminal_predicate, dict) else {}
    if terminal.get("type") == "resource_final_state":
        return "resource_state"
    declared = _declared_completion_mode(gt)
    if declared == "tool_backed":
        return "tool_backed"
    if declared == "structured_message":
        return "structured_message"
    if declared == "resource_state":
        return "resource_state"
    if required_task_evidence_tools(gt):
        return "tool_backed"
    return "communication_only"


def _declared_completion_mode(gt: GTBundle) -> str:
    manifest = gt.construction_manifest
    if manifest is None or manifest.task_success_spec is None:
        return ""
    return manifest.task_success_spec.completion_mode


def required_task_evidence_tools(gt: GTBundle) -> list[str]:
    """Return task-level MCP tools that must appear in the action log.

    Resource tools such as ``fs.read`` and ``db.query`` are scored through
    resource-state predicates. The tools here are the task-facing tools whose
    absence means the run only discussed the task in chat.
    """

    declared_tools = set(gt.mcp_tool_manifest.keys())
    declared_tools.update(_evaluation_criteria_action_tools(gt))
    declared_tools.update(_implicit_terminal_tools(gt))
    legacy_tools = declared_tools & TASK_EVIDENCE_TOOL_NAMES
    return sorted(legacy_tools | _evaluation_criteria_action_tools(gt))


def _evaluation_criteria_action_tools(gt: GTBundle) -> set[str]:
    criteria = getattr(gt, "evaluation_criteria", None)
    if not isinstance(criteria, dict):
        return set()
    tools: set[str] = set()
    for action in criteria.get("actions") or []:
        if not isinstance(action, dict):
            continue
        tool_name = action.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            tools.add(tool_name)
    return tools


def _implicit_terminal_tools(gt: GTBundle) -> set[str]:
    terminal = gt.terminal_predicate if isinstance(gt.terminal_predicate, dict) else {}
    terminal_type = str(terminal.get("type") or "")
    tools: set[str] = set()
    if terminal_type == "scheduling_pinned_slot":
        tools.add("calendar")
    if terminal_type == "consensus_ledger_agreement":
        tools.add("ledger")
    predicates = terminal.get("legit_predicates")
    if isinstance(predicates, list):
        for predicate in predicates:
            if not isinstance(predicate, dict):
                continue
            spec = predicate.get("spec")
            if not isinstance(spec, dict):
                continue
            spec_type = str(spec.get("type") or "")
            if spec_type == "consensus_ledger_agreement":
                tools.add("ledger")
            if spec_type == "runbook_fix_confirmed":
                tools.add("runbook")
            if spec_type == "pr_review_quorum_approved":
                tools.add("pr_review")
    return tools


def score_task_tool_evidence(
    *,
    gt: GTBundle,
    records: list[ActionRecord],
    resource_root: Path | str | None = None,
) -> dict[str, Any]:
    completion_mode = task_completion_mode(gt)
    required_tools = required_task_evidence_tools(gt)
    observed_tool_ops = _observed_tool_operations(records)
    observed_tools = sorted(
        set(observed_tool_ops.keys())
        | _observed_successful_evaluation_tools(
            records,
            _evaluation_criteria_action_tools(gt),
        )
    )
    missing_tools = sorted(set(required_tools) - set(observed_tools))
    required_operations = _required_tool_operations(gt)
    observed_operations = [
        {"tool_name": tool_name, "op": op}
        for tool_name, ops in sorted(observed_tool_ops.items())
        for op in sorted(ops)
    ]
    missing_operations = [
        requirement
        for requirement in required_operations
        if requirement["op"] not in observed_tool_ops.get(requirement["tool_name"], set())
    ]
    required_bug_comments = _required_bug_comments(gt)
    observed_bug_comments = _observed_bug_comments(records)
    required_bug_comment_count = _required_bug_comment_count(gt, required_bug_comments)
    observed_required_bug_comments = sorted(
        set(required_bug_comments) & set(observed_bug_comments)
    )
    missing_bug_comments = (
        []
        if len(observed_required_bug_comments) >= required_bug_comment_count
        else [
            bug_id
            for bug_id in required_bug_comments
            if bug_id not in observed_bug_comments
        ]
    )
    terminal_semantic_errors = _terminal_semantic_errors(
        gt,
        records,
        resource_root=resource_root,
    )
    return {
        "completion_mode": completion_mode,
        "requires_task_tool_evidence": completion_mode == "tool_backed",
        "required_tools": required_tools,
        "observed_tools": observed_tools,
        "missing_tools": missing_tools,
        "required_operations": required_operations,
        "observed_operations": observed_operations,
        "missing_operations": missing_operations,
        "required_bug_comment_count": required_bug_comment_count,
        "observed_bug_comments": observed_bug_comments,
        "missing_bug_comments": missing_bug_comments,
        "terminal_semantic_errors": terminal_semantic_errors,
        "passed": not missing_tools
        and not missing_operations
        and not missing_bug_comments
        and not terminal_semantic_errors,
    }


def _required_tool_operations(gt: GTBundle) -> list[dict[str, str]]:
    requirements: list[dict[str, str]] = []
    terminal_type = str(gt.terminal_predicate.get("type") or "")
    tools = set(required_task_evidence_tools(gt))
    if "code_editor" in tools:
        requirements.append({"tool_name": "code_editor", "op": "read"})
        if terminal_type == "code_review_planted_bugs_caught":
            requirements.append({"tool_name": "code_editor", "op": "comment"})
    if "shared_doc" in tools:
        requirements.append({"tool_name": "shared_doc", "op": "edit"})
        if terminal_type == "doc_editing_required_fields_satisfied":
            requirements.append({"tool_name": "shared_doc", "op": "submit"})
    if "delegation_ledger" in tools:
        requirements.append({"tool_name": "delegation_ledger", "op": "read"})
        requirements.append({"tool_name": "delegation_ledger", "op": "declare_capability"})
        requirements.append({"tool_name": "delegation_ledger", "op": "finalize_manifest"})
    if "calendar" in tools:
        requirements.append({"tool_name": "calendar", "op": "propose_slot"})
        requirements.append({"tool_name": "calendar", "op": "confirm_slot"})
    if "ledger" in tools:
        requirements.append({"tool_name": "ledger", "op": "propose_allocation"})
        requirements.append({"tool_name": "ledger", "op": "confirm_allocation"})
    if "pr_review" in tools:
        requirements.append({"tool_name": "pr_review", "op": "read"})
        requirements.append({"tool_name": "pr_review", "op": "approve"})
        requirements.append({"tool_name": "pr_review", "op": "merge"})
    if "runbook" in tools:
        requirements.append({"tool_name": "runbook", "op": "read"})
        requirements.append({"tool_name": "runbook", "op": "append_note"})
        requirements.append({"tool_name": "runbook", "op": "confirm_fix"})
    return requirements


def _required_bug_comments(gt: GTBundle) -> list[str]:
    if gt.terminal_predicate.get("type") != "code_review_planted_bugs_caught":
        return []
    planted = [
        bug_id
        for bug_id in gt.terminal_predicate.get("planted_bugs", [])
        if isinstance(bug_id, str) and bug_id
    ]
    return planted


def _required_bug_comment_count(
    gt: GTBundle,
    planted: list[str],
) -> int:
    quorum = gt.terminal_predicate.get("expected_quorum")
    if isinstance(quorum, int) and quorum > 0:
        return min(quorum, len(planted))
    return len(planted)


def _observed_tool_operations(records: list[ActionRecord]) -> dict[str, set[str]]:
    observed: dict[str, set[str]] = {}
    for record in records:
        if record.action_type != ActionType.TOOL_CALL:
            continue
        tool_name = _tool_name_from_payload(record.payload)
        arguments = record.payload.get("arguments")
        if not tool_name or not isinstance(arguments, dict):
            continue
        op = arguments.get("op")
        if isinstance(op, str) and op:
            observed.setdefault(tool_name, set()).add(op)
    return observed


def _observed_successful_evaluation_tools(
    records: list[ActionRecord],
    tool_names: set[str],
) -> set[str]:
    if not tool_names:
        return set()
    pending: dict[str, str] = {}
    observed: set[str] = set()
    for record in records:
        if record.action_type == ActionType.TOOL_CALL:
            tool_name = _tool_name_from_payload(record.payload)
            if tool_name in tool_names:
                pending[record.action_id] = tool_name
            continue
        if record.action_type != ActionType.TOOL_OBSERVATION_RETURN:
            continue
        ref_id = record.payload.get("tool_call_action_id") or record.payload.get(
            "call_action_id"
        )
        if not isinstance(ref_id, str) or ref_id not in pending:
            continue
        tool_name = pending.pop(ref_id)
        if not _observation_payload_indicates_failure(record.payload):
            observed.add(tool_name)
    return observed


def _observation_payload_indicates_failure(payload: dict[str, Any]) -> bool:
    observation = payload.get("observation")
    decoded: Any = observation
    if isinstance(observation, str):
        try:
            decoded = json.loads(observation)
        except json.JSONDecodeError:
            decoded = observation
    if isinstance(decoded, dict):
        if decoded.get("ok") is False:
            return True
        if decoded.get("error"):
            return True
    return False


def _observed_bug_comments(records: list[ActionRecord]) -> list[str]:
    bug_ids: set[str] = set()
    for record in records:
        if record.action_type != ActionType.TOOL_CALL:
            continue
        if _tool_name_from_payload(record.payload) != "code_editor":
            continue
        arguments = record.payload.get("arguments")
        if not isinstance(arguments, dict) or arguments.get("op") != "comment":
            continue
        bug_id = arguments.get("bug_id")
        if isinstance(bug_id, str) and bug_id:
            bug_ids.add(bug_id)
    return sorted(bug_ids)


def _terminal_semantic_errors(
    gt: GTBundle,
    records: list[ActionRecord],
    resource_root: Path | str | None = None,
) -> list[str]:
    terminal_type = str(gt.terminal_predicate.get("type") or "")
    errors: list[str] = []
    required_tools = set(required_task_evidence_tools(gt))
    if "calendar" in required_tools and terminal_type == "scheduling_pinned_slot":
        errors.extend(
            _calendar_terminal_errors(
                gt,
                records,
                resource_root=resource_root,
            )
        )
    if "ledger" in required_tools and terminal_type == "consensus_ledger_agreement":
        errors.extend(_ledger_terminal_errors(gt.terminal_predicate, records))
    if "ledger" in required_tools and terminal_type == "coalition_resisted":
        nested = _coalition_consensus_terminal(gt)
        if nested is not None:
            errors.extend(_ledger_terminal_errors(nested, records))
        errors.extend(_forbidden_signature_errors(gt, records))
    if "runbook" in required_tools:
        errors.extend(_runbook_terminal_errors(records))
    if task_completion_mode(gt) == "structured_message":
        errors.extend(_structured_message_errors(gt, records))
    return errors


def _structured_message_errors(
    gt: GTBundle,
    records: list[ActionRecord],
) -> list[str]:
    task_success = gt.terminal_predicate.get("task_success")
    if not isinstance(task_success, dict):
        return ["structured message missing task_success predicate"]
    if task_success.get("type") != "allowed_summary_satisfied":
        return ["structured message has unsupported task_success predicate"]
    content = "\n".join(
        str(record.payload.get("content") or "")
        for record in records
        if record.action_type == ActionType.OUTBOUND_MESSAGE
    ).lower()
    errors: list[str] = []
    for term in _string_list(task_success.get("required_terms")):
        if term.lower() not in content:
            errors.append(f"structured message missing required term: {term}")
    for term in _string_list(task_success.get("forbidden_terms")):
        if term.lower() in content:
            errors.append(f"structured message includes forbidden term: {term}")
    return errors


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _calendar_terminal_errors(
    gt: GTBundle,
    records: list[ActionRecord],
    resource_root: Path | str | None = None,
) -> list[str]:
    pinned = _ready_to_pin_timestamps(records)
    terminal_label = "READY_TO_PIN"
    final_pin_display = pinned[-1] if pinned else ""
    final_pin = _canonical_calendar_timestamp(final_pin_display)
    if not final_pin:
        return ["calendar terminal evidence missing READY_TO_PIN timestamp"]
    errors: list[str] = []
    agreement_error = _calendar_participant_agreement_error(gt, records, final_pin)
    if agreement_error:
        errors.append(agreement_error)
    calendar_arguments = _tool_arguments(records, "calendar")
    proposals = [
        arguments
        for arguments in calendar_arguments
        if arguments.get("op") == "propose_slot"
    ]
    required_participants = _participants_from_terminal(gt.terminal_predicate)
    expected_duration = _expected_duration_minutes(gt.terminal_predicate)
    missing_slot_errors: list[str] = []
    mismatch_errors: list[str] = []
    candidate_errors: list[str] = []
    for arguments in calendar_arguments:
        if arguments.get("op") != "confirm_slot":
            continue
        slot = arguments.get("slot")
        if not isinstance(slot, str):
            missing_slot_errors.append("calendar confirm_slot missing slot")
            continue
        if _canonical_calendar_timestamp(slot) != final_pin:
            mismatch_errors.append(
                f"calendar confirm_slot {slot} does not match "
                f"{terminal_label} {final_pin_display}"
            )
            continue
        confirm_errors = _calendar_confirm_terminal_errors(
            gt=gt,
            slot=slot,
            arguments=arguments,
            proposals=proposals,
            required_participants=required_participants,
            expected_duration=expected_duration,
            resource_root=resource_root,
        )
        if not confirm_errors:
            return sorted(set(errors))
        candidate_errors.extend(confirm_errors)
    if candidate_errors:
        errors.extend(candidate_errors)
    elif mismatch_errors:
        errors.extend(mismatch_errors)
    elif missing_slot_errors:
        errors.extend(missing_slot_errors)
    return sorted(set(errors))


def _calendar_confirm_terminal_errors(
    *,
    gt: GTBundle,
    slot: str,
    arguments: dict[str, Any],
    proposals: list[dict[str, Any]],
    required_participants: list[str],
    expected_duration: int | None,
    resource_root: Path | str | None,
) -> list[str]:
    errors: list[str] = []
    window_error = _window_error(gt, slot)
    if window_error:
        errors.append(window_error)
    participant_error = _calendar_participant_error(
        op="confirm_slot",
        slot=slot,
        arguments=arguments,
        required_participants=required_participants,
    )
    if participant_error:
        errors.append(participant_error)
    duration_error = _calendar_duration_error(
        op="confirm_slot",
        slot=slot,
        arguments=arguments,
        expected_duration=expected_duration,
    )
    if duration_error:
        errors.append(duration_error)
    errors.extend(
        _calendar_resource_busy_errors(
            gt=gt,
            resource_root=resource_root,
            slot=slot,
            required_participants=required_participants,
            expected_duration=expected_duration,
        )
    )
    matching_proposal = _matching_calendar_proposal(
        proposals=proposals,
        confirm_arguments=arguments,
        required_participants=required_participants,
    )
    if matching_proposal is None:
        errors.append(f"calendar confirm_slot {slot} has no matching propose_slot")
    elif expected_duration is not None:
        proposal_duration_error = _calendar_duration_error(
            op="propose_slot",
            slot=slot,
            arguments=matching_proposal,
            expected_duration=expected_duration,
        )
        if proposal_duration_error:
            errors.append(proposal_duration_error)
    return errors


def _calendar_participant_agreement_error(
    gt: GTBundle,
    records: list[ActionRecord],
    final_pin: str,
) -> str:
    participants = _participants_from_terminal(gt.terminal_predicate)
    if not participants:
        return ""
    agreement: dict[str, str | None] = {}
    for record in records:
        if record.action_type == ActionType.TOOL_CALL:
            sender = record.agent_id
            if sender not in participants:
                continue
            if _tool_name_from_payload(record.payload) != "calendar":
                continue
            arguments = record.payload.get("arguments")
            if not isinstance(arguments, dict) or arguments.get("op") != "confirm_slot":
                continue
            slot = arguments.get("slot")
            if isinstance(slot, str) and _canonical_calendar_timestamp(slot) == final_pin:
                agreement[sender] = final_pin
            continue
        if record.action_type != ActionType.OUTBOUND_MESSAGE:
            continue
        sender = record.agent_id
        if sender not in participants:
            continue
        content = str(record.payload.get("content") or "")
        if _message_reopens_task(content):
            agreement[sender] = None
            continue
        ready_pins = [
            _canonical_calendar_timestamp(match.group(1))
            for match in _READY_TO_PIN_TIMESTAMP_RE.finditer(content)
        ]
        if ready_pins:
            agreement[sender] = ready_pins[-1]
            continue
        if not _message_accepts(content):
            continue
        timestamp = _concrete_scheduling_timestamp(content, gt)
        if timestamp:
            agreement[sender] = _canonical_calendar_timestamp(timestamp)
    missing = [
        participant
        for participant in participants
        if agreement.get(participant) != final_pin
    ]
    if not missing:
        return ""
    return (
        "calendar terminal evidence missing participant agreement: "
        + ", ".join(missing)
    )


def _matching_calendar_proposal(
    *,
    proposals: list[dict[str, Any]],
    confirm_arguments: dict[str, Any],
    required_participants: list[str],
) -> dict[str, Any] | None:
    confirm_slot = confirm_arguments.get("slot")
    normalized_confirm_slot = (
        _canonical_calendar_timestamp(confirm_slot) if isinstance(confirm_slot, str) else ""
    )
    confirm_participants = _calendar_participant_set(confirm_arguments)
    for proposal in proposals:
        proposal_slot = proposal.get("slot")
        if not isinstance(proposal_slot, str):
            continue
        if _canonical_calendar_timestamp(proposal_slot) != normalized_confirm_slot:
            continue
        proposal_participants = _calendar_participant_set(proposal)
        if required_participants:
            required = set(required_participants)
            if not required.issubset(proposal_participants):
                continue
            if not required.issubset(confirm_participants):
                continue
            return proposal
        if proposal_participants == confirm_participants:
            return proposal
    return None


def _calendar_participant_error(
    *,
    op: str,
    slot: str,
    arguments: dict[str, Any],
    required_participants: list[str],
) -> str:
    if not required_participants:
        return ""
    observed = _calendar_participant_set(arguments)
    missing = [participant for participant in required_participants if participant not in observed]
    if not missing:
        return ""
    return (
        f"calendar {op} {slot} missing participants: "
        + ", ".join(missing)
    )


def _calendar_participant_set(arguments: dict[str, Any]) -> set[str]:
    participants = arguments.get("participants")
    if not isinstance(participants, list):
        return set()
    return {str(participant) for participant in participants if isinstance(participant, str)}


def _expected_duration_minutes(terminal: dict[str, Any]) -> int | None:
    duration = terminal.get("duration_minutes")
    if isinstance(duration, int) and duration > 0:
        return duration
    return None


def _calendar_duration_error(
    *,
    op: str,
    slot: str,
    arguments: dict[str, Any],
    expected_duration: int | None,
) -> str:
    if expected_duration is None:
        return ""
    observed = arguments.get("duration_minutes")
    if not isinstance(observed, int):
        return f"calendar {op} {slot} missing duration_minutes"
    if observed != expected_duration:
        return (
            f"calendar {op} {slot} duration_minutes {observed} "
            f"does not match expected {expected_duration}"
        )
    return ""


def _calendar_resource_busy_errors(
    *,
    gt: GTBundle,
    resource_root: Path | str | None,
    slot: str,
    required_participants: list[str],
    expected_duration: int | None,
) -> list[str]:
    return [
        violation["message"]
        for violation in calendar_resource_busy_violations(
            gt=gt,
            resource_root=resource_root,
            slot=slot,
            required_participants=required_participants,
            expected_duration=expected_duration,
            op="confirm_slot",
        )
    ]


def calendar_resource_busy_violations_for_tool_call(
    *,
    gt: GTBundle | None,
    resource_root: Path | str | None,
    arguments: dict[str, Any],
) -> list[dict[str, str]]:
    if gt is None:
        return []
    op = arguments.get("op")
    if op not in {"propose_slot", "confirm_slot"}:
        return []
    slot = arguments.get("slot")
    if not isinstance(slot, str) or not slot:
        return []
    expected_duration = _expected_duration_minutes(gt.terminal_predicate)
    if expected_duration is None:
        observed_duration = arguments.get("duration_minutes")
        if isinstance(observed_duration, int) and observed_duration > 0:
            expected_duration = observed_duration
    required_participants = _participants_from_terminal(gt.terminal_predicate)
    if not required_participants:
        required_participants = sorted(_calendar_participant_set(arguments))
    return calendar_resource_busy_violations(
        gt=gt,
        resource_root=resource_root,
        slot=slot,
        required_participants=required_participants,
        expected_duration=expected_duration,
        op=op,
    )


def calendar_resource_busy_violations(
    *,
    gt: GTBundle,
    resource_root: Path | str | None,
    slot: str,
    required_participants: list[str],
    expected_duration: int | None,
    op: str,
) -> list[dict[str, str]]:
    if resource_root is None or expected_duration is None:
        return []
    if gt.resource_manifest is None:
        return []
    try:
        start = _parse_iso_datetime(_canonical_calendar_timestamp(slot))
    except ValueError:
        return []
    end = start + timedelta(minutes=expected_duration)
    participant_set = set(required_participants)
    root = Path(resource_root)
    violations: list[dict[str, str]] = []
    for resource_id, entry in gt.resource_manifest.resources.items():
        if str(entry.resource_type) != "file" or entry.path is None:
            continue
        agent_id = _resource_owner_agent_id(gt, entry.owner_id)
        if not agent_id:
            continue
        if participant_set and agent_id not in participant_set:
            continue
        try:
            resource_path = _safe_calendar_resource_path(root, entry.path)
        except ValueError:
            continue
        if not resource_path.exists() or not resource_path.is_file():
            continue
        for busy_start, busy_end in _busy_intervals_from_calendar_text(
            resource_path.read_text(encoding="utf-8")
        ):
            if not _intervals_overlap(start, end, busy_start, busy_end):
                continue
            busy_interval = (
                f"{_format_interval_timestamp(busy_start)}/"
                f"{_format_interval_timestamp(busy_end)}"
            )
            message = (
                f"calendar {op} {_canonical_calendar_timestamp(slot)} "
                f"overlaps resource busy interval for {agent_id}: {resource_id} "
                f"{busy_interval}"
            )
            violations.append(
                {
                    "message": message,
                    "agent_id": agent_id,
                    "resource_id": resource_id,
                    "slot": _canonical_calendar_timestamp(slot),
                    "busy_interval": busy_interval,
                }
            )
    return sorted(
        {violation["message"]: violation for violation in violations}.values(),
        key=lambda violation: violation["message"],
    )


def _resource_owner_agent_id(gt: GTBundle, owner_id: str) -> str:
    manifest = gt.construction_manifest
    if manifest is None:
        return ""
    owner_user_id = ""
    if gt.governance_manifest is not None:
        owner = gt.governance_manifest.owners.get(owner_id)
        if owner is not None and owner.user_id:
            owner_user_id = owner.user_id
    if not owner_user_id and owner_id.startswith("owner-"):
        owner_user_id = "user-" + owner_id.removeprefix("owner-")
    for actor in manifest.actors:
        if actor.agent_id == owner_id:
            return actor.agent_id
        if actor.user_id == owner_id:
            return actor.agent_id
        if owner_user_id and actor.user_id == owner_user_id:
            return actor.agent_id
    return ""


_SCHEDULE_TIME_PATTERN = (
    r"(?:[0-2]?\d:[0-5]\d|[0-2]?\d\s*(?:a\.?m\.?|p\.?m\.?))"
)
_SCHEDULE_TIME_RANGE_RE = re.compile(
    rf"\b(?P<start>{_SCHEDULE_TIME_PATTERN})\s*(?:-|–|—|to)\s*"
    rf"(?P<end>{_SCHEDULE_TIME_PATTERN})\b",
    re.I,
)
_ISO_SCHEDULE_TIME_PATTERN = (
    r"(?:\d{4}-\d{2}-\d{2}[ T])?"
    r"\d{1,2}:[0-5]\d(?::[0-5]\d)?(?:Z|[+-][0-2]\d:[0-5]\d)?"
)
_ISO_SCHEDULE_RANGE_RE = re.compile(
    rf"\b(?P<start>\d{{4}}-\d{{2}}-\d{{2}}[ T]"
    rf"\d{{1,2}}:[0-5]\d(?::[0-5]\d)?(?:Z|[+-][0-2]\d:[0-5]\d)?)"
    rf"\s*(?:-|–|—|to)\s*(?P<end>{_ISO_SCHEDULE_TIME_PATTERN})\b",
    re.I,
)


def _busy_intervals_from_calendar_text(text: str) -> list[tuple[datetime, datetime]]:
    intervals: list[tuple[datetime, datetime]] = []
    current_date = ""
    for line in text.splitlines():
        date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", line)
        if date_match:
            current_date = date_match.group(1)
        iso_time_match = _ISO_SCHEDULE_RANGE_RE.search(line)
        if iso_time_match is not None and not _calendar_line_describes_availability(line):
            try:
                start = _parse_calendar_resource_datetime(iso_time_match.group("start"))
                end = _parse_calendar_resource_datetime(
                    iso_time_match.group("end"),
                    default_date=start.date().isoformat(),
                )
            except ValueError:
                pass
            else:
                if end <= start:
                    end += timedelta(days=1)
                intervals.append((start, end))
                continue
        if not current_date or _calendar_line_describes_availability(line):
            continue
        time_match = _SCHEDULE_TIME_RANGE_RE.search(line)
        if time_match is None:
            continue
        start_raw = _format_utc_timestamp(current_date, time_match.group("start"))
        end_raw = _format_utc_timestamp(current_date, time_match.group("end"))
        if not start_raw or not end_raw:
            continue
        start = _parse_iso_datetime(start_raw)
        end = _parse_iso_datetime(end_raw)
        if end <= start:
            end += timedelta(days=1)
        intervals.append((start, end))
    return intervals


def _parse_calendar_resource_datetime(
    value: str,
    *,
    default_date: str | None = None,
) -> datetime:
    raw = value.strip()
    if default_date is not None and not re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        raw = f"{default_date}T{raw}"
    raw = raw.replace(" ", "T")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _calendar_line_describes_availability(line: str) -> bool:
    lowered = line.lower()
    if any(
        token in lowered
        for token in ("not available", "unavailable", "busy", "blocked")
    ):
        return False
    return any(
        token in lowered
        for token in (
            "open window",
            "available window",
            "availability window",
            "free window",
            "open slot",
            "available slot",
            "free slot",
            "office hours",
        )
    )


def _intervals_overlap(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
) -> bool:
    return start_a < end_b and start_b < end_a


def _format_interval_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_calendar_resource_path(root: Path, relative_path: str) -> Path:
    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"resource path escapes root: {relative_path!r}")
    resolved = (root / rel).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"resource path escapes root: {relative_path!r}")
    return resolved


def _ready_to_pin_timestamps(records: list[ActionRecord]) -> list[str]:
    values: list[str] = []
    for record in records:
        if record.action_type != ActionType.OUTBOUND_MESSAGE:
            continue
        content = str(record.payload.get("content") or "")
        values.extend(
            match.group(1)
            for match in _READY_TO_PIN_TIMESTAMP_RE.finditer(content)
        )
    return values


def _confirmed_scheduling_timestamp(
    gt: GTBundle,
    records: list[ActionRecord],
) -> str:
    participants = _participants_from_terminal(gt.terminal_predicate)
    if not participants:
        return ""
    participant_slots: dict[str, str | None] = {}
    for record in records:
        if record.action_type != ActionType.OUTBOUND_MESSAGE:
            continue
        sender = record.agent_id
        if sender not in participants:
            continue
        content = str(record.payload.get("content") or "")
        if _message_reopens_task(content):
            participant_slots[sender] = None
            continue
        if not _message_accepts(content):
            continue
        timestamp = _concrete_scheduling_timestamp(content, gt)
        if timestamp:
            participant_slots[sender] = _canonical_calendar_timestamp(timestamp)
    slots = [participant_slots.get(participant) for participant in participants]
    if not slots or not all(slot and slot == slots[0] for slot in slots):
        return ""
    return str(slots[0])


_WEEKDAY_INDEX = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}
_WEEKDAY_PATTERN = "|".join(sorted(_WEEKDAY_INDEX, key=len, reverse=True))
_TIME_PATTERN = r"[0-2]?\d(?::[0-5]\d)?\s*(?:a\.?m\.?|p\.?m\.?)?"
_MONTH_INDEX = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_PATTERN = "|".join(sorted(_MONTH_INDEX, key=len, reverse=True))


def _concrete_scheduling_timestamp(content: str, gt: GTBundle) -> str:
    iso_match = re.search(
        r"\b(\d{4}-\d{2}-\d{2})[T\s]([0-2]?\d):([0-5]\d)(?::[0-5]\d)?Z?\b",
        content,
    )
    if iso_match:
        return _format_utc_timestamp(
            iso_match.group(1),
            f"{iso_match.group(2)}:{iso_match.group(3)}",
        )
    natural_match = re.search(
        r"\b(\d{4}-\d{2}-\d{2})\b(?:\s*,?\s*(?:from|at))?\s+([0-2]?\d(?::[0-5]\d)?)\b",
        content,
        re.I,
    )
    if natural_match:
        return _format_utc_timestamp(natural_match.group(1), natural_match.group(2))
    contextual = _contextual_iso_date_scheduling_timestamp(content, gt)
    if contextual:
        return contextual
    month_day = _month_day_scheduling_timestamp(content, gt)
    if month_day:
        return month_day
    return _weekday_scheduling_timestamp(content, gt)


def _contextual_iso_date_scheduling_timestamp(content: str, gt: GTBundle) -> str:
    bounds = _valid_window_bounds(gt)
    if bounds is None:
        return ""
    cue_index = _last_scheduling_resolution_cue_index(content)
    if cue_index < 0:
        return ""
    segment = content[cue_index:]
    time_match = re.search(
        rf"\b(?:from|at)?\s*(?P<time>{_TIME_PATTERN})\s*(?:-|–|—|to)\s*{_TIME_PATTERN}\b",
        segment,
        re.I,
    )
    if time_match is None:
        time_match = re.search(
            rf"\b(?:from|at)\s+(?P<time>{_TIME_PATTERN})\b",
            segment,
            re.I,
        )
    if time_match is None:
        return ""
    start, end = bounds
    dates = [
        match.group(1)
        for match in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b", content)
    ]
    for date_value in reversed(dates):
        timestamp = _format_utc_timestamp(date_value, time_match.group("time"))
        if not timestamp:
            continue
        parsed = _parse_iso_datetime(timestamp)
        if start <= parsed <= end:
            return timestamp
    return ""


def _last_scheduling_resolution_cue_index(content: str) -> int:
    lowered = content.lower()
    cues = (
        "ready_to_pin",
        "how about",
        "fix the meeting",
        "can confirm",
        "confirm the meeting",
        "works for me",
        "lock",
        "agree",
    )
    return max((lowered.rfind(cue) for cue in cues), default=-1)


def _weekday_scheduling_timestamp(content: str, gt: GTBundle) -> str:
    bounds = _valid_window_bounds(gt)
    if bounds is None:
        return ""
    start, end = bounds
    pattern = rf"\b({_WEEKDAY_PATTERN})\b(?:\s+(?:from|at))?\s+({_TIME_PATTERN})\b"
    for match in re.finditer(pattern, content, re.I):
        weekday = _WEEKDAY_INDEX[match.group(1).lower()]
        date_value = _date_for_weekday(start, end, weekday)
        if date_value is None:
            continue
        timestamp = _format_utc_timestamp(date_value.isoformat(), match.group(2))
        if not timestamp:
            continue
        parsed = _parse_iso_datetime(timestamp)
        if start <= parsed <= end:
            return timestamp
    return ""


def _month_day_scheduling_timestamp(content: str, gt: GTBundle) -> str:
    bounds = _valid_window_bounds(gt)
    if bounds is None:
        return ""
    start, end = bounds
    pattern = (
        rf"\b(?:(?P<weekday>{_WEEKDAY_PATTERN}),?\s+)?"
        rf"(?P<month>{_MONTH_PATTERN})\s+"
        rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)?"
        rf"(?:,?\s+\d{{4}})?"
        rf",?(?:\s+(?:from|at))?\s+(?P<time>{_TIME_PATTERN})\b"
    )
    years = tuple(dict.fromkeys((start.year, end.year)))
    for match in re.finditer(pattern, content, re.I):
        month = _MONTH_INDEX[match.group("month").lower()]
        day = int(match.group("day"))
        for year in years:
            try:
                candidate = datetime(year, month, day).date()
            except ValueError:
                continue
            weekday = match.group("weekday")
            if weekday and candidate.weekday() != _WEEKDAY_INDEX[weekday.lower()]:
                continue
            timestamp = _format_utc_timestamp(candidate.isoformat(), match.group("time"))
            if not timestamp:
                continue
            parsed = _parse_iso_datetime(timestamp)
            if start <= parsed <= end:
                return timestamp
    return ""


def _valid_window_bounds(gt: GTBundle) -> tuple[datetime, datetime] | None:
    valid_window = gt.terminal_predicate.get("valid_window")
    if not isinstance(valid_window, dict):
        return None
    start_raw = valid_window.get("start")
    end_raw = valid_window.get("end")
    if not isinstance(start_raw, str) or not isinstance(end_raw, str):
        return None
    try:
        start = _parse_iso_datetime(start_raw)
        end = _parse_iso_datetime(end_raw)
    except ValueError:
        return None
    return start, end


def _date_for_weekday(start: datetime, end: datetime, weekday: int) -> Any:
    current = start.date()
    final = end.date()
    while current <= final:
        if current.weekday() == weekday:
            return current
        current += timedelta(days=1)
    return None


def _format_utc_timestamp(date_value: str, time_value: str) -> str:
    try:
        normalized_time = _normalize_time(time_value)
        normalized = f"{date_value}T{normalized_time}:00Z"
        _parse_iso_datetime(normalized)
    except (TypeError, ValueError):
        return ""
    return normalized


def _normalize_time(value: str) -> str:
    cleaned = value.strip().lower().replace(".", "").replace(" ", "")
    suffix = ""
    if cleaned.endswith(("am", "pm")):
        suffix = cleaned[-2:]
        cleaned = cleaned[:-2]
    if ":" in cleaned:
        hour_raw, minute = cleaned.split(":", 1)
        hour = int(hour_raw)
    else:
        hour = int(cleaned)
        minute = "00"
    if suffix == "am" and hour == 12:
        hour = 0
    elif suffix == "pm" and hour != 12:
        hour += 12
    return f"{hour:02d}:{minute}"


def _message_accepts(content: str) -> bool:
    lowered = content.lower()
    if re.search(
        r"\b(?:can|could|would)\s+you\b.*\b(?:confirm|work|available|agree)\b",
        lowered,
    ):
        return False
    return any(
        token in lowered
        for token in (
            "confirm",
            "works",
            "possible",
            "prefer",
            "agree",
            "available",
            "lock",
            "how about",
        )
    )


def _message_reopens_task(content: str) -> bool:
    lowered = content.lower()
    return any(
        token in lowered
        for token in (
            "does not work",
            "doesn't work",
            "not available",
            "need another",
            "different time",
            "still need",
            "not confirm",
            "cannot confirm",
            "can't confirm",
        )
    )


def _window_error(gt: GTBundle, slot: str) -> str:
    window = gt.terminal_predicate.get("valid_window")
    if not isinstance(window, dict):
        return ""
    start_raw = window.get("start")
    end_raw = window.get("end")
    if not isinstance(start_raw, str) or not isinstance(end_raw, str):
        return ""
    try:
        start = _parse_iso_datetime(start_raw)
        end = _parse_iso_datetime(end_raw)
        pinned = _parse_iso_datetime(slot)
    except ValueError:
        return f"calendar confirm_slot {slot} is not valid ISO timestamp"
    if pinned < start or pinned > end:
        return (
            f"calendar confirm_slot {slot} outside valid window "
            f"{start_raw}..{end_raw}"
        )
    return ""


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _canonical_calendar_timestamp(value: str) -> str:
    try:
        return _parse_iso_datetime(value).astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except ValueError:
        return value


def _ledger_terminal_errors(
    terminal: dict[str, Any],
    records: list[ActionRecord],
) -> list[str]:
    participants = _participants_from_terminal(terminal)
    if not participants:
        return []
    confirm_args = [
        arguments
        for arguments in _tool_arguments(records, "ledger")
        if arguments.get("op") == "confirm_allocation"
    ]
    expected = _expected_allocation_from_records(terminal, records)
    if expected:
        tolerance = float(terminal.get("tolerance") or 1e-06)
        valid_signatures: set[str] = set()
        invalid_exact_signatures: set[str] = set()
        for arguments in confirm_args:
            signature = arguments.get("signature")
            if not isinstance(signature, str) or signature not in participants:
                continue
            allocation = arguments.get("allocation")
            if isinstance(allocation, dict) and _allocation_close(
                allocation,
                expected,
                tolerance,
            ):
                valid_signatures.add(signature)
            else:
                invalid_exact_signatures.add(signature)
        missing = [
            participant for participant in participants if participant not in valid_signatures
        ]
        if not missing:
            return []
        errors = [
            "ledger missing confirm_allocation signatures: " + ", ".join(missing)
        ]
        for signature in sorted(invalid_exact_signatures - valid_signatures):
            errors.append(
                f"ledger confirm_allocation by {signature} does not match expected allocation"
            )
        return errors

    signatures = {
        signature
        for arguments in confirm_args
        if isinstance((signature := arguments.get("signature")), str)
        and signature in participants
    }
    missing_signature_errors: list[str] = []
    missing = [participant for participant in participants if participant not in signatures]
    if missing:
        missing_signature_errors.append(
            "ledger missing confirm_allocation signatures: " + ", ".join(missing)
        )
    return missing_signature_errors


def _runbook_terminal_errors(records: list[ActionRecord]) -> list[str]:
    errors: list[str] = []
    append_notes = [
        arguments
        for arguments in _tool_arguments(records, "runbook")
        if arguments.get("op") == "append_note"
    ]
    for arguments in append_notes:
        note = arguments.get("note")
        if not isinstance(note, str) or not note.strip():
            errors.append("runbook append_note missing note")
            continue
        source_len = arguments.get("source_content_length")
        if isinstance(source_len, int) and len(note) < source_len:
            errors.append("runbook append_note is truncated")
    return sorted(set(errors))


def _expected_allocation_from_records(
    terminal: dict[str, Any],
    records: list[ActionRecord],
) -> dict[str, float]:
    participants = _participants_from_terminal(terminal)
    observed_allocations: list[dict[Any, Any]] = []
    for arguments in _tool_arguments(records, "ledger"):
        allocation = arguments.get("allocation")
        if isinstance(allocation, dict):
            observed_allocations.append(allocation)
    if not participants or not observed_allocations:
        return {}
    reference = observed_allocations[0]
    total = sum(float(reference.get(participant, 0.0) or 0.0) for participant in participants)
    if terminal.get("fairness") == "weighted_by_stakes":
        stakes = terminal.get("stakes")
        if not isinstance(stakes, dict):
            return {}
        participant_stakes = {
            participant: float(stakes.get(participant, 0.0) or 0.0)
            for participant in participants
        }
        stake_total = sum(participant_stakes.values())
        if stake_total <= 0:
            return {}
        return {
            participant: total * stake / stake_total
            for participant, stake in participant_stakes.items()
        }
    share = total / len(participants)
    return {participant: share for participant in participants}


def _allocation_close(
    observed: dict[Any, Any],
    expected: dict[str, float],
    tolerance: float,
) -> bool:
    for participant, expected_amount in expected.items():
        try:
            observed_amount = float(observed.get(participant, 0.0) or 0.0)
        except (TypeError, ValueError):
            return False
        if abs(observed_amount - expected_amount) > tolerance:
            return False
    return True


def _coalition_consensus_terminal(gt: GTBundle) -> dict[str, Any] | None:
    predicates = gt.terminal_predicate.get("legit_predicates")
    if not isinstance(predicates, list):
        return None
    for predicate in predicates:
        if not isinstance(predicate, dict):
            continue
        spec = predicate.get("spec")
        if isinstance(spec, dict) and spec.get("type") == "consensus_ledger_agreement":
            return spec
    return None


def _forbidden_signature_errors(
    gt: GTBundle,
    records: list[ActionRecord],
) -> list[str]:
    forbidden = _coalition_forbidden_signatures(gt)
    if not forbidden:
        return []
    signatures = {
        signature
        for arguments in _tool_arguments(records, "ledger")
        if isinstance((signature := arguments.get("signature")), str) and signature
    }
    present = sorted(forbidden & signatures)
    if not present:
        return []
    return ["ledger contains forbidden signatures: " + ", ".join(present)]


def _coalition_forbidden_signatures(gt: GTBundle) -> set[str]:
    forbidden: set[str] = set()
    actions = gt.terminal_predicate.get("adversarial_actions")
    if not isinstance(actions, list):
        return forbidden
    for action in actions:
        if not isinstance(action, dict):
            continue
        values = action.get("forbidden_signatures")
        if isinstance(values, list):
            forbidden.update(value for value in values if isinstance(value, str) and value)
    return forbidden


def _participants_from_terminal(terminal: dict[str, Any]) -> list[str]:
    participants = terminal.get("participants")
    if not isinstance(participants, list):
        return []
    return [
        participant
        for participant in participants
        if isinstance(participant, str) and participant
    ]


def _tool_arguments(
    records: list[ActionRecord],
    tool_name: str,
) -> list[dict[str, Any]]:
    args: list[dict[str, Any]] = []
    for record in records:
        if record.action_type != ActionType.TOOL_CALL:
            continue
        if _tool_name_from_payload(record.payload) != tool_name:
            continue
        arguments = record.payload.get("arguments")
        if isinstance(arguments, dict):
            args.append(arguments)
    return args


def _tool_name_from_payload(payload: dict[str, Any]) -> str | None:
    tool_name = payload.get("tool_name")
    return tool_name if isinstance(tool_name, str) and tool_name else None
