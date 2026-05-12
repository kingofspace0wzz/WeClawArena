"""Tests for wildclaw_social MCP tool handlers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.generator.family_packs.wildclaw_social import (
    load_meeting_negotiation_scenario,
    materialize_meeting_negotiation_bundle,
)
from clawsocialarena.mcp_tools.wildclaw_social import (
    MeetingNegotiationContext,
    TOOL_NAMES,
    dispatch,
    register_wildclaw_social_handlers,
)


@pytest.fixture
def meeting_context(tmp_path: Path) -> MeetingNegotiationContext:
    bundle = load_meeting_negotiation_scenario()
    bundle_dir = tmp_path / "scenario"
    materialize_meeting_negotiation_bundle(bundle, bundle_dir)
    return MeetingNegotiationContext(
        resources_root=bundle_dir / "resources",
        meeting_id="MTG-7",
        organizer_owner_id="alice",
        participant_owner_ids=("bob", "carol", "dave"),
    )


def test_send_email_and_read_inbox_roundtrip(
    meeting_context: MeetingNegotiationContext,
) -> None:
    send = dispatch(
        "send_email",
        {
            "sender_id": "alice",
            "recipient_id": "bob",
            "subject": "Hi",
            "body": "Available Thursday 09:30?",
        },
        meeting_context,
    )
    assert send["ok"]
    read = dispatch("read_inbox", {"reader_id": "bob"}, meeting_context)
    assert read["ok"]
    assert len(read["messages"]) == 1
    assert read["messages"][0]["subject"] == "Hi"


def test_check_availability_for_self_returns_slots(
    meeting_context: MeetingNegotiationContext,
) -> None:
    result = dispatch(
        "check_availability",
        {"owner_id": "bob", "caller_id": "bob"},
        meeting_context,
    )
    assert result["ok"]
    assert result["slots"]
    assert result["slots"][0]["day"] == "Thursday"


def test_check_availability_for_other_participant_denied(
    meeting_context: MeetingNegotiationContext,
) -> None:
    result = dispatch(
        "check_availability",
        {"owner_id": "carol", "caller_id": "bob"},
        meeting_context,
    )
    assert result["ok"] is False
    assert result["error"] == "cannot_read_other_participant_calendar"


def test_organizer_can_check_any_participant_calendar(
    meeting_context: MeetingNegotiationContext,
) -> None:
    result = dispatch(
        "check_availability",
        {"owner_id": "carol", "caller_id": "alice"},
        meeting_context,
    )
    assert result["ok"]


def test_create_event_blocked_without_all_confirmations(
    meeting_context: MeetingNegotiationContext,
) -> None:
    dispatch(
        "propose_meeting_time",
        {
            "meeting_id": "MTG-7",
            "proposer_id": "alice",
            "proposed_time": "Thursday 09:30",
        },
        meeting_context,
    )
    # Only bob confirms.
    dispatch(
        "confirm_attendance",
        {"meeting_id": "MTG-7", "confirmer_id": "bob"},
        meeting_context,
    )
    result = dispatch(
        "create_calendar_event",
        {"meeting_id": "MTG-7", "creator_id": "alice"},
        meeting_context,
    )
    assert result["ok"] is False
    assert result["error"] == "missing_confirmations"
    assert set(result["missing_participants"]) == {"carol", "dave"}


def test_create_event_succeeds_when_all_confirmed(
    meeting_context: MeetingNegotiationContext,
) -> None:
    dispatch(
        "propose_meeting_time",
        {
            "meeting_id": "MTG-7",
            "proposer_id": "alice",
            "proposed_time": "Thursday 09:30",
        },
        meeting_context,
    )
    for participant in ("bob", "carol", "dave"):
        dispatch(
            "confirm_attendance",
            {"meeting_id": "MTG-7", "confirmer_id": participant},
            meeting_context,
        )
    result = dispatch(
        "create_calendar_event",
        {"meeting_id": "MTG-7", "creator_id": "alice"},
        meeting_context,
    )
    assert result["ok"]
    assert result["status"] == "event_created"


def test_organizer_cannot_self_confirm(
    meeting_context: MeetingNegotiationContext,
) -> None:
    result = dispatch(
        "confirm_attendance",
        {"meeting_id": "MTG-7", "confirmer_id": "alice"},
        meeting_context,
    )
    assert result["ok"] is False
    assert result["error"] == "organizer_cannot_self_confirm"


def test_only_organizer_can_propose_time(
    meeting_context: MeetingNegotiationContext,
) -> None:
    denied = dispatch(
        "propose_meeting_time",
        {
            "meeting_id": "MTG-7",
            "proposer_id": "bob",
            "proposed_time": "Friday 14:00",
        },
        meeting_context,
    )
    assert denied["ok"] is False
    assert denied["error"] == "only_organizer_can_propose"


def test_register_social_handlers_wires_all_tools(
    meeting_context: MeetingNegotiationContext,
) -> None:
    host = McpHost()
    register_wildclaw_social_handlers(host, context=meeting_context)
    registered = set(host.tools())
    assert set(TOOL_NAMES).issubset(registered)


@pytest.mark.asyncio
async def test_dispatch_through_mcp_host(
    meeting_context: MeetingNegotiationContext,
) -> None:
    host = McpHost()
    register_wildclaw_social_handlers(host, context=meeting_context)
    result = await host.dispatch("check_availability", {"owner_id": "bob", "caller_id": "bob"})
    assert result["ok"]
