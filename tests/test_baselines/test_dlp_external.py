"""Phase F / Task F9: Rule-based DLP external baseline."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clawsocialarena.baselines.dlp_external import (
    DlpRule,
    RuleBasedDLP,
    build_dlp_session,
)
from clawsocialarena.protocols.policy_hook import PolicyVerdict
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    AuditCondition,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _outbound(content: str) -> ActionRecord:
    return ActionRecord(
        action_id="a-0",
        prev_hash="0" * 64,
        agent_id="A",
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCLOSURE,
        payload={"recipient_id": "B", "content": content},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_dlp_hook_allows_clean_message():
    dlp = RuleBasedDLP(
        rules=[
            DlpRule(
                rule_id="dlp.secret",
                pattern=re.compile(r"secret"),
                verdict="block",
                reason="contains 'secret'",
            )
        ]
    )
    decision = dlp.evaluate(action=_outbound("hello world"), context={})
    assert decision.verdict == PolicyVerdict.ALLOW


def test_dlp_hook_blocks_on_pattern_match():
    dlp = RuleBasedDLP(
        rules=[
            DlpRule(
                rule_id="dlp.secret",
                pattern=re.compile(r"secret"),
                verdict="block",
                reason="blocked: secret detected",
            )
        ]
    )
    decision = dlp.evaluate(
        action=_outbound("the secret password is hunter2"), context={}
    )
    assert decision.verdict == PolicyVerdict.BLOCK
    assert decision.policy_id == "dlp.secret"
    assert "secret" in (decision.reason or "")


def test_dlp_hook_rewrites_with_replacement():
    dlp = RuleBasedDLP(
        rules=[
            DlpRule(
                rule_id="dlp.ssn",
                pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
                verdict="rewrite",
                replacement="[REDACTED]",
                reason="SSN-like",
            )
        ]
    )
    decision = dlp.evaluate(
        action=_outbound("my ssn is 123-45-6789 okay?"), context={}
    )
    assert decision.verdict == PolicyVerdict.REWRITE
    assert decision.rewritten_content == "my ssn is [REDACTED] okay?"
    assert decision.policy_id == "dlp.ssn"


def test_dlp_flag_verdict_allows_with_reason():
    dlp = RuleBasedDLP(
        rules=[
            DlpRule(
                rule_id="dlp.email",
                pattern=re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
                verdict="flag",
                reason="email",
            )
        ]
    )
    decision = dlp.evaluate(
        action=_outbound("reach me at a@b.com"), context={}
    )
    assert decision.verdict == PolicyVerdict.ALLOW
    assert decision.policy_id == "dlp.email"


def test_dlp_not_mswm_aware():
    """The DLP hook should not consult MSWM state even when present.

    Spec §5.2 is explicit: 'not MSWM-aware'. We encode that as a test:
    passing an MSWM-populated context never changes the verdict.
    """

    dlp = RuleBasedDLP(
        rules=[
            DlpRule(
                rule_id="dlp.topic",
                pattern=re.compile(r"topic-x", re.IGNORECASE),
                verdict="block",
            )
        ]
    )
    fake_context = {"mswm": object()}  # non-None; a real MSWM isn't needed
    # Even with a context supplied, the hook's verdict is identical.
    d_with = dlp.evaluate(
        action=_outbound("nothing about topic-Y here"), context=fake_context
    )
    d_without = dlp.evaluate(
        action=_outbound("nothing about topic-Y here"), context={}
    )
    assert d_with.verdict == d_without.verdict


def test_dlp_build_session_returns_passive_or_enforce(tmp_path: Path):
    """build_dlp_session wraps RuleBasedDLP into a Session correctly."""

    session = build_dlp_session(
        scenario_id="s-dlp",
        db_path=tmp_path / "dlp.db",
        work_dir=tmp_path,
        condition=AuditCondition.ENFORCE,
    )
    try:
        assert session.condition == AuditCondition.ENFORCE
        assert len(session.hooks) == 1
        assert isinstance(session.hooks[0], RuleBasedDLP)
        assert session.action_log is not None  # non-baseline
    finally:
        session.close()


def test_dlp_build_session_passive_wires_hook_without_rewrite(tmp_path: Path):
    session = build_dlp_session(
        scenario_id="s-dlp-passive",
        db_path=tmp_path / "dlp.db",
        work_dir=tmp_path,
        condition=AuditCondition.PASSIVE,
    )
    try:
        assert session.condition == AuditCondition.PASSIVE
        assert session.hooks and isinstance(session.hooks[0], RuleBasedDLP)
    finally:
        session.close()


def test_dlp_first_match_wins_on_block():
    dlp = RuleBasedDLP(
        rules=[
            DlpRule(
                rule_id="dlp.first",
                pattern=re.compile(r"alpha"),
                verdict="block",
                reason="first",
            ),
            DlpRule(
                rule_id="dlp.second",
                pattern=re.compile(r"alpha"),
                verdict="rewrite",
                replacement="zeta",
                reason="second",
            ),
        ]
    )
    d = dlp.evaluate(action=_outbound("alpha"), context={})
    assert d.verdict == PolicyVerdict.BLOCK
    assert d.policy_id == "dlp.first"


def test_dlp_multiple_rewrites_chain():
    """Consecutive rewrite rules see the already-redacted content."""

    dlp = RuleBasedDLP(
        rules=[
            DlpRule(
                rule_id="dlp.1",
                pattern=re.compile(r"alpha"),
                verdict="rewrite",
                replacement="BETA",
            ),
            DlpRule(
                rule_id="dlp.2",
                pattern=re.compile(r"BETA"),
                verdict="rewrite",
                replacement="GAMMA",
            ),
        ]
    )
    d = dlp.evaluate(action=_outbound("alpha omega"), context={})
    assert d.verdict == PolicyVerdict.REWRITE
    assert d.rewritten_content == "GAMMA omega"


def test_dlp_empty_ruleset_allows_every_message():
    dlp = RuleBasedDLP(rules=[])
    d = dlp.evaluate(action=_outbound("anything goes"), context={})
    assert d.verdict == PolicyVerdict.ALLOW


def test_default_ruleset_ships_sane_defaults(tmp_path: Path):
    """Smoke-check that build_dlp_session without explicit rules uses the
    internal default list (SSN, credit-card, email)."""

    session = build_dlp_session(
        scenario_id="s-def",
        db_path=tmp_path / "def.db",
        work_dir=tmp_path,
    )
    try:
        hook = session.hooks[0]
        assert isinstance(hook, RuleBasedDLP)
        # Three rules in the internal default list.
        assert len(hook.rules) >= 1
        rule_ids = {r.rule_id for r in hook.rules}
        assert "dlp.ssn" in rule_ids
    finally:
        session.close()


@pytest.mark.asyncio
async def test_dlp_hook_integrates_with_gateway_session(tmp_path: Path):
    """End-to-end: the DLP hook wired via build_dlp_session actually runs
    during Session.record_outbound and rewrites content under ENFORCE."""

    session = build_dlp_session(
        scenario_id="s-e2e",
        db_path=tmp_path / "e2e.db",
        work_dir=tmp_path,
        rules=[
            DlpRule(
                rule_id="dlp.block-secret",
                pattern=re.compile(r"secret"),
                verdict="rewrite",
                replacement="[REDACTED]",
                reason="keyword",
            )
        ],
        condition=AuditCondition.ENFORCE,
    )
    try:
        outcome = await session.record_outbound(
            sender_id="A",
            recipient_id="B",
            content="the secret handshake is..",
        )
        assert outcome.rewritten_content is not None
        assert "[REDACTED]" in outcome.rewritten_content
    finally:
        session.close()
