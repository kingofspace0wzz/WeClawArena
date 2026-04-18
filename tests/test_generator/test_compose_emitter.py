"""Compose emitter tests (Task D2).

The emitter takes a `Scenario` and returns a docker-compose YAML string with:
- one service per agent plus one `gateway` service,
- every agent container on the `clawnet` bridge network,
- `CLAWSOCIAL_GATEWAY_URL=http://gateway:8080` and
  `CLAWSOCIAL_AGENT_ID=<agent_id>` injected per agent,
- the output parseable via `yaml.safe_load`.
"""

from __future__ import annotations

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
