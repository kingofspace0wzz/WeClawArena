from typing import Protocol, runtime_checkable


@runtime_checkable
class ScenarioIO(Protocol):
    def load(self, scenario_id: str) -> tuple[dict, dict]:
        """Return (scenario_spec, gt_bundle) for scenario_id."""
        ...

    def submit(self, run_id: str, artifacts: dict) -> None:
        ...
