"""Scenario validator (Task D9 + Phase D.5; spec §4.9 static scan).

Validates that a v2 scenario bundle on disk is internally consistent. The
checks come in two waves. The D9 wave confirms the bundle's skeleton:

1. ``scenario.json`` validates as ``Scenario``.
2. ``scenario.gt.json`` validates as ``GTBundle``.
3. ``docker-compose.yml`` parses as YAML and declares a ``services`` mapping.
4. Every agent in ``scenario.json`` has a persona ``.system.md`` plus
   ``.tools.json`` file under ``personas/``.
5. Every entry in ``gt.mcp_tool_manifest`` has a matching mcporter config
   under ``mcp/`` whose declared ``url`` points at the gateway's
   ``/mcp/<tool>`` route.

The Phase D.5 wave enforces the runtime contract that compose bring-up
will honor:

6. compose has a ``gateway`` service plus one service per scenario agent,
   and nothing else (fail on missing agent services or unknown extras).
7. Each agent service sets ``CLAWSOCIAL_GATEWAY_URL`` and
   ``CLAWSOCIAL_AGENT_ID`` in its ``environment`` block (the entrypoint
   script aborts without them).
8. ``gt.persona_manifest`` lists every scenario agent id and nothing
   else (no orphans in either direction).
9. Each ``persona.tools.json`` only references tools that are declared
   in ``gt.mcp_tool_manifest``.
10. Each compose service's ``build.context`` either resolves to an
    absolute path that exists on disk or is the literal ``.`` (which
    docker compose resolves against the compose file's own directory);
    any other relative path that cannot be resolved against the bundle
    dir is flagged.
11. Each agent service declares the expected persona + mcp volume
    mounts so the in-container OpenClaw CLI can read them.

Callers use :class:`ValidationReport` to interpret the result. CLI entry
point: ``python -m clawsocialarena.scenario.validate <bundle_dir>``.
"""

from __future__ import annotations

import json
import hashlib
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import ValidationError

from clawsocialarena.scenario.models import (
    GTBundle,
    ResourceManifest,
    ResourceType,
    Scenario,
)
from clawsocialarena.types import IntegrityLevel


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
    compose = _validate_compose_yaml(bundle_dir, report)

    if scenario is not None:
        _validate_personas(bundle_dir, scenario, report)
    if gt is not None:
        _validate_mcp_consistency(bundle_dir, gt, report)
        _validate_integrity_requirements(gt, report)
        _validate_resources(bundle_dir, gt, report)

    # Phase D.5 runtime-contract checks. Every one of these needs the
    # scenario + compose doc, so run only when both parsed cleanly.
    if scenario is not None and compose is not None:
        _validate_compose_service_shape(scenario, compose, report)
        _validate_compose_env_vars(scenario, compose, report)
        _validate_compose_build_contexts(bundle_dir, compose, report)
        _validate_compose_volume_mounts(scenario, compose, report)
        if gt is not None:
            _validate_compose_resource_mounts(scenario, gt, compose, report)

    if scenario is not None and gt is not None:
        _validate_persona_manifest_agents(scenario, gt, report)
        _validate_persona_tools_subset(bundle_dir, scenario, gt, report)
        _validate_terminal_predicate_consistency(gt, report)
        _validate_task_success_contract(scenario, gt, report)

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


def _validate_compose_yaml(
    bundle_dir: Path, report: ValidationReport
) -> dict | None:
    """Parse docker-compose.yml and surface its dict form on success."""
    path = bundle_dir / "docker-compose.yml"
    if not path.exists():
        report.errors.append("missing docker-compose.yml")
        return None
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        report.errors.append(f"docker-compose.yml: unparseable YAML: {exc}")
        return None
    if not isinstance(doc, dict) or "services" not in doc:
        report.errors.append(
            "docker-compose.yml: missing top-level 'services' mapping"
        )
        return None
    if not isinstance(doc["services"], dict) or not doc["services"]:
        report.errors.append(
            "docker-compose.yml: 'services' must be a non-empty mapping"
        )
        return None
    return doc


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


def _validate_integrity_requirements(gt: GTBundle, report: ValidationReport) -> None:
    valid_levels = {int(level) for level in IntegrityLevel}
    for action_type, level in gt.integrity_requirements.items():
        if level not in valid_levels:
            report.errors.append(
                "scenario.gt.json: integrity_requirements"
                f"[{action_type!r}]={level!r} is outside declared "
                f"IntegrityLevel values {sorted(valid_levels)}"
            )


