"""Emit `personas/<agent_id>.system.md` + `<agent_id>.tools.json` per agent.

Spec §4.5 requires one persona prompt file and one allowed-tool manifest per
agent in each scenario bundle. The emitter is a pure function returning a
``dict[filename -> contents]`` so the orchestrator controls disk layout and
the generator stays side-effect-free.

Conventions:
- `.system.md` starts with an H1 carrying the agent id, followed by the
  persona prompt body. Downstream tooling can parse the H1 as the agent id
  without relying on filenames.
- `.tools.json` is a JSON array of tool names. Empty by default; the CLI
  passes a per-agent allowlist when the scenario's MCP bundle is scoped to
  subsets of agents.
"""

from __future__ import annotations

import json
from typing import Mapping

from clawsocialarena.scenario.models import Scenario


def emit_persona_files(
    scenario: Scenario,
    *,
    tool_allowlist_by_agent: Mapping[str, list[str]] | None = None,
) -> dict[str, str]:
    """Return ``{filename: contents}`` for the scenario's persona bundle.

    Arguments
    ---------
    scenario:
        The scenario to emit personas for. One pair of files is emitted per
        ``ScenarioAgent``.
    tool_allowlist_by_agent:
        Optional per-agent list of tool names the agent may invoke. Missing
        agents default to an empty list.
    """
    allowlist = dict(tool_allowlist_by_agent or {})
    files: dict[str, str] = {}
    for agent in scenario.agents:
        files[f"{agent.agent_id}.system.md"] = _render_system_md(
            agent_id=agent.agent_id,
            user_id=agent.user_id,
            body=agent.system_prompt_template,
        )
        tools = list(allowlist.get(agent.agent_id, []))
        files[f"{agent.agent_id}.tools.json"] = json.dumps(tools, indent=2) + "\n"
    return files


def _render_system_md(*, agent_id: str, user_id: str, body: str) -> str:
    """Render the persona Markdown for one agent."""
    body = body.rstrip("\n")
    return (
        f"# {agent_id}\n"
        f"\n"
        f"Scenario agent id: `{agent_id}`\n"
        f"Backing user id: `{user_id}`\n"
        f"\n"
        f"## Persona prompt\n"
        f"\n"
        f"{body}\n"
    )
