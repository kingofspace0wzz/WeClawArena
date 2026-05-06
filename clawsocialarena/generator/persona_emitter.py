"""Emit `personas/<agent_id>.system.md` + `<agent_id>.tools.json` per agent.

Spec §4.5 requires one persona prompt file and one allowed-tool manifest per
agent in each scenario bundle. The emitter is a pure function returning a
``dict[filename -> contents]`` so the orchestrator controls disk layout and
the generator stays side-effect-free.

Conventions:
- `.system.md` starts with an H1 carrying the runtime agent id for tooling,
  followed by the persona prompt body. It intentionally omits backing user ids
  from agent-facing text; those ids remain in `scenario.json` and GT metadata.
- `.tools.json` is a JSON array of tool names. Phase D.5 Fix 4 wires the
  per-agent allowlist: when the caller passes a per-agent list, only that
  subset lands in the file. Agents that are not in the mapping and do not
  carry an ``allowed_tools`` override still default to an empty list, which
  is the safest choice for "tools.json required, but no explicit scope".
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
        Optional per-agent list of tool names the agent may invoke. When
        supplied, it takes precedence over any ``allowed_tools`` set on
        the ``ScenarioAgent`` itself (the CLI uses this seam to route
        ``mcp_tool_manifest`` + ``allowed_tools`` into a single call).
        Missing agents fall back to the agent's own ``allowed_tools``
        field; if that is ``None`` too, the emitter writes ``[]`` so
        ``.tools.json`` remains a valid JSON array.
    """
    overrides = dict(tool_allowlist_by_agent or {})
    files: dict[str, str] = {}
    for agent in scenario.agents:
        files[f"{agent.agent_id}.system.md"] = _render_system_md(
            agent_id=agent.agent_id,
            user_id=agent.user_id,
            body=agent.system_prompt_template,
        )
        if agent.agent_id in overrides:
            tools = list(overrides[agent.agent_id])
        elif agent.allowed_tools is not None:
            tools = list(agent.allowed_tools)
        else:
            tools = []
        files[f"{agent.agent_id}.tools.json"] = json.dumps(tools, indent=2) + "\n"
    return files


def _render_system_md(*, agent_id: str, user_id: str, body: str) -> str:
    """Render the persona Markdown for one agent."""
    body = body.rstrip("\n")
    return (
        f"# {agent_id}\n"
        f"\n"
        f"## Persona prompt\n"
        f"\n"
        f"{body}\n"
    )
