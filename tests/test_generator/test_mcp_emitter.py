"""MCP emitter tests (Task D4).

The emitter takes the scenario's ``mcp_tool_manifest`` (as declared on the
GT bundle) and emits one mcporter config file per tool. Each config points
at the gateway container as the MCP host.
"""

from __future__ import annotations

import json

from clawsocialarena.generator.mcp_emitter import emit_mcp_configs
from clawsocialarena.scenario.models import McpToolSpec


def _manifest() -> dict[str, McpToolSpec]:
    return {
        "calendar": McpToolSpec(
            schema={
                "type": "object",
                "properties": {"slot": {"type": "string"}},
                "required": ["slot"],
            },
            audit_class="outbound_message",
        ),
        "ledger": McpToolSpec(
            schema={"type": "object"},
            audit_class="side_channel",
        ),
    }


def test_emit_mcp_configs_one_file_per_tool():
    files = emit_mcp_configs(_manifest())
    assert set(files.keys()) == {"calendar.json", "ledger.json"}


def test_emit_mcp_configs_point_at_gateway_http_mcp():
    files = emit_mcp_configs(_manifest())
    for name, content in files.items():
        parsed = json.loads(content)
        tool = name.removesuffix(".json")
        assert parsed["type"] == "http"
        assert parsed["url"] == f"http://gateway:8080/mcp/{tool}"


def test_emit_mcp_configs_preserves_schema_and_audit_class():
    files = emit_mcp_configs(_manifest())
    calendar = json.loads(files["calendar.json"])
    assert calendar["tool_name"] == "calendar"
    assert calendar["schema"]["properties"]["slot"]["type"] == "string"
    assert calendar["audit_class"] == "outbound_message"

    ledger = json.loads(files["ledger.json"])
    assert ledger["audit_class"] == "side_channel"


def test_emit_mcp_configs_accepts_dict_input():
    """For convenience, a dict[str, dict] is also accepted (matches JSON)."""
    dict_manifest = {
        "calendar": {
            "schema": {"type": "object"},
            "audit_class": "outbound_message",
        },
    }
    files = emit_mcp_configs(dict_manifest)
    assert "calendar.json" in files
    parsed = json.loads(files["calendar.json"])
    assert parsed["audit_class"] == "outbound_message"


def test_emit_mcp_configs_empty_manifest_returns_empty_dict():
    assert emit_mcp_configs({}) == {}


def test_emit_mcp_configs_is_deterministic():
    a = emit_mcp_configs(_manifest())
    b = emit_mcp_configs(_manifest())
    assert a == b