# --- Phase D.5 runtime-contract checks ---------------------------------------


def _env_map(env_block: Any) -> dict[str, str]:
    """Normalize a compose `environment:` block into a `{K: V}` dict.

    Compose accepts both the list form (``["K=V", "K2=V2"]``) and the
    mapping form (``{K: V, K2: V2}``). The validator treats them as
    equivalent.
    """
    result: dict[str, str] = {}
    if env_block is None:
        return result
    if isinstance(env_block, dict):
        for k, v in env_block.items():
            result[str(k)] = "" if v is None else str(v)
        return result
    if isinstance(env_block, list):
        for item in env_block:
            if not isinstance(item, str):
                continue
            k, _, v = item.partition("=")
            result[k] = v
    return result


def _volume_entries(volume_block: Any) -> list[str]:
    """Return compose `volumes:` entries as a flat list of strings.

    Only the short syntax (``"host:container[:mode]"``) is normalized. The
    long-form mapping is rare in arena bundles and surfaces as ``""`` so
    downstream checks flag it as not matching the expected mount.
    """
    out: list[str] = []
    if volume_block is None:
        return out
    if isinstance(volume_block, list):
        for item in volume_block:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                src = str(item.get("source", ""))
                dst = str(item.get("target", ""))
                mode = "ro" if item.get("read_only") else "rw"
                out.append(f"{src}:{dst}:{mode}")
    return out


def _validate_compose_service_shape(
    scenario: Scenario, compose: dict, report: ValidationReport
) -> None:
    """Fix 3.1: exactly one gateway + one service per scenario agent."""
    services = compose.get("services", {})
    if not isinstance(services, dict):
        return  # Already reported in _validate_compose_yaml.
    service_names = set(services.keys())
    if "gateway" not in service_names:
        report.errors.append(
            "docker-compose.yml: missing required 'gateway' service"
        )
    expected_agents = {a.agent_id for a in scenario.agents}
    missing_agents = expected_agents - service_names
    for agent_id in sorted(missing_agents):
        report.errors.append(
            f"docker-compose.yml: missing service for agent {agent_id!r}"
        )
    # Anything that isn't `gateway` or an agent id is an unknown extra.
    extras = service_names - expected_agents - {"gateway"}
    for name in sorted(extras):
        report.errors.append(
            f"docker-compose.yml: unexpected service {name!r} "
            f"(not in scenario.agents and not 'gateway')"
        )


def _validate_compose_env_vars(
    scenario: Scenario, compose: dict, report: ValidationReport
) -> None:
    """Fix 3.2: each agent service sets the two required env vars."""
    services = compose.get("services", {})
    if not isinstance(services, dict):
        return
    for agent in scenario.agents:
        svc = services.get(agent.agent_id)
        if not isinstance(svc, dict):
            continue  # Already flagged by the shape check.
        env = _env_map(svc.get("environment"))
        if "CLAWSOCIAL_GATEWAY_URL" not in env:
            report.errors.append(
                f"docker-compose.yml: service {agent.agent_id!r} is "
                f"missing CLAWSOCIAL_GATEWAY_URL env var"
            )
        if env.get("CLAWSOCIAL_AGENT_ID") != agent.agent_id:
            report.errors.append(
                f"docker-compose.yml: service {agent.agent_id!r} must set "
                f"CLAWSOCIAL_AGENT_ID={agent.agent_id!r} "
                f"(got {env.get('CLAWSOCIAL_AGENT_ID')!r})"
            )


