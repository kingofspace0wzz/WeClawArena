"""Live executor in store-mode: reads from v2 store, writes to per-run dir."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def _fake_v2_store(tmp_path: Path) -> Path:
    """Create a minimal v2 store with one base, fully naturalized shape."""
    store = tmp_path / "store"
    base_id = "MG-A-tau2_telecom__t0"
    base_dir = store / "telecom" / base_id
    base_dir.mkdir(parents=True)
    (base_dir / "scenario.json").write_text(json.dumps({
        "scenario_id": "smoke",
        "agents": [
            {"agent_id": "leo_assistant", "user_id": "leo",
             "system_prompt_template": "You are leo."},
            {"agent_id": "maya_assistant", "user_id": "maya",
             "system_prompt_template": "You are maya."},
        ],
        "agent_graph": {"nodes": [
            {"agent_id": "leo_assistant", "role_label": "primary_account_holder",
             "owner_id": "leo"},
            {"agent_id": "maya_assistant", "role_label": "secondary_line_owner",
             "owner_id": "maya"},
        ]},
        "opening_message": {"from": "system", "to": "leo_assistant",
                             "content": "Coordinate with maya."},
        "max_turns": 4,
        "family_id": "tau2_telecom",
    }))
    (base_dir / "scenario.gt.json").write_text(json.dumps({
        "governance_manifest": {
            "governed_actions": {"a1": {"agent_id": "leo_assistant"}},
            "approval_mandates": [],
        },
        "resource_manifest": {"resources": []},
        "construction_manifest": {"family_id": "tau2_telecom"},
    }))
    (base_dir / "family_pack_context.json").write_text("{}")
    (base_dir / "naturalization_record.json").write_text(json.dumps({
        "input_hash": "sha256:fake", "naturalization_model": "gpt-5.2",
        "status": "ok",
    }))

    manifest = {
        "version": "v2.0.0",
        "n_bases": 1, "n_modes": 5, "n_variants": 5,
        "naturalization_model": "gpt-5.2",
        "rows": [
            {"variant_id": f"{base_id}__no_attacker", "base_id": base_id,
             "attack_mode": "no_attacker", "bundle_dir": f"telecom/{base_id}"},
        ],
    }
    (store / "manifest.json").write_text(json.dumps(manifest))
    return store


def test_store_mode_writes_session_db_under_run_dir(tmp_path: Path) -> None:
    """A 1-row mock run drops session.db under pilot/<run>/variants/<vid>/."""
    from clawsocialarena.orchestrator.phase5_live_executor import LiveScenarioExecutor

    store = _fake_v2_store(tmp_path)
    run_dir = tmp_path / "pilot" / "smoke"

    class _DoneNowClient:
        def create_with_tools(self, **kwargs):
            from clawsocialarena.llm.openai_client import OpenAIToolCallResult
            from clawsocialarena.llm.costing import TokenUsage
            return OpenAIToolCallResult(
                tool_calls=[], content='{"done": true}',
                usage=TokenUsage(model="m", input_tokens=10, cached_input_tokens=0,
                                  output_tokens=5),
            )

    executor = LiveScenarioExecutor(
        store_dir=store,
        run_dir=run_dir,
        agent_client=_DoneNowClient(),
        max_turns=2,
    )
    row = {
        "variant_id": "MG-A-tau2_telecom__t0__no_attacker",
        "base_id": "MG-A-tau2_telecom__t0",
        "attack_mode": "no_attacker",
        "bundle_dir": "telecom/MG-A-tau2_telecom__t0",
        "family_id": "tau2_telecom",
    }
    result = executor.execute(row=row, base_dir=store)
    assert result.error is None or result.error == ""
    variant_dir = run_dir / "variants" / row["variant_id"]
    assert (variant_dir / "phase5_session" / "session.db").is_file()


def test_persona_tool_manifests_are_applied_to_scenario_agents(
    tmp_path: Path,
) -> None:
    from clawsocialarena.orchestrator.phase5_live_executor import (
        _apply_persona_tool_manifests,
    )

    variant_dir = tmp_path / "variant"
    personas = variant_dir / "personas"
    personas.mkdir(parents=True)
    (personas / "buyer.tools.json").write_text(
        json.dumps(["read_owned_file", "record_purchase_order"]),
        encoding="utf-8",
    )
    (personas / "seller.tools.json").write_text(
        json.dumps(["read_owned_file", "record_seller_acceptance"]),
        encoding="utf-8",
    )
    scenario = {
        "agents": [
            {"agent_id": "buyer", "system_prompt_template": "Buyer."},
            {"agent_id": "seller", "system_prompt_template": "Seller."},
        ]
    }

    _apply_persona_tool_manifests(scenario, variant_dir)

    assert scenario["agents"][0]["available_tools"] == [
        "read_owned_file",
        "record_purchase_order",
    ]
    assert scenario["agents"][0]["allowed_tools"] == [
        "read_owned_file",
        "record_purchase_order",
    ]
    assert scenario["agents"][1]["available_tools"] == [
        "read_owned_file",
        "record_seller_acceptance",
    ]
    assert scenario["agents"][1]["allowed_tools"] == [
        "read_owned_file",
        "record_seller_acceptance",
    ]
