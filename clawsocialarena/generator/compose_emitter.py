"""Emit `docker-compose.yml` for a Scenario (spec §4.5, §A.3 / Task D2).

The emitter is a pure function: given a `Scenario`, it returns the compose
YAML text. Writing the string to disk is the orchestrator's job so the
generator can keep compose emission, persona emission, and MCP emission
side-effect-free while it assembles a bundle.

Layout:
- One gateway service on a private `clawnet` bridge network.
- One OpenClaw container per agent, each reaching the gateway by service name
  via `CLAWSOCIAL_GATEWAY_URL=http://gateway:8080` and carrying its own
  `CLAWSOCIAL_AGENT_ID` env var.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from clawsocialarena.scenario.models import Scenario

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_TEMPLATE_NAME = "compose.yml.j2"


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def emit_compose_yaml(scenario: Scenario) -> str:
    """Render `docker-compose.yml` text for the given scenario.

    The returned string is valid YAML (parseable via ``yaml.safe_load``) and
    deterministic for a given `Scenario` input.
    """
    env = _jinja_env()
    template = env.get_template(_TEMPLATE_NAME)
    return template.render(
        scenario_id=scenario.scenario_id,
        agents=[
            {
                "agent_id": agent.agent_id,
                "user_id": agent.user_id,
            }
            for agent in scenario.agents
        ],
    )
