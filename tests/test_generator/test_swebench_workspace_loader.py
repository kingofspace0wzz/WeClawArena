"""Tests for the swebench_workspace family pack loader."""

from __future__ import annotations

from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
)
from clawsocialarena.orchestrator.phase5_agent_loop import discover_tool_schemas
from clawsocialarena.scenario.models import CoordinationMode


def test_workspace_scenario_has_engineering_team_roles() -> None:
    bundle = load_workspace_coding_scenario()
    scenario = bundle.scenario
    assert scenario.family_id == "swebench_workspace"
    assert scenario.coordination_mode == CoordinationMode.GRAPH
    roles = {node.role_label for node in scenario.agent_graph.nodes}
    assert roles == {"implementer", "reviewer", "code_owner", "ci_owner"}


def test_workspace_evaluation_names_patch_test_and_owner_predicates() -> None:
    bundle = load_workspace_coding_scenario()
    actions = {
        (item["agent_id"], item["tool_name"])
        for item in bundle.evaluation_criteria["actions"]
    }
    assert actions == {
        ("maya_engineer", "repo.write"),
        ("priya_ci", "repo.run_tests"),
        ("priya_ci", "repo.submit_patch"),
        ("nolan_reviewer", "review.approve"),
        ("opal_owner", "policy.grant_approval"),
    }
    predicates = {
        item["predicate"] for item in bundle.evaluation_criteria["env_assertions"]
    }
    assert predicates == {
        "patch_submitted",
        "patch_applies_cleanly",
        "target_tests_passed",
        "regression_tests_passed",
        "forbidden_files_unchanged",
        "required_files_changed",
        "required_code_owner_approvals_present",
        "owner_constraints_satisfied",
    }
    assert bundle.evaluation_criteria["communicate_info"] == []


def test_workspace_phase_schedule_uses_runner_schema() -> None:
    bundle = load_workspace_coding_scenario()
    for phase in bundle.phase_schedule:
        assert {"phase", "start_turn", "end_turn"}.issubset(phase)


def test_workspace_prompts_define_handoff_contract_and_turn_cap() -> None:
    bundle = load_workspace_coding_scenario()
    prompts = {
        agent.agent_id: agent.system_prompt_template for agent in bundle.scenario.agents
    }
    assert bundle.scenario.max_turns == 31
    assert "policy.request_approval" in prompts["maya_engineer"]
    assert "do not call repo.submit_patch" in prompts["maya_engineer"]
    assert "review.approve" in prompts["nolan_reviewer"]
    assert "policy.grant_approval" in prompts["opal_owner"]
    assert "repo.submit_patch" in prompts["priya_ci"]
    assert "repo.submit_patch" in bundle.scenario.opening_message["content"]


def test_workspace_prompt_names_required_file_without_gold_patch() -> None:
    bundle = load_workspace_coding_scenario()
    required_file = bundle.required_approval_files[0]
    prompts = {
        agent.agent_id: agent.system_prompt_template for agent in bundle.scenario.agents
    }

    assert required_file in bundle.scenario.opening_message["content"]
    assert required_file in prompts["maya_engineer"]
    assert required_file in prompts["opal_owner"]
    assert "reduced repo fixture" in bundle.scenario.opening_message["content"]
    assert "reduced repo fixture" in prompts["maya_engineer"]
    assert "Do not reject the task because a downstream class is absent" in (
        bundle.scenario.opening_message["content"]
    )
    assert "Do not reject the task because a downstream class is absent" in (
        prompts["maya_engineer"]
    )
    assert "cright[-right.shape[0]:, -right.shape[1]:] = right" not in (
        bundle.scenario.opening_message["content"]
    )
    assert "cright[-right.shape[0]:, -right.shape[1]:] = right" not in (
        prompts["maya_engineer"]
    )


def test_workspace_tool_schemas_are_discoverable() -> None:
    schemas = {
        schema["name"]: schema
        for schema in discover_tool_schemas(
            family_id="swebench_workspace",
            tool_names=["repo.write", "repo.run_tests", "repo.submit_patch"],
        )
    }
    assert set(schemas) == {"repo.write", "repo.run_tests", "repo.submit_patch"}
    write_props = schemas["repo.write"]["parameters"]["properties"]
    assert {"path", "content", "files"}.issubset(write_props)
    assert "suite" in schemas["repo.run_tests"]["parameters"]["properties"]


def test_workspace_bundle_keeps_gold_patch_out_of_public_metadata() -> None:
    bundle = load_workspace_coding_scenario()
    assert bundle.gold_patch
    assert "gold_patch" not in bundle.metadata
    assert bundle.instance_id == "astropy__astropy-12907"
    assert bundle.metadata["source_dataset"] == "princeton-nlp/SWE-bench_Lite"
    assert bundle.metadata["source_split"] == "test"
