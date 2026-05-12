from pathlib import Path

from clawsocialarena.eval.runner import EvalRunner
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def test_evaluate_baseline_records_scores_task_and_marks_saf_not_applicable(
    tmp_path: Path,
) -> None:
    gt = GTBundle(
        scenario_id="baseline-scenario-001",
        terminal_predicate={"type": "none"},
        mcp_tool_manifest={
            "code_editor": {
                "schema": {
                    "type": "object",
                    "properties": {"op": {"type": "string"}},
                    "required": ["op"],
                },
                "audit_class": "tool_call",
            },
        },
    )
    transcript_path = tmp_path / "baseline_transcript.jsonl"
    transcript_path.write_text('{"event_type":"tool_call"}\n', encoding="utf-8")

    scorecard = EvalRunner().evaluate_baseline_records(
        records=[
            _record(
                action_id="tool-read",
                action_type=ActionType.TOOL_CALL,
                payload={
                    "tool_name": "code_editor",
                    "arguments": {"op": "read", "path": "task.py"},
                },
            )
        ],
        gt=gt,
        transcript_path=transcript_path,
        meta={"condition": "baseline", "model": "gpt-4.1-mini"},
    )

    assert scorecard.task.tsr == 1.0
    assert scorecard.meta["condition"] == "baseline"
    assert scorecard.diagnostics["runtime_artifacts"] == {
        "baseline_transcript_path": str(transcript_path),
    }
    assert scorecard.diagnostics["baseline_trace_record_count"] == 1
    assert scorecard.saf.diagnostics["not_applicable"] is True
    assert set(scorecard.saf.diagnostics["applicability"].values()) == {False}
    assert scorecard.saf.overall == 1.0
    assert scorecard.cassette_hash == ""


def _record(
    *,
    action_id: str,
    action_type: ActionType,
    payload: dict,
) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="",
        agent_id="agent-1",
        action_type=action_type,
        timestamp="2026-01-01T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload=payload,
        integrity_level=IntegrityLevel.EXTERNAL,
    )
