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

Build contexts
--------------
``docker compose`` resolves relative build contexts against the compose
file's own directory. Because scenario bundles live at arbitrary depths
(``benchmark/scenarios/<scenario_id>/docker-compose.yml``,
``/tmp/gen_test/<scenario_id>/docker-compose.yml``, etc.), the emitter takes
an explicit ``compose_build_root`` and writes an **absolute** path into each
service's ``build.context``. Absolute paths resolve identically no matter
where the compose file ends up, which eliminates the depth ambiguity that
the Phase D review flagged. The caller (typically
``clawsocialarena.generator.cli``) is responsible for picking the right
root -- usually the repo root so the gateway + OpenClaw Dockerfiles see
their expected source trees.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from clawsocialarena.scenario.models import Scenario

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_TEMPLATE_NAME = "compose.yml.j2"

# The compose emitter defaults to the repo root so `python -m
# clawsocialarena.generator.cli` produces a bundle that builds the same
# images as ``docker/compose-templates/minimal.yml``. Callers that generate
# bundles against a different source tree pass ``compose_build_root``
# explicitly.
_DEFAULT_BUILD_ROOT = Path(__file__).resolve().parents[2]


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def emit_compose_yaml(
    scenario: Scenario,
    *,
    compose_build_root: Path | str | None = None,
) -> str:
    """Render `docker-compose.yml` text for the given scenario.

    Arguments
    ---------
    scenario:
        The scenario whose gateway + agent services are being emitted.
    compose_build_root:
        Directory that every service's ``build.context`` points at. The
        emitter resolves it to an absolute path before rendering so the
        emitted YAML stays valid regardless of where the compose file is
        written. Defaults to the repo root inferred from this module's
        on-disk location.

    The returned string is valid YAML (parseable via ``yaml.safe_load``) and
    deterministic for a given ``(scenario, compose_build_root)`` pair.
    """
    root = (
        Path(compose_build_root).resolve()
        if compose_build_root is not None
        else _DEFAULT_BUILD_ROOT
    )
    env = _jinja_env()
    template = env.get_template(_TEMPLATE_NAME)
    return template.render(
        scenario_id=scenario.scenario_id,
        build_context=str(root),
        agents=[
            {
                "agent_id": agent.agent_id,
                "user_id": agent.user_id,
            }
            for agent in scenario.agents
        ],
    )
