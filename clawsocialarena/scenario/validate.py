"""Scenario validator (Task D9; spec §4.9 static scan).

Validates that a v2 scenario bundle on disk is internally consistent:

1. ``scenario.json`` validates as ``Scenario``.
2. ``scenario.gt.json`` validates as ``GTBundle``.
3. ``docker-compose.yml`` parses as YAML and declares a ``services`` mapping.
4. Every agent in ``scenario.json`` has a persona ``.system.md`` plus
   ``.tools.json`` file under ``personas/``.
5. Every entry in ``gt.mcp_tool_manifest`` has a matching mcporter config
   under ``mcp/`` whose declared ``url`` points at the gateway's
   ``/mcp/<tool>`` route.

Callers use :class:`ValidationReport` to interpret the result. CLI entry
point: ``python -m clawsocialarena.scenario.validate <bundle_dir>``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from clawsocialarena.scenario.models import GTBundle, Scenario


@dataclass
class ValidationReport:
    """Outcome of validating one scenario bundle.

    ``errors`` is a list of human-readable strings; an empty list means the
    bundle is valid.
    """

    bundle_dir: Path
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_bundle(bundle_dir: str | Path) -> ValidationReport:
    """Validate one scenario bundle directory."""
    bundle_dir = Path(bundle_dir)
    report = ValidationReport(bundle_dir=bundle_dir)

    if not bundle_dir.is_dir():
        report.errors.append(f"not a directory: {bundle_dir}")
        return report

    scenario = _validate_scenario_json(bundle_dir, report)
    gt = _validate_gt_json(bundle_dir, report)
    _validate_compose_yaml(bundle_dir, report)

    if scenario is not None:
        _validate_personas(bundle_dir, scenario, report)
    if gt is not None:
        _validate_mcp_consistency(bundle_dir, gt, report)

    return report


def _validate_scenario_json(
    bundle_dir: Path, report: ValidationReport
) -> Scenario | None:
    path = bundle_dir / "scenario.json"
    if not path.exists():
        report.errors.append("missing scenario.json")
        return None
    try:
        return Scenario.model_validate(json.loads(path.read_text()))
    except (json.JSONDecodeError, ValidationError) as exc:
        report.errors.append(f"scenario.json: {exc}")
        return None


def _validate_gt_json(
    bundle_dir: Path, report: ValidationReport
) -> GTBundle | None:
    path = bundle_dir / "scenario.gt.json"
    if not path.exists():
        report.errors.append("missing scenario.gt.json")
        return None
    try:
        return GTBundle.model_validate(json.loads(path.read_text()))
    except (json.JSONDecodeError, ValidationError) as exc:
        report.errors.append(f"scenario.gt.json: {exc}")
        return None


def _validate_compose_yaml(bundle_dir: Path, report: ValidationReport) -> None:
    path = bundle_dir / "docker-compose.yml"
    if not path.exists():
        report.errors.append("missing docker-compose.yml")
        return
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        report.errors.append(f"docker-compose.yml: unparseable YAML: {exc}")
        return
    if not isinstance(doc, dict) or "services" not in doc:
        report.errors.append(
            "docker-compose.yml: missing top-level 'services' mapping"
        )
        return
    if not isinstance(doc["services"], dict) or not doc["services"]:
        report.errors.append(
            "docker-compose.yml: 'services' must be a non-empty mapping"
        )


def _validate_personas(
    bundle_dir: Path, scenario: Scenario, report: ValidationReport
) -> None:
    personas_dir = bundle_dir / "personas"
    if not personas_dir.is_dir():
        report.errors.append("missing personas/ directory")
        return
    for agent in scenario.agents:
        system_md = personas_dir / f"{agent.agent_id}.system.md"
        tools_json = personas_dir / f"{agent.agent_id}.tools.json"
        if not system_md.exists():
            report.errors.append(
                f"missing personas/{agent.agent_id}.system.md"
            )
        if not tools_json.exists():
            report.errors.append(
                f"missing personas/{agent.agent_id}.tools.json"
            )
            continue
        try:
            parsed = json.loads(tools_json.read_text())
        except json.JSONDecodeError as exc:
            report.errors.append(
                f"personas/{agent.agent_id}.tools.json: {exc}"
            )
            continue
        if not isinstance(parsed, list):
            report.errors.append(
                f"personas/{agent.agent_id}.tools.json: must be a JSON array"
            )


def _validate_mcp_consistency(
    bundle_dir: Path, gt: GTBundle, report: ValidationReport
) -> None:
    manifest = gt.mcp_tool_manifest or {}
    mcp_dir = bundle_dir / "mcp"
    if manifest and not mcp_dir.is_dir():
        report.errors.append("missing mcp/ directory (manifest is non-empty)")
        return
    for tool_name in manifest.keys():
        config_path = mcp_dir / f"{tool_name}.json"
        if not config_path.exists():
            report.errors.append(f"missing mcp/{tool_name}.json")
            continue
        try:
            parsed = json.loads(config_path.read_text())
        except json.JSONDecodeError as exc:
            report.errors.append(f"mcp/{tool_name}.json: {exc}")
            continue
        url = parsed.get("url")
        if not isinstance(url, str) or not url.endswith(f"/mcp/{tool_name}"):
            report.errors.append(
                f"mcp/{tool_name}.json: url must end in "
                f"'/mcp/{tool_name}' (got {url!r})"
            )
        if parsed.get("type") != "http":
            report.errors.append(
                f"mcp/{tool_name}.json: type must be 'http' "
                f"(got {parsed.get('type')!r})"
            )


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if len(argv) != 1:
        print(
            "usage: python -m clawsocialarena.scenario.validate <bundle_dir>",
            file=sys.stderr,
        )
        return 2
    report = validate_bundle(argv[0])
    if report.ok:
        print(f"ok: {report.bundle_dir}")
        return 0
    print(f"FAIL: {report.bundle_dir}", file=sys.stderr)
    for err in report.errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
