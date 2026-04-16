from clawsocialarena.generator.template import CategoryCode, TaskFamily, Template
from clawsocialarena.generator.templates.cu_scheduling import CUSchedulingTemplate


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
    assert shape.integrity_requirements == {"outbound_message": 3}
