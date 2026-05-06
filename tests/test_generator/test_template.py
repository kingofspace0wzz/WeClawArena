from clawsocialarena.generator.template import (
    CategoryCode,
    TaskFamily,
    Template,
    TemplateShape,
)
from clawsocialarena.generator.templates.am_scheduling import AMSchedulingTemplate
from clawsocialarena.generator.templates.cu_scheduling import CUSchedulingTemplate
from clawsocialarena.generator.templates.mc_scheduling import MCSchedulingTemplate


def test_cu_scheduling_implements_protocol():
    t = CUSchedulingTemplate()
    assert isinstance(t, Template)


def test_cu_scheduling_build_is_deterministic():
    t = CUSchedulingTemplate()
    s1 = t.build(seed=42, scenario_id="cu-0")
    s2 = t.build(seed=42, scenario_id="cu-0")
    assert s1 == s2


def test_cu_scheduling_shape_fields():
    t = CUSchedulingTemplate()
    shape = t.build(seed=7, scenario_id="cu-sched-7")
    assert shape.category == CategoryCode.CU
    assert shape.task_family == TaskFamily.SCHEDULING
    assert len(shape.agents) == 2
    assert shape.terminal_predicate["type"] == "scheduling_pinned_slot"
    assert shape.terminal_predicate["participants"] == ["alice", "bob"]
    assert shape.integrity_requirements == {"outbound_message": 3, "tool_call": 2}
    assert "calendar" in shape.mcp_tool_manifest
    assert all("calendar" in agent["allowed_tools"] for agent in shape.agents)


def test_scheduling_templates_use_future_windows_not_stale_april_dates():
    shapes = [
        CUSchedulingTemplate().build(seed=7, scenario_id="cu-sched-7"),
        MCSchedulingTemplate().build(seed=7, scenario_id="mc-sched-7"),
        AMSchedulingTemplate().build(seed=7, scenario_id="am-sched-7"),
    ]

    for shape in shapes:
        valid_window = shape.terminal_predicate["valid_window"]
        assert valid_window["start"] >= "2026-06-01T00:00:00Z"
        assert "2026-04" not in valid_window["start"]
        assert "2026-04" not in valid_window["end"]
        assert "2026-04" not in shape.opening_message["content"]


def test_template_shape_governance_manifest_defaults_empty():
    shape = CUSchedulingTemplate().build(seed=7, scenario_id="cu-sched-7")
    assert shape.governance_manifest == {}


def test_template_shape_accepts_governance_manifest():
    shape = TemplateShape(
        scenario_id="cu-governance",
        category=CategoryCode.CU,
        task_family=TaskFamily.SCHEDULING,
        agents=[
            {
                "agent_id": "alice",
                "user_id": "user-a",
                "system_prompt_template": "p",
                "default_owner_id": "owner-alice",
                "default_identity_id": "identity-alice",
            }
        ],
        initial_state={},
        max_turns=4,
        opening_message={"from": "alice", "to": "alice", "content": "start"},
        phase_schedule=[],
        declared_policies={},
        terminal_predicate={"type": "scheduling_pinned_slot"},
        invariants={},
        integrity_requirements={},
        planted_disclosures=[],
        governance_manifest={
            "owners": {"owner-alice": {"owner_id": "owner-alice"}},
            "identities": {
                "identity-alice": {
                    "identity_id": "identity-alice",
                    "owner_id": "owner-alice",
                    "agent_id": "alice",
                }
            },
            "authorization_scopes": {},
            "approval_mandates": {},
            "escalation_rules": {},
        },
    )

    assert shape.governance_manifest["owners"]["owner-alice"]["owner_id"] == "owner-alice"
