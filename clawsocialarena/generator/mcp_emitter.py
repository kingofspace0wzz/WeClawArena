"""Emit mcporter configs for a scenario's MCP tool manifest (spec §4.5).

Each tool in the scenario's ``mcp_tool_manifest`` maps to one JSON file under
``mcp/``. mcporter reads these to dial the gateway over HTTP; every tool
points at the gateway container on the shared ``clawnet`` bridge network
and the gateway routes the request to the appropriate scenario-specific MCP
server.

The emitter is a pure function: it returns ``dict[filename -> contents]``
and does not touch disk. Accepts either a ``dict[str, McpToolSpec]`` (the
form stored on ``GTBundle``) or a plain ``dict[str, dict]`` (the raw JSON
shape) so callers can use whichever is convenient.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from clawsocialarena.scenario.models import McpToolSpec


_GATEWAY_MCP_BASE = "http://gateway:8080/mcp"


def emit_mcp_configs(
    mcp_tool_manifest: Mapping[str, McpToolSpec] | Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    """Return ``{<tool_name>.json: contents}`` for the given manifest."""
    files: dict[str, str] = {}
    for tool_name in sorted(mcp_tool_manifest.keys()):
        spec = mcp_tool_manifest[tool_name]
        if isinstance(spec, McpToolSpec):
            schema = spec.input_schema
            audit_class = spec.audit_class
        else:
            schema = dict(spec.get("schema", {}))
            audit_class = str(spec["audit_class"])
        config = {
            "tool_name": tool_name,
            "type": "http",
            "url": f"{_GATEWAY_MCP_BASE}/{tool_name}",
            "schema": schema,
            "audit_class": audit_class,
        }
        files[f"{tool_name}.json"] = json.dumps(config, indent=2, sort_keys=True) + "\n"
    return files
