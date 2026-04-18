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


# --- Phase D.5 Fix 4: per-agent allowed_tools ------------------------------


def _mg_consensus_smoke_scenario() -> Scenario:
    """Three-agent consensus fixture with asymmetric tool scopes.

    The CU-scheduling template is symmetric in tools so it cannot drive a
    per-agent allocation test on its own. This fixture stands in for a
    future `MG_Consensus` template: a moderator talks to `/vote_tally`
    while voters only get the read-only `/read_feed`. It is only used by
    tests below; it is not registered in the production scenario
    registry.
    """
    return Scenario(
        scenario_id="mg-consensus-smoke",
        category="MG",
        task_family="decision",
        agents=[
            ScenarioAgent(
                agent_id="moderator",
                user_id="user-mod",
                system_prompt_template="You close the consensus round.",
                allowed_tools=["vote_tally", "read_feed"],
            ),
            ScenarioAgent(
                agent_id="voter-1",
                user_id="user-v1",
                system_prompt_template="You cast exactly one vote.",
                allowed_tools=["read_feed"],
            ),
            ScenarioAgent(
                agent_id="voter-2",
                user_id="user-v2",
                system_prompt_template="You cast exactly one vote.",
                allowed_tools=["read_feed"],
            ),
        ],
        initial_state={"votes": []},
        max_turns=6,
        opening_message={
            "from": "moderator",
            "to": "voter-1",
            "content": "Round 1 open.",
        },
    )


def test_emit_persona_tools_respects_per_agent_allowed_tools():
    """Without a caller override, per-agent `allowed_tools` are written."""
    scenario = _mg_consensus_smoke_scenario()
    files = emit_persona_files(scenario)
    mod_tools = json.loads(files["moderator.tools.json"])
    v1_tools = json.loads(files["voter-1.tools.json"])
    v2_tools = json.loads(files["voter-2.tools.json"])
    assert mod_tools == ["vote_tally", "read_feed"]
    assert v1_tools == ["read_feed"]
    assert v2_tools == ["read_feed"]
    # Privacy property: voters have no access to the tally tool.
    assert "vote_tally" not in v1_tools
    assert "vote_tally" not in v2_tools


def test_emit_persona_tools_caller_override_wins_over_agent_field():
    """The `tool_allowlist_by_agent` mapping trumps `agent.allowed_tools`."""
    scenario = _mg_consensus_smoke_scenario()
    files = emit_persona_files(
        scenario,
        tool_allowlist_by_agent={"moderator": []},
    )
    # Caller supplied an explicit empty allowlist for moderator.
    assert json.loads(files["moderator.tools.json"]) == []
    # Untouched voters still pick up their own allowed_tools.
    assert json.loads(files["voter-1.tools.json"]) == ["read_feed"]


def test_emit_persona_tools_none_field_falls_back_to_empty_without_override():
    """Legacy agents without `allowed_tools` or override keep the [] default."""
    scenario = Scenario(
        scenario_id="legacy",
        category="CU",
        task_family="scheduling",
        agents=[
            ScenarioAgent(
                agent_id="ghost",
                user_id="user-g",
                system_prompt_template="You are a legacy agent.",
            ),
        ],
        initial_state={},
        max_turns=4,
        opening_message={"from": "ghost", "to": "ghost", "content": "hi"},
    )
    files = emit_persona_files(scenario)
    assert json.loads(files["ghost.tools.json"]) == []
