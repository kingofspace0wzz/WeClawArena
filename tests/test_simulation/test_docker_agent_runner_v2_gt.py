from __future__ import annotations

import json
from pathlib import Path


def test_docker_runner_loads_phase5_gt_without_terminal_predicate(
    tmp_path: Path,
) -> None:
    from clawsocialarena.simulation.docker_agent_runner import (
        _load_gt_bundle_for_simulation,
    )

    gt_path = tmp_path / "scenario.gt.json"
    gt_path.write_text(
        json.dumps(
            {
                "scenario_id": "v2-row",
                "canonical_action_stream": [],
                "evaluation_criteria": {"actions": []},
                "policies": {},
                "resource_manifest": {"resources": {}},
            }
        ),
        encoding="utf-8",
    )

    gt = _load_gt_bundle_for_simulation(gt_path)

    assert gt.scenario_id == "v2-row"
    assert gt.terminal_predicate == {"type": "none"}
