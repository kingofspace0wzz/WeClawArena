"""Tests for marble_research MCP tool handlers."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.generator.family_packs.marble_research import (
    load_research_collaboration_scenario,
    materialize_research_collaboration_bundle,
)
from clawsocialarena.mcp_tools.marble_research import (
    ResearchCollaborationContext,
    TOOL_NAMES,
    dispatch,
    register_marble_research_handlers,
)


@pytest.fixture
def research_context(tmp_path: Path) -> ResearchCollaborationContext:
    bundle = load_research_collaboration_scenario()
    bundle_dir = tmp_path / "scenario"
    materialize_research_collaboration_bundle(bundle, bundle_dir)
    return ResearchCollaborationContext(
        resources_root=bundle_dir / "resources",
        proposal_id="PROP-7",
        convener_owner_id="alpha",
        peer_owner_ids=("beta", "gamma"),
    )


def _draft_all_5q(context: ResearchCollaborationContext, drafter: str = "alpha") -> None:
    for section in ("problem", "importance", "difficulty", "gap", "approach"):
        dispatch(
            "draft_proposal_section",
            {
                "proposal_id": "PROP-7",
                "section": section,
                "content": f"{section}: seeded text",
                "drafter_id": drafter,
            },
            context,
        )


def test_get_pi_details_labels_roles(
    research_context: ResearchCollaborationContext,
) -> None:
    convener = dispatch("get_pi_details", {"pi_id": "alpha"}, research_context)
    peer = dispatch("get_pi_details", {"pi_id": "beta"}, research_context)
    assert convener["role"] == "convener_pi"
    assert peer["role"] == "peer_pi"


def test_finalize_blocked_when_5q_incomplete(
    research_context: ResearchCollaborationContext,
) -> None:
    result = dispatch(
        "finalize_proposal",
        {"proposal_id": "PROP-7", "finalizer_id": "alpha"},
        research_context,
    )
    assert result["ok"] is False
    assert result["error"] == "5q_incomplete"
    assert set(result["missing_sections"]) == {
        "problem",
        "importance",
        "difficulty",
        "gap",
        "approach",
    }


def test_finalize_succeeds_with_complete_5q_and_no_citations(
    research_context: ResearchCollaborationContext,
) -> None:
    _draft_all_5q(research_context)
    result = dispatch(
        "finalize_proposal",
        {"proposal_id": "PROP-7", "finalizer_id": "alpha"},
        research_context,
    )
    assert result["ok"]
    assert result["status"] == "finalized"


def test_finalize_blocked_when_unpublished_citation_unauthorized(
    research_context: ResearchCollaborationContext,
) -> None:
    _draft_all_5q(research_context)
    dispatch(
        "request_citation_approval",
        {
            "proposal_id": "PROP-7",
            "result_id": "UR-beta-1",
            "owner_id": "beta",
            "requester_id": "alpha",
        },
        research_context,
    )
    result = dispatch(
        "finalize_proposal",
        {"proposal_id": "PROP-7", "finalizer_id": "alpha"},
        research_context,
    )
    assert result["ok"] is False
    assert result["error"] == "unauthorized_citations"


def test_finalize_succeeds_after_owner_grants_approval(
    research_context: ResearchCollaborationContext,
) -> None:
    _draft_all_5q(research_context)
    dispatch(
        "request_citation_approval",
        {
            "proposal_id": "PROP-7",
            "result_id": "UR-beta-1",
            "owner_id": "beta",
            "requester_id": "alpha",
        },
        research_context,
    )
    grant = dispatch(
        "grant_citation_approval",
        {
            "proposal_id": "PROP-7",
            "result_id": "UR-beta-1",
            "grantor_id": "beta",
        },
        research_context,
    )
    assert grant["ok"]
    result = dispatch(
        "finalize_proposal",
        {"proposal_id": "PROP-7", "finalizer_id": "alpha"},
        research_context,
    )
    assert result["ok"]
    assert result["status"] == "finalized"


def test_grantor_cannot_approve_other_pi_result(
    research_context: ResearchCollaborationContext,
) -> None:
    _draft_all_5q(research_context)
    # alpha tries to grant approval for beta's result - denied.
    forged = dispatch(
        "grant_citation_approval",
        {
            "proposal_id": "PROP-7",
            "result_id": "UR-beta-1",
            "grantor_id": "alpha",
        },
        research_context,
    )
    assert forged["ok"] is False
    assert forged["error"] == "result_not_owned_by_grantor"


def test_only_convener_can_finalize(
    research_context: ResearchCollaborationContext,
) -> None:
    _draft_all_5q(research_context)
    denied = dispatch(
        "finalize_proposal",
        {"proposal_id": "PROP-7", "finalizer_id": "beta"},
        research_context,
    )
    assert denied["ok"] is False
    assert denied["error"] == "authorization_denied"


def test_register_research_handlers_wires_all_tools(
    research_context: ResearchCollaborationContext,
) -> None:
    host = McpHost()
    register_marble_research_handlers(host, context=research_context)
    registered = set(host.tools())
    assert set(TOOL_NAMES).issubset(registered)


@pytest.mark.asyncio
async def test_dispatch_through_mcp_host(
    research_context: ResearchCollaborationContext,
) -> None:
    host = McpHost()
    register_marble_research_handlers(host, context=research_context)
    result = await host.dispatch("get_pi_details", {"pi_id": "alpha"})
    assert result["ok"]
    assert result["role"] == "convener_pi"
