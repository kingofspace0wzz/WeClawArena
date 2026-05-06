"""Scenario loader (spec §4.5; Task D8).

``ScenarioLoader.load(scenario_id)`` returns a triple
``(Scenario, GTBundle, ComposeSpec)``. The ``ComposeSpec`` dataclass holds
filesystem paths for the docker-compose.yml + personas/ + mcp/ portions
of the bundle; downstream ``ScenarioIO`` consumers dial the compose runner
with it.

The loader is tolerant of legacy bundles that ship only
``scenario.json`` + ``scenario.gt.json`` (no compose/personas/mcp). In
that case, the compose path is set to ``None`` and the directory paths
point at whatever ``<base>/personas`` or ``<base>/mcp`` resolves to, even
if those directories do not yet exist. Callers that need to discriminate
should use ``ComposeSpec.compose_yaml`` being ``None``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from clawsocialarena.scenario.models import Scenario, GTBundle


@dataclass(frozen=True)
class ComposeSpec:
    """Filesystem-side view of a v2 scenario bundle.

    Fields:
        compose_yaml: path to ``docker-compose.yml`` or ``None`` when the
            bundle is a legacy (v1) directory that ships only JSON.
        personas_dir: path to ``personas/`` (may not exist for legacy bundles).
        mcp_dir: path to ``mcp/`` (may not exist for legacy bundles).
        resources_dir: path to ``resources/`` (may not exist for legacy bundles).
    """

    compose_yaml: Path | None
    personas_dir: Path
    mcp_dir: Path
    resources_dir: Path


class ScenarioLoader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def load(self, scenario_id: str) -> tuple[Scenario, GTBundle, ComposeSpec]:
        base = self.root / scenario_id
        scenario = Scenario.model_validate(
            json.loads((base / "scenario.json").read_text())
        )
        gt = GTBundle.model_validate(
            json.loads((base / "scenario.gt.json").read_text())
        )
        compose_yaml_path = base / "docker-compose.yml"
        compose_spec = ComposeSpec(
            compose_yaml=compose_yaml_path if compose_yaml_path.exists() else None,
            personas_dir=base / "personas",
            mcp_dir=base / "mcp",
            resources_dir=base / "resources",
        )
        return scenario, gt, compose_spec