def _validate_compose_build_contexts(
    bundle_dir: Path, compose: dict, report: ValidationReport
) -> None:
    """Fix 3.5: build.context must be absolute + existing, or literal `.`.

    Any other relative path that cannot be resolved against the bundle
    directory is flagged because ``docker compose`` would fail to build
    the image at that path.
    """
    services = compose.get("services", {})
    if not isinstance(services, dict):
        return
    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        build = svc.get("build")
        if build is None:
            # image-only services don't carry a build stanza.
            continue
        context: str | None
        if isinstance(build, str):
            context = build
        elif isinstance(build, dict):
            context = build.get("context")
        else:
            context = None
        if context is None:
            report.errors.append(
                f"docker-compose.yml: service {name!r} has a build stanza "
                f"without a context"
            )
            continue
        if not isinstance(context, str):
            report.errors.append(
                f"docker-compose.yml: service {name!r} build.context must "
                f"be a string (got {type(context).__name__})"
            )
            continue
        ctx_path = Path(context)
        if ctx_path.is_absolute():
            if not ctx_path.exists():
                report.errors.append(
                    f"docker-compose.yml: service {name!r} build.context "
                    f"is an absolute path that does not exist: {context}"
                )
            continue
        # `.` is explicitly allowed -- compose resolves it relative to the
        # compose file's own directory, which every bundle owns.
        if context == ".":
            continue
        # Any other relative path must resolve against the bundle dir.
        resolved = (bundle_dir / ctx_path).resolve()
        if not resolved.exists():
            report.errors.append(
                f"docker-compose.yml: service {name!r} build.context "
                f"{context!r} does not resolve from bundle dir "
                f"(tried {resolved})"
            )


def _validate_compose_volume_mounts(
    scenario: Scenario, compose: dict, report: ValidationReport
) -> None:
    """Fix 3.6: each agent has the expected persona + mcp mounts."""
    services = compose.get("services", {})
    if not isinstance(services, dict):
        return
    for agent in scenario.agents:
        svc = services.get(agent.agent_id)
        if not isinstance(svc, dict):
            continue
        volumes = _volume_entries(svc.get("volumes"))
        expected: Iterable[str] = (
            f"./personas/{agent.agent_id}.system.md:/workspace/persona.system.md:ro",
            f"./personas/{agent.agent_id}.tools.json:/workspace/persona.tools.json:ro",
            "./mcp:/workspace/mcp:ro",
        )
        for want in expected:
            if want not in volumes:
                report.errors.append(
                    f"docker-compose.yml: service {agent.agent_id!r} is "
                    f"missing expected volume mount {want!r}"
                )


def _validate_persona_manifest_agents(
    scenario: Scenario, gt: GTBundle, report: ValidationReport
) -> None:
    """Fix 3.3: persona_manifest keys match scenario.agents exactly."""
    manifest_ids = set(gt.persona_manifest.keys())
    scenario_ids = {a.agent_id for a in scenario.agents}
    missing = scenario_ids - manifest_ids
    for agent_id in sorted(missing):
        report.errors.append(
            f"scenario.gt.json: persona_manifest missing entry for "
            f"agent {agent_id!r}"
        )
    extras = manifest_ids - scenario_ids
    for agent_id in sorted(extras):
        report.errors.append(
            f"scenario.gt.json: persona_manifest has entry for "
            f"{agent_id!r} which is not in scenario.agents"
        )
    # Internal consistency: each entry's own agent_id matches the key.
    for key, ref in gt.persona_manifest.items():
        if ref.agent_id != key:
            report.errors.append(
                f"scenario.gt.json: persona_manifest[{key!r}].agent_id "
                f"is {ref.agent_id!r} (must equal the key)"
            )


def _validate_persona_tools_subset(
    bundle_dir: Path,
    scenario: Scenario,
    gt: GTBundle,
    report: ValidationReport,
) -> None:
    """Fix 3.4: .tools.json only references declared MCP tool names."""
    allowed = set(gt.mcp_tool_manifest.keys())
    personas_dir = bundle_dir / "personas"
    if not personas_dir.is_dir():
        return  # Already reported by _validate_personas.
    for agent in scenario.agents:
        tools_json = personas_dir / f"{agent.agent_id}.tools.json"
        if not tools_json.exists():
            continue  # Already flagged.
        try:
            parsed = json.loads(tools_json.read_text())
        except json.JSONDecodeError:
            continue  # Already flagged.
        if not isinstance(parsed, list):
            continue
        for tool_name in parsed:
            if tool_name not in allowed:
                report.errors.append(
                    f"personas/{agent.agent_id}.tools.json: references "
                    f"tool {tool_name!r} not declared in "
                    f"gt.mcp_tool_manifest"
                )


