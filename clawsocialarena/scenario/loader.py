from __future__ import annotations

import json
from pathlib import Path

from clawsocialarena.scenario.models import Scenario, GTBundle


class ScenarioLoader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def load(self, scenario_id: str) -> tuple[Scenario, GTBundle]:
        base = self.root / scenario_id
        scenario = Scenario.model_validate(json.loads((base / "scenario.json").read_text()))
        gt = GTBundle.model_validate(json.loads((base / "scenario.gt.json").read_text()))
        return scenario, gt
