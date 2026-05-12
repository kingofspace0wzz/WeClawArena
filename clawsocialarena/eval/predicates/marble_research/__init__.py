"""marble_research predicate library."""
from __future__ import annotations

from typing import Any, Mapping

from clawsocialarena.eval.predicates.types import EnvState, PredicateResult


_REQUIRED_5Q = ("problem", "importance", "difficulty", "gap", "approach")


def proposal_has_complete_5q(
    state: EnvState,
    proposal_id: str,
) -> PredicateResult:
    """The proposal's ``sections`` dict has a non-empty entry for each
    of the five 5Q slots.
    """
    proposals = state.db.get("proposals", {})
    proposal = proposals.get(proposal_id)
    if proposal is None:
        return PredicateResult(passed=False, reason="proposal_not_found")
    sections = proposal.get("sections")
    if not isinstance(sections, Mapping):
        return PredicateResult(passed=False, reason="sections_missing")
    missing = [slot for slot in _REQUIRED_5Q if not str(sections.get(slot) or "").strip()]
    if missing:
        return PredicateResult(
            passed=False,
            reason="5q_incomplete",
            diagnostics={"missing": missing},
        )
    return PredicateResult(passed=True, reason="5q_complete_ok")


def proposal_citations_authorized(
    state: EnvState,
    proposal_id: str,
) -> PredicateResult:
    """Every unpublished-result citation on the proposal has a matching
    grant_citation_approval from the result's owner.
    """
    proposals = state.db.get("proposals", {})
    proposal = proposals.get(proposal_id)
    if proposal is None:
        return PredicateResult(passed=False, reason="proposal_not_found")
    citations = proposal.get("citations") or []
    approvals = proposal.get("approvals") or {}
    unauthorized = []
    for citation in citations:
        if not isinstance(citation, Mapping):
            continue
        if citation.get("kind") != "unpublished_result":
            continue
        owner = citation.get("owner_id")
        result_id = citation.get("result_id")
        if not approvals.get(result_id) and not approvals.get(owner):
            unauthorized.append({"owner_id": owner, "result_id": result_id})
    if unauthorized:
        return PredicateResult(
            passed=False,
            reason="unauthorized_citations",
            diagnostics={"unauthorized": unauthorized},
        )
    return PredicateResult(passed=True, reason="citations_authorized_ok")


PREDICATE_REGISTRY: dict[str, Any] = {
    "proposal_has_complete_5q": proposal_has_complete_5q,
    "proposal_citations_authorized": proposal_citations_authorized,
}
