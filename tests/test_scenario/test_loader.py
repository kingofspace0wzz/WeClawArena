from pathlib import Path

from clawsocialarena.scenario.loader import ScenarioLoader
from clawsocialarena.scenario.models import Scenario, GTBundle

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "scenarios"


def test_load_cu_scheduling_mvp():
    loader = ScenarioLoader(root=FIXTURES)
    scenario, gt = loader.load("cu_scheduling_mvp")
    assert isinstance(scenario, Scenario)
    assert isinstance(gt, GTBundle)
    assert scenario.scenario_id == "cu-scheduling-mvp"
    assert scenario.category == "CU"
    assert scenario.task_family == "scheduling"
    assert len(scenario.agents) == 2
    assert gt.terminal_predicate["type"] == "scheduling_pinned_slot"
