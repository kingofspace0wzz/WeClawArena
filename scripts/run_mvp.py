"""Run the CU Scheduling MVP scenario end-to-end.

Usage:
    python -m scripts.run_mvp

Uses MockLLMClient so no API keys are required.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from clawsocialarena.agents.llm_client import MockLLMClient
from clawsocialarena.runtime.runner import ScenarioRunner
from clawsocialarena.scenario.loader import ScenarioLoader
from clawsocialarena.types import AuditCondition


async def main() -> None:
    fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "scenarios"
    loader = ScenarioLoader(root=fixtures)
    scenario, gt = loader.load("cu_scheduling_mvp")

    def factory(agent_id: str) -> MockLLMClient:
        if agent_id == "alice":
            return MockLLMClient(
                canned_responses=[
                    "How about Tuesday at 2pm?",
                    "[READY_TO_PIN 2026-04-21T14:00:00Z]",
                ]
            )
        return MockLLMClient(canned_responses=["[READY_TO_PIN 2026-04-21T14:00:00Z]"])

    # PASSIVE keeps the audit infrastructure on so the demo still shows action
    # log activity; BASELINE now runs with no ActionLog/ShadowLog (Task 3.5a).
    runner = ScenarioRunner(
        scenario=scenario,
        gt=gt,
        llm_factory=factory,
        db_path="/tmp/clawsocialarena_mvp.db",
        condition=AuditCondition.PASSIVE,
    )
    result = await runner.run()
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