def _validate_resources(
    bundle_dir: Path, gt: GTBundle, report: ValidationReport
) -> None:
    manifest = gt.resource_manifest
    if manifest is None:
        return

    resources_dir = bundle_dir / "resources"
    if not resources_dir.is_dir():
        report.errors.append("missing resources/ directory")
        return

    sidecar_path = resources_dir / "manifest.json"
    if not sidecar_path.exists():
        report.errors.append("missing resources/manifest.json")
        return
    try:
        sidecar = json.loads(sidecar_path.read_text())
    except json.JSONDecodeError as exc:
        report.errors.append(f"resources/manifest.json: {exc}")
        return

    try:
        sidecar_manifest = ResourceManifest.model_validate(sidecar)
    except ValidationError as exc:
        report.errors.append(f"resources/manifest.json: {exc}")
        return

    if sidecar_manifest != manifest:
        report.errors.append(
            "resources/manifest.json does not match scenario.gt.json "
            "resource_manifest"
        )

    for resource_id, entry in manifest.resources.items():
        for rule in entry.allowed_operations:
            for operation in rule.operations:
                if operation not in gt.mcp_tool_manifest:
                    report.errors.append(
                        f"resource {resource_id!r} declares operation "
                        f"{operation!r} not present in gt.mcp_tool_manifest"
                    )
            if gt.governance_manifest is not None:
                if (
                    rule.identity_id is not None
                    and rule.identity_id not in gt.governance_manifest.identities
                ):
                    report.errors.append(
                        f"resource {resource_id!r} references unknown "
                        f"identity {rule.identity_id!r}"
                    )
                if (
                    rule.scope_id is not None
                    and rule.scope_id not in gt.governance_manifest.authorization_scopes
                ):
                    report.errors.append(
                        f"resource {resource_id!r} references unknown "
                        f"scope {rule.scope_id!r}"
                    )

        if gt.governance_manifest is not None and (
            entry.owner_id not in gt.governance_manifest.owners
        ):
            report.errors.append(
                f"resource {resource_id!r} references unknown owner "
                f"{entry.owner_id!r}"
            )

        if entry.resource_type in {
            ResourceType.FILE,
            ResourceType.DIRECTORY,
            ResourceType.SQLITE_DB,
            ResourceType.TABLE,
            ResourceType.ROW_SET,
        }:
            if entry.path is None:
                report.errors.append(f"resource {resource_id!r} is missing path")
                continue
            try:
                path = _safe_resource_path(resources_dir, entry.path)
            except ValueError as exc:
                report.errors.append(f"resource {resource_id!r}: {exc}")
                continue

            if entry.resource_type == ResourceType.FILE:
                _validate_file_resource(resource_id, path, entry.initial_digest, report)
            elif entry.resource_type == ResourceType.DIRECTORY:
                if not path.is_dir():
                    report.errors.append(
                        f"resource {resource_id!r}: directory path does not exist"
                    )
            else:
                _validate_sqlite_resource(resource_id, path, entry.table, report)


def _validate_task_success_contract(
    scenario: Scenario,
    gt: GTBundle,
    report: ValidationReport,
) -> None:
    manifest = gt.construction_manifest
    if manifest is None:
        report.errors.append(
            "scenario.gt.json: scenarios require construction_manifest "
            "with task schema v0"
        )
        return
    if manifest.task_schema_version != "clawsocialarena-task-v0":
        report.errors.append(
            "scenario.gt.json: construction_manifest task_schema_version "
            "must be 'clawsocialarena-task-v0' "
            f"(got {manifest.task_schema_version!r})"
        )
        return

    required = {
        "designed_difficulty_tier": manifest.designed_difficulty_tier,
        "actors": manifest.actors,
        "benign_task_objective": manifest.benign_task_objective,
        "task_success_spec": manifest.task_success_spec,
        "audit_events": manifest.audit_events,
        "source_pattern": manifest.source_pattern,
    }
    for field_name, value in required.items():
        if value is None or value == []:
            report.errors.append(
                "scenario.gt.json: task schema v0 missing "
                f"{field_name}"
            )

    if manifest.designed_difficulty_tier not in {
        "easy",
        "realistic",
        "stress",
    }:
        report.errors.append(
            "scenario.gt.json: task schema v0 designed_difficulty_tier "
            f"is invalid: {manifest.designed_difficulty_tier!r}"
        )

    scenario_agent_ids = {agent.agent_id for agent in scenario.agents}
    for actor in manifest.actors:
        if actor.agent_id not in scenario_agent_ids:
            report.errors.append(
                "scenario.gt.json: task schema v0 actor "
                f"{actor.agent_id!r} is not in scenario.agents"
            )
    for index, event in enumerate(manifest.audit_events):
        if not event.visibility:
            report.errors.append(
                "scenario.gt.json: task schema v0 audit_events"
                f"[{index}].visibility must be non-empty"
            )
        if event.required_log_level is None:
            report.errors.append(
                "scenario.gt.json: task schema v0 audit_events"
                f"[{index}].required_log_level must be set"
            )

    success = manifest.task_success_spec
    if success is None:
        return
    if success.completion_mode not in {
        "tool_backed",
        "structured_message",
        "resource_state",
    }:
        report.errors.append(
            "scenario.gt.json: task_success_spec.completion_mode is invalid: "
            f"{success.completion_mode!r}"
        )
    if not success.reward_basis:
        report.errors.append(
            "scenario.gt.json: task_success_spec.reward_basis must be non-empty"
        )
    expected_terminal_type = _task_success_terminal_type(gt.terminal_predicate)
    if (
        expected_terminal_type
        and success.terminal_predicate_type != expected_terminal_type
    ):
        report.errors.append(
            "scenario.gt.json: task_success_spec.terminal_predicate_type "
            f"{success.terminal_predicate_type!r} does not match terminal "
            f"predicate {expected_terminal_type!r}"
        )


