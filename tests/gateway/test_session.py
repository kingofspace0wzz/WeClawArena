"""Tests for the gateway Session object (Task A2).

The Session holds the per-scenario audit substrate that the v1
``ScenarioRunner`` used to own directly. Under ``AuditCondition.BASELINE``
the substrate is absent; under ``PASSIVE`` or ``ENFORCE`` the full set of
``ActionLog``, ``ShadowLog``, and ``PhaseTracker`` instances is wired.
"""

from __future__ import annotations

from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.gateway.session import Session
from clawsocialarena.types import AuditCondition


def test_session_baseline_has_no_audit_substrate(tmp_path: Path) -> None:
    session = Session.build(
        scenario_id="baseline-demo",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
    )

    assert session.scenario_id == "baseline-demo"
    assert session.condition == AuditCondition.BASELINE
    assert session.action_log is None
    assert session.shadow_log is None
    assert session.phase_tracker is None
    assert session.cassette is None
    assert session.hooks == []


def test_session_passive_has_full_substrate(tmp_path: Path) -> None:
    db_path = tmp_path / "passive.db"
    session = Session.build(
        scenario_id="passive-demo",
        condition=AuditCondition.PASSIVE,
        db_path=db_path,
    )

    assert session.scenario_id == "passive-demo"
    assert session.condition == AuditCondition.PASSIVE
    assert isinstance(session.action_log, ActionLog)
    assert isinstance(session.shadow_log, ShadowLog)
    assert isinstance(session.phase_tracker, PhaseTracker)
    assert session.cassette is None
    assert session.hooks == []

    expected_shadow_path = db_path.parent / f"{db_path.stem}.shadow.db"
    assert expected_shadow_path.exists()


def test_session_enforce_mirrors_passive(tmp_path: Path) -> None:
    db_path = tmp_path / "enforce.db"
    session = Session.build(
        scenario_id="enforce-demo",
        condition=AuditCondition.ENFORCE,
        db_path=db_path,
    )

    assert session.condition == AuditCondition.ENFORCE
    assert isinstance(session.action_log, ActionLog)
    assert isinstance(session.shadow_log, ShadowLog)
    assert isinstance(session.phase_tracker, PhaseTracker)
    assert session.cassette is None
    assert session.hooks == []
