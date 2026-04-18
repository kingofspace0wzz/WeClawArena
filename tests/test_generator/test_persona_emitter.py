"""Persona emitter tests (Task D3).

The emitter returns a dict[filename -> contents] so the orchestrator can
decide where to write on disk. Per agent we emit:

- `<agent_id>.system.md`  -- Markdown-formatted persona prompt.
- `<agent_id>.tools.json` -- the allowed tool manifest for that agent, a
  subset of the scenario's MCP bundle.
"""

from __future__ import annotations

import json

from clawsocialarena.generator.persona_emitter import emit_persona_files
from clawsocialarena.scenario.models import Scenario, ScenarioAgent


def _scenario() -> Scenario:
    return Scenario(
        scenario_id="persona-emitter-test",
        category="CU",
        task_family="scheduling",
        agents=[
            ScenarioAgent(
                agent_id="alice",
                user_id="user-a",
                system_prompt_template=(
                    "You are Alice's personal agent. Pin a 1-hour slot."
                ),
            ),
            ScenarioAgent(
                agent_id="bob",
                user_id="user-b",
                system_prompt_template="You are Bob's personal agent.",
            ),
        ],
        initial_state={},
        max_turns=8,
        opening_message={"from": "alice", "to": "bob", "content": "hi"},
    )


def test_emit_persona_files_returns_two_files_per_agent():
    scenario = _scenario()
    files = emit_persona_files(scenario)
    assert "alice.system.md" in files
    assert "alice.tools.json" in files
    assert "bob.system.md" in files
    assert "bob.tools.json" in files
    # Exactly 2 files per agent
    assert len(files) == 2 * len(scenario.agents)


def test_emit_persona_system_md_contains_agent_id_and_prompt():
    scenario = _scenario()
    files = emit_persona_files(scenario)
    alice_md = files["alice.system.md"]
    # The Markdown body surfaces the agent id + the persona prompt body.
    assert "alice" in alice_md
    assert "Alice's personal agent" in alice_md


def test_emit_persona_tools_json_is_valid_json_array():
    scenario = _scenario()
    files = emit_persona_files(scenario)
    parsed = json.loads(files["alice.tools.json"])
    # Default: no allowlist given -> empty list
    assert parsed == []


def test_emit_persona_tools_honors_per_agent_allowlist():
    scenario = _scenario()
    allowlist = {
        "alice": ["calendar"],
        "bob": ["calendar", "ledger"],
    }
    files = emit_persona_files(scenario, tool_allowlist_by_agent=allowlist)
    assert json.loads(files["alice.tools.json"]) == ["calendar"]
    assert json.loads(files["bob.tools.json"]) == ["calendar", "ledger"]


def test_emit_persona_files_is_deterministic():
    scenario = _scenario()
    a = emit_persona_files(scenario)
    b = emit_persona_files(scenario)
    assert a == b