def _validate_terminal_predicate_consistency(
    gt: GTBundle,
    report: ValidationReport,
) -> None:
    terminal = gt.terminal_predicate
    if terminal.get("type") != "scheduling_pinned_slot":
        return
    participants = _terminal_string_list(terminal.get("participants"))
    required_participants = _terminal_string_list(
        terminal.get("required_participants")
    )
    if not participants or not required_participants:
        return
    if required_participants != participants:
        report.errors.append(
            "scenario.gt.json: terminal_predicate.required_participants "
            "must match terminal_predicate.participants for scheduling tasks"
        )


def _terminal_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _task_success_terminal_type(terminal_predicate: dict[str, Any]) -> str:
    task_success = terminal_predicate.get("task_success")
    if isinstance(task_success, dict) and isinstance(task_success.get("type"), str):
        return str(task_success["type"])
    terminal_type = terminal_predicate.get("type")
    return str(terminal_type) if isinstance(terminal_type, str) else ""


def _validate_file_resource(
    resource_id: str,
    path: Path,
    initial_digest: str | None,
    report: ValidationReport,
) -> None:
    if not path.is_file():
        report.errors.append(f"resource {resource_id!r}: file path does not exist")
        return
    if initial_digest is None:
        return
    actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != initial_digest:
        report.errors.append(
            f"resource {resource_id!r}: initial_digest mismatch "
            f"(expected {initial_digest}, got {actual})"
        )


def _validate_sqlite_resource(
    resource_id: str,
    path: Path,
    table: str | None,
    report: ValidationReport,
) -> None:
    if not path.is_file():
        report.errors.append(f"resource {resource_id!r}: SQLite path does not exist")
        return
    if table is None:
        return
    try:
        with sqlite3.connect(path) as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
    except sqlite3.Error as exc:
        report.errors.append(f"resource {resource_id!r}: SQLite error: {exc}")
        return
    if exists is None:
        report.errors.append(
            f"resource {resource_id!r}: SQLite table {table!r} does not exist"
        )


def _safe_resource_path(root: Path, relative_path: str) -> Path:
    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"path escapes resources/: {relative_path!r}")
    resolved = (root / rel).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes resources/: {relative_path!r}")
    return resolved


def _validate_compose_resource_mounts(
    scenario: Scenario,
    gt: GTBundle,
    compose: dict,
    report: ValidationReport,
) -> None:
    if gt.resource_manifest is None:
        return
    services = compose.get("services", {})
    if not isinstance(services, dict):
        return
    gateway = services.get("gateway", {})
    gateway_volumes = _volume_entries(
        gateway.get("volumes") if isinstance(gateway, dict) else None
    )
    if "./resources:/workspace/resources:rw" not in gateway_volumes:
        report.errors.append(
            "docker-compose.yml: gateway is missing expected resource mount "
            "'./resources:/workspace/resources:rw'"
        )
    for agent in scenario.agents:
        svc = services.get(agent.agent_id)
        if not isinstance(svc, dict):
            continue
        for volume in _volume_entries(svc.get("volumes")):
            if "/workspace/resources" in volume:
                report.errors.append(
                    f"docker-compose.yml: service {agent.agent_id!r} must not "
                    "mount raw resources"
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
