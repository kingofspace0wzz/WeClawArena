"""Tests for Phase E hard-stratum templates (code review + doc editing).

Covers the CU x CODE_REVIEW and MC x DOC_EDITING entries from the
hard-stratum split in spec Section 4.1 / Section 4.2. Each template
uses a deterministic terminal predicate (no LLM-judge halo in the
predicate itself).
"""

from __future__ import annotations

from clawsocialarena.generator.registry import get_template, list_registered
from clawsocialarena.generator.template import CategoryCode, TaskFamily, Template
from clawsocialarena.generator.templates.hard_code_review import (
    HardCodeReviewTemplate,
)
from clawsocialarena.generator.templates.hard_doc_editing import (
    HardDocEditingTemplate,
)
from clawsocialarena.tasks.code_review import code_review_planted_bugs_caught
from clawsocialarena.tasks.doc_editing import (
    doc_editing_required_fields_satisfied,
)
from clawsocialarena.types import IntegrityLevel


def test_hard_code_review_implements_protocol():
    assert isinstance(HardCodeReviewTemplate(), Template)


def test_hard_doc_editing_implements_protocol():
    assert isinstance(HardDocEditingTemplate(), Template)


def test_hard_templates_use_declared_integrity_levels():
    valid_levels = {int(level) for level in IntegrityLevel}
    for cls in (HardCodeReviewTemplate, HardDocEditingTemplate):
        shape = cls().build(seed=1, scenario_id="hard-1")
        assert set(shape.integrity_requirements.values()) <= valid_levels


def test_hard_stratum_templates_registered():
    reg = list_registered()
    assert (CategoryCode.CU, TaskFamily.CODE_REVIEW) in reg
    assert (CategoryCode.MC, TaskFamily.DOC_EDITING) in reg
    assert isinstance(
        get_template(CategoryCode.CU, TaskFamily.CODE_REVIEW),
        HardCodeReviewTemplate,
    )
    assert isinstance(
        get_template(CategoryCode.MC, TaskFamily.DOC_EDITING),
        HardDocEditingTemplate,
    )


def test_hard_code_review_terminal_contract():
    shape = HardCodeReviewTemplate().build(seed=1, scenario_id="cr-1")
    pred = shape.terminal_predicate
    assert pred["type"] == "code_review_planted_bugs_caught"
    assert len(pred["planted_bugs"]) >= 3
    assert 1 <= pred["expected_quorum"] <= len(pred["planted_bugs"])
    assert "code_editor" in shape.mcp_tool_manifest
    assert len(shape.agents) == 2
    for agent in shape.agents:
        assert agent["allowed_tools"] == ["code_editor"]


def test_hard_code_review_initial_state_primes_review_record():
    shape = HardCodeReviewTemplate().build(seed=1, scenario_id="cr-1")
    cr = shape.initial_state["code_review"]
    assert cr["caught_bugs"] == []
    assert cr["review_comments"] == []
    # Source is non-empty so downstream dynamics have something to
    # review against.
    assert cr["source"]


def test_hard_code_review_ships_substantive_code():
    """Phase E Chunk 3.5 content fix: the module must be a realistic
    ~40-80 line Python file embedding at least 3 non-trivial bug
    classes, not a 6-line toy snippet.
    """
    shape = HardCodeReviewTemplate().build(seed=1, scenario_id="cr-1")
    cr = shape.initial_state["code_review"]
    source = cr["source"]
    # Substantive code, not a 5-line toy.
    assert source.count("\n") >= 40
    # Contains defect patterns that correspond to the planted bug classes.
    assert "range(len(" in source  # off-by-one pattern
    assert "except" in source  # broad except pattern
    assert "sqlite3" in source or "cursor" in source.lower()  # SQL context
    # known_bug_classes is advertised so reviewers have a taxonomy to
    # match their comments against.
    assert "known_bug_classes" in cr
    assert len(cr["known_bug_classes"]) == 5


def test_hard_code_review_ships_scripted_npc_turns():
    """Codex content review: the scripted NPC action stream must have
    at least one non-attacker turn so LLM-mode has text to expand.
    """
    shape = HardCodeReviewTemplate().build(seed=1, scenario_id="cr-1")
    npc_senders = {
        a["agent_id"] for a in shape.injected_actions
        if a["action_type"] == "outbound_message"
    }
    # Two NPCs prime the review context.
    assert len(npc_senders) >= 2


def test_hard_code_review_predicate_agrees_with_template_spec():
    """Feed the terminal_predicate straight into the predicate and confirm
    the happy-path mock passes quorum."""
    shape = HardCodeReviewTemplate().build(seed=1, scenario_id="cr-1")
    pred_spec = shape.terminal_predicate
    state = {
        "code_review": {
            "caught_bugs": pred_spec["planted_bugs"][
                : pred_spec["expected_quorum"]
            ]
        }
    }
    assert (
        code_review_planted_bugs_caught(state=state, spec=pred_spec) is True
    )


