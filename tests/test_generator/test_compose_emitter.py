"""Compose emitter tests (Task D2 + Phase D.5 runtime-contract fix).

The emitter takes a `Scenario` and returns a docker-compose YAML string with:
- one service per agent plus one `gateway` service,
- every agent container on the `clawnet` bridge network,
- `CLAWSOCIAL_GATEWAY_URL=http://gateway:8080` and
  `CLAWSOCIAL_AGENT_ID=<agent_id>` injected per agent,
- the output parseable via `yaml.safe_load`.

Phase D.5 additions:
- ``build.context`` is emitted as an absolute path (the ``compose_build_root``).
- Agent services declare per-agent persona volume mounts and the shared mcp
  directory mount.
- The agent service ``command`` points at the entrypoint script, not
  ``sleep infinity``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from clawsocialarena.generator.compose_emitter import emit_compose_yaml
from clawsocialarena.scenario.models import Scenario, ScenarioAgent


def _scenario(n_agents: int) -> Scenario:
    agents = [
        ScenarioAgent(
            agent_id=f"agent-{i}",
            user_id=f"user-{i}",
            system_prompt_template="",
        )
        for i in range(n_agents)
    ]
    return Scenario(
        scenario_id="compose-emitter-test",
        category="CU",
        task_family="scheduling",
        agents=agents,
        initial_state={},
        max_turns=8,
        opening_message={"from": agents[0].agent_id, "to": agents[-1].agent_id, "content": "hi"},
    )


def test_emit_compose_yaml_has_gateway_plus_N_agents():
    scenario = _scenario(3)
    out = emit_compose_yaml(scenario)
    doc = yaml.safe_load(out)
    assert isinstance(doc, dict)
    services = doc["services"]
    # N agents + gateway => N+1 services
    assert len(services) == 3 + 1
    assert "gateway" in services
    for agent in scenario.agents:
        assert agent.agent_id in services


def test_emit_compose_yaml_service_names_match_agent_ids_exactly():
    scenario = _scenario(2)
    doc = yaml.safe_load(emit_compose_yaml(scenario))
    agent_ids = {a.agent_id for a in scenario.agents}
    non_gateway = set(doc["services"].keys()) - {"gateway"}
    assert non_gateway == agent_ids


def test_emit_compose_yaml_injects_gateway_url_and_agent_id_env():
    scenario = _scenario(2)
    doc = yaml.safe_load(emit_compose_yaml(scenario))
    for agent in scenario.agents:
        env = doc["services"][agent.agent_id]["environment"]
        # Normalize KEY=VAL list into a dict
        env_map: dict[str, str] = {}
        for item in env:
            k, _, v = item.partition("=")
            env_map[k] = v
        assert env_map["CLAWSOCIAL_GATEWAY_URL"] == "http://gateway:8080"
        assert env_map["CLAWSOCIAL_AGENT_ID"] == agent.agent_id


def test_emit_compose_yaml_uses_private_clawnet_bridge():
    scenario = _scenario(2)
    doc = yaml.safe_load(emit_compose_yaml(scenario))
    assert doc["networks"]["clawnet"]["driver"] == "bridge"
    for svc in doc["services"].values():
        assert "clawnet" in svc["networks"]


def test_emit_compose_yaml_is_deterministic_for_same_scenario():
    scenario = _scenario(2)
    a = emit_compose_yaml(scenario)
    b = emit_compose_yaml(scenario)
    assert a == b


# --- Phase D.5 additions -----------------------------------------------------


def test_emit_compose_yaml_build_context_is_absolute(tmp_path: Path):
    """build.context must be an absolute path (Phase D.5 Fix 1)."""
    scenario = _scenario(2)
    doc = yaml.safe_load(
        emit_compose_yaml(scenario, compose_build_root=tmp_path)
    )
    for svc in doc["services"].values():
        ctx = svc["build"]["context"]
        assert Path(ctx).is_absolute(), f"expected absolute path, got {ctx!r}"
        # And it should match the build root we supplied.
        assert Path(ctx) == tmp_path.resolve()


def test_emit_compose_yaml_default_build_context_is_repo_root():
    """With no explicit root, the emitter falls back to the repo root."""
    scenario = _scenario(1)
    doc = yaml.safe_load(emit_compose_yaml(scenario))
    for svc in doc["services"].values():
        ctx = Path(svc["build"]["context"])
        assert ctx.is_absolute()
        # Repo root must hold the two Dockerfiles the compose file refers to.
        assert (ctx / "docker" / "gateway.Dockerfile").exists()
        assert (ctx / "docker" / "openclaw-with-plugin.Dockerfile").exists()


def test_emit_compose_yaml_declares_persona_and_mcp_volume_mounts():
    """Each agent must mount its persona files + the shared mcp dir (Fix 1)."""
    scenario = _scenario(2)
    doc = yaml.safe_load(emit_compose_yaml(scenario))
    for agent in scenario.agents:
        volumes = doc["services"][agent.agent_id]["volumes"]
        # Volume entries are "host:container[:mode]" strings.
        joined = "\n".join(volumes)
        assert (
            f"./personas/{agent.agent_id}.system.md:/workspace/persona.system.md:ro"
            in joined
        )
        assert (
            f"./personas/{agent.agent_id}.tools.json:/workspace/persona.tools.json:ro"
            in joined
        )
        assert "./mcp:/workspace/mcp:ro" in joined


def test_emit_compose_yaml_mounts_resources_only_into_gateway():
    scenario = _scenario(2)
    doc = yaml.safe_load(emit_compose_yaml(scenario, include_resources=True))

    gateway_volumes = doc["services"]["gateway"]["volumes"]
    assert "./resources:/workspace/resources:rw" in gateway_volumes

    for agent in scenario.agents:
        volumes = doc["services"][agent.agent_id]["volumes"]
        assert not any("/workspace/resources" in item for item in volumes)


def test_emit_compose_yaml_gateway_persists_run_artifacts():
    scenario = _scenario(2)
    doc = yaml.safe_load(emit_compose_yaml(scenario))

    gateway = doc["services"]["gateway"]
    assert "./run:/workspace/run:rw" in gateway["volumes"]
    assert "./scenario.gt.json:/workspace/scenario.gt.json:ro" in gateway["volumes"]
    command = " ".join(str(part) for part in gateway["command"])
    assert "--condition passive" in command
    assert "--db-path /workspace/run/action_log.db" in command
    assert "--work-dir /workspace/run" in command
    assert "--gt-path /workspace/scenario.gt.json" in command


def test_emit_compose_yaml_gateway_receives_resource_root_when_resources_mounted():
    scenario = _scenario(2)
    doc = yaml.safe_load(emit_compose_yaml(scenario, include_resources=True))

    command = " ".join(str(part) for part in doc["services"]["gateway"]["command"])
    assert "--resource-root /workspace/resources" in command


def _svc_command_text(svc: dict) -> str:
    """Join a compose service's entrypoint + command into one string."""
    parts: list[str] = []
    for key in ("entrypoint", "command"):
        val = svc.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            parts.extend(str(v) for v in val)
        else:
            parts.append(str(val))
    return " ".join(parts)


def test_emit_compose_yaml_agent_command_is_not_sleep_infinity():
    """Fix 1: agents must launch the entrypoint script, not idle forever."""
    scenario = _scenario(2)
    doc = yaml.safe_load(emit_compose_yaml(scenario))
    for agent in scenario.agents:
        svc = doc["services"][agent.agent_id]
        joined = _svc_command_text(svc)
        assert joined, f"agent {agent.agent_id} has no entrypoint or command"
        assert "sleep infinity" not in joined
        # Positive check: entrypoint/command points at the arena's script.
        assert "agent-entrypoint.sh" in joined