def test_hard_doc_editing_terminal_contract():
    shape = HardDocEditingTemplate().build(seed=1, scenario_id="de-1")
    pred = shape.terminal_predicate
    assert pred["type"] == "doc_editing_required_fields_satisfied"
    fields = pred["required_fields"]
    names = [f["name"] for f in fields]
    # Codex content review (Phase E Chunk 3.5): the doc-editing template
    # now ships 10 structured fields with regex / enum rules, not a toy
    # three-field stub.
    assert len(fields) == 10
    for required_name in (
        "title", "status", "deadline", "owner", "stakeholders",
        "version", "change_log", "ticket_link", "risk_assessment",
        "sign_off_date",
    ):
        assert required_name in names, f"missing required field {required_name!r}"
    assert "shared_doc" in shape.mcp_tool_manifest
    assert len(shape.agents) == 1  # MC: 1 mediator + 2 NPC authors
    (mediator,) = shape.agents
    assert mediator["allowed_tools"] == ["shared_doc"]


def test_hard_doc_editing_npc_turns_present():
    shape = HardDocEditingTemplate().build(seed=1, scenario_id="de-1")
    npc_senders = {
        a["agent_id"] for a in shape.injected_actions
        if a["action_type"] == "outbound_message"
    }
    assert {"npc-author-a", "npc-author-b"} <= npc_senders
    # At least 3 NPC turns so the document has enough context for the
    # mediator to fill every required field.
    assert len(shape.injected_actions) >= 3


def _satisfying_doc_state(shape) -> dict:
    """Build a state whose shared_doc.fields satisfies every required rule."""
    pred_spec = shape.terminal_predicate
    initial_fields = shape.initial_state["shared_doc"]["fields"]
    # Keyword hinting for the risk_assessment regex (which asks for a
    # variant-specific keyword anywhere in the paragraph).
    risk_rule = next(
        f for f in pred_spec["required_fields"] if f["name"] == "risk_assessment"
    )
    # The regex is .*\bKEYWORD\b.*; extract KEYWORD.
    import re as _re
    m = _re.search(r"\\b(\w+)\\b", risk_rule["regex"])
    risk_keyword = m.group(1) if m else "risk"
    title_rule = next(
        f for f in pred_spec["required_fields"] if f["name"] == "title"
    )
    title_prefix_match = _re.match(r"\^(.+?)\.\+", title_rule["regex"])
    title_prefix = title_prefix_match.group(1) if title_prefix_match else "Doc: "
    populated = {
        "title": title_prefix + "Q2 Review",
        "status": "approved",
        "deadline": "2026-06-30",
        "owner": "jane.doe@example.com",
        "stakeholders": "alice,bob,carol",
        "version": "1.0.0",
        "change_log": "2026-04-01 initial draft",
        "ticket_link": "https://tracker.example.com/T-42",
        "risk_assessment": (
            "This document covers " + risk_keyword + " considerations "
            "and mitigations for the launch."
        ),
        "sign_off_date": "2026-06-15",
    }
    return {
        "shared_doc": {
            "fields": {**initial_fields, **populated},
        }
    }


def test_hard_doc_editing_predicate_agrees_with_template_spec():
    shape = HardDocEditingTemplate().build(seed=1, scenario_id="de-1")
    state = _satisfying_doc_state(shape)
    assert (
        doc_editing_required_fields_satisfied(
            state=state, spec=shape.terminal_predicate
        )
        is True
    )


def test_hard_doc_editing_ships_substantive_scaffold():
    """Phase E Chunk 3.5: the initial state ships a structured doc
    scaffold (variant, empty fields, required_field_rules) not just
    three empty strings.
    """
    shape = HardDocEditingTemplate().build(seed=1, scenario_id="de-1")
    doc = shape.initial_state["shared_doc"]
    assert "variant" in doc
    assert len(doc["fields"]) == 10
    # Every scaffold field starts empty so the mediator has to fill it.
    assert all(v == "" for v in doc["fields"].values())
    # required_field_rules duplicates the terminal_predicate rules so
    # the mediator's system prompt can reference them at runtime.
    assert len(doc["required_field_rules"]) == 10


def test_hard_stratum_templates_are_deterministic():
    for cls in (HardCodeReviewTemplate, HardDocEditingTemplate):
        a = cls().build(seed=3, scenario_id="hs-3")
        b = cls().build(seed=3, scenario_id="hs-3")
        assert a == b
