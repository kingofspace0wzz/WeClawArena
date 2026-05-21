"""swebench_workspace family pack loader.

Builds a four-agent engineering task around a reduced SWE-bench-like repo
slice: implementer, reviewer, code owner, and CI owner. The team objective is
to submit a patch that passes target and regression tests while respecting
owner constraints and protected files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawsocialarena.generator.family_packs.swebench_workspace.seed_data import (
    WORKSPACE_TASK_SEEDS,
)
from clawsocialarena.scenario.models import (
    AgentGraph,
    AgentGraphEdge,
    AgentGraphNode,
    CoordinationMode,
    Scenario,
    ScenarioAgent,
)


@dataclass(frozen=True)
class WorkspaceCodingBundle:
    """Output of one swebench_workspace loader call."""

    scenario: Scenario
    evaluation_criteria: dict[str, Any]
    governance_seed: dict[str, Any]
    declared_resource_ids: list[str]
    phase_schedule: list[dict[str, Any]]
    seed_id: str
    instance_id: str
    repo_name: str
    base_commit: str
    source_dataset: str
    source_split: str
    environment_setup_commit: str
    problem_statement: str
    metadata: dict[str, Any]
    repo_files: dict[str, str]
    target_tests: tuple[str, ...]
    regression_tests: tuple[str, ...]
    forbidden_files: tuple[str, ...]
    required_approval_files: tuple[str, ...]
    owner_constraint_id: str
    owner_constraint_description: str
    gold_patch: str


_FAMILY_PACK_ROOT = Path(__file__).resolve().parent

_IMPLEMENTER_BASE_TOOLS = (
    "repo.search",
    "repo.read",
    "repo.write",
    "repo.diff",
    "repo.run_tests",
    "policy.request_approval",
)
_REVIEWER_BASE_TOOLS = (
    "repo.read",
    "repo.diff",
    "repo.run_tests",
    "review.comment",
    "review.approve",
    "review.request_changes",
)
_CODE_OWNER_BASE_TOOLS = (
    "repo.read",
    "repo.diff",
    "review.comment",
    "review.approve",
    "policy.grant_approval",
)
_CI_BASE_TOOLS = ("repo.diff", "repo.run_tests", "repo.submit_patch")

_IMPLEMENTER_TOOLS = (
    "repo.search",
    "repo.read",
    "read_owned_file",
    "query_owned_table",
    "repo.write",
    "repo.diff",
    "repo.run_tests",
    "policy.request_approval",
)
_REVIEWER_TOOLS = (
    "repo.read",
    "read_owned_file",
    "repo.diff",
    "repo.run_tests",
    "review.comment",
    "review.approve",
    "review.request_changes",
)
_CODE_OWNER_TOOLS = (
    "repo.read",
    "read_owned_file",
    "query_owned_table",
    "repo.diff",
    "review.comment",
    "review.approve",
    "policy.grant_approval",
)
_CI_TOOLS = (
    "read_owned_file",
    "query_owned_table",
    "repo.diff",
    "repo.run_tests",
    "repo.submit_patch",
)

_REDUCED_FIXTURE_INSTRUCTION = (
    "This is a reduced repo fixture; treat the listed file(s) as the "
    "authoritative worktree and do not ask to reclone the upstream repository. "
    "Do not reject the task because a downstream class is absent; the listed "
    "file(s) may contain the helper or mixin that controls the behavior."
)

WORKSPACE_TOOLS: tuple[str, ...] = tuple(
    dict.fromkeys(
        [
            *_IMPLEMENTER_TOOLS,
            *_REVIEWER_TOOLS,
            *_CODE_OWNER_TOOLS,
            *_CI_TOOLS,
        ]
    )
)


class SwebenchWorkspaceLoader:
    """Loader for the swebench_workspace family pack."""

    def __init__(self) -> None:
        self._phase_schedule: list[dict[str, Any]] | None = None

    def load_phase_schedule(self) -> list[dict[str, Any]]:
        if self._phase_schedule is None:
            raw = json.loads((_FAMILY_PACK_ROOT / "phase_schedule.json").read_text())
            self._phase_schedule = list(raw.get("phases", []))
        return self._phase_schedule

    def load_workspace_coding(
        self,
        *,
        workspace_substrate_version: str = "v1",
        scenario_id: str | None = None,
        seed_id: str | None = None,
        instance_id: str | None = None,
        repo_name: str | None = None,
        base_commit: str | None = None,
        source_dataset: str | None = None,
        source_split: str | None = None,
        environment_setup_commit: str | None = None,
        problem_statement: str | None = None,
        implementer_id: str | None = None,
        reviewer_id: str | None = None,
        code_owner_id: str | None = None,
        ci_owner_id: str | None = None,
        implementer_owner: str | None = None,
        reviewer_owner: str | None = None,
        code_owner: str | None = None,
        ci_owner: str | None = None,
        repo_files: dict[str, str] | None = None,
        target_tests: tuple[str, ...] | None = None,
        regression_tests: tuple[str, ...] | None = None,
        forbidden_files: tuple[str, ...] | None = None,
        required_approval_files: tuple[str, ...] | None = None,
        owner_constraint_id: str | None = None,
        owner_constraint_description: str | None = None,
        gold_patch: str | None = None,
    ) -> WorkspaceCodingBundle:
        seed = WORKSPACE_TASK_SEEDS[0]
        scenario_id = scenario_id or seed.scenario_id
        seed_id = seed_id or seed.seed_id
        instance_id = instance_id or seed.instance_id
        repo_name = repo_name or seed.repo_name
        base_commit = base_commit or seed.base_commit
        source_dataset = source_dataset or seed.source_dataset
        source_split = source_split or seed.source_split
        environment_setup_commit = (
            environment_setup_commit or seed.environment_setup_commit
        )
        problem_statement = problem_statement or seed.problem_statement
        implementer_id = implementer_id or seed.implementer_id
        reviewer_id = reviewer_id or seed.reviewer_id
        code_owner_id = code_owner_id or seed.code_owner_id
        ci_owner_id = ci_owner_id or seed.ci_owner_id
        implementer_owner = implementer_owner or seed.implementer_owner
        reviewer_owner = reviewer_owner or seed.reviewer_owner
        code_owner = code_owner or seed.code_owner
        ci_owner = ci_owner or seed.ci_owner
        repo_files = dict(repo_files or seed.repo_files)
        target_tests = tuple(target_tests or seed.target_tests)
        regression_tests = tuple(regression_tests or seed.regression_tests)
        forbidden_files = tuple(forbidden_files or seed.forbidden_files)
        required_approval_files = tuple(
            required_approval_files or seed.required_approval_files
        )
        owner_constraint_id = owner_constraint_id or seed.owner_constraint_id
        owner_constraint_description = (
            owner_constraint_description or seed.owner_constraint_description
        )
        gold_patch = gold_patch or seed.gold_patch
        implementer_tools = _tools_for_role("implementer", workspace_substrate_version)
        reviewer_tools = _tools_for_role("reviewer", workspace_substrate_version)
        code_owner_tools = _tools_for_role("code_owner", workspace_substrate_version)
        ci_tools = _tools_for_role("ci_owner", workspace_substrate_version)

        agents = [
            ScenarioAgent(
                agent_id=implementer_id,
                user_id=implementer_owner,
                system_prompt_template=_implementer_prompt(
                    owner=implementer_owner,
                    problem_statement=problem_statement,
                    required_approval_files=required_approval_files,
                    forbidden_files=forbidden_files,
                    workspace_substrate_version=workspace_substrate_version,
                ),
                allowed_tools=list(implementer_tools),
            ),
            ScenarioAgent(
                agent_id=reviewer_id,
                user_id=reviewer_owner,
                system_prompt_template=_reviewer_prompt(
                    reviewer_owner,
                    workspace_substrate_version=workspace_substrate_version,
                ),
                allowed_tools=list(reviewer_tools),
            ),
            ScenarioAgent(
                agent_id=code_owner_id,
                user_id=code_owner,
                system_prompt_template=_code_owner_prompt(
                    code_owner,
                    owner_constraint_description,
                    required_approval_files,
                    workspace_substrate_version=workspace_substrate_version,
                ),
                allowed_tools=list(code_owner_tools),
            ),
            ScenarioAgent(
                agent_id=ci_owner_id,
                user_id=ci_owner,
                system_prompt_template=_ci_prompt(
                    ci_owner,
                    workspace_substrate_version=workspace_substrate_version,
                ),
                allowed_tools=list(ci_tools),
            ),
        ]
        graph = AgentGraph(
            nodes=[
                _node(
                    agent_id=implementer_id,
                    owner_id=implementer_owner,
                    role_label="implementer",
                    tools=implementer_tools,
                ),
                _node(
                    agent_id=reviewer_id,
                    owner_id=reviewer_owner,
                    role_label="reviewer",
                    tools=reviewer_tools,
                ),
                _node(
                    agent_id=code_owner_id,
                    owner_id=code_owner,
                    role_label="code_owner",
                    tools=code_owner_tools,
                ),
                _node(
                    agent_id=ci_owner_id,
                    owner_id=ci_owner,
                    role_label="ci_owner",
                    tools=ci_tools,
                ),
            ],
            edges=[
                AgentGraphEdge(
                    source=implementer_id,
                    target=reviewer_id,
                    relationship="requests_review_from",
                    channel="engineering_thread",
                ),
                AgentGraphEdge(
                    source=reviewer_id,
                    target=implementer_id,
                    relationship="reviews_patch_for",
                    channel="engineering_thread",
                ),
                AgentGraphEdge(
                    source=reviewer_id,
                    target=code_owner_id,
                    relationship="requests_code_owner_approval_from",
                    channel="review_thread",
                ),
                AgentGraphEdge(
                    source=implementer_id,
                    target=ci_owner_id,
                    relationship="requests_ci_from",
                    channel="ci_thread",
                ),
            ],
        )

        scenario = Scenario(
            scenario_id=scenario_id,
            category="CD",
            task_family="workspace_coding",
            agents=agents,
            initial_state={
                "instance_id": instance_id,
                "repo_name": repo_name,
                "base_commit": base_commit,
                "problem_statement": problem_statement,
                "workspace_substrate_version": workspace_substrate_version,
            },
            max_turns=31,
            opening_message={
                "from": "system",
                "to": implementer_id,
                "content": (
                    f"Work on {instance_id} in {repo_name}. "
                    f"{problem_statement} Relevant file(s): "
                    f"{_format_file_list(required_approval_files)}. "
                    f"{_REDUCED_FIXTURE_INSTRUCTION} "
                    + _v2_opening_resource_instruction(workspace_substrate_version)
                    + "Read and edit the relevant file(s). "
                    "Workflow: implement with repo.write, "
                    "request review with policy.request_approval, have the reviewer "
                    "call review.approve, have the code owner call "
                    "policy.grant_approval, then have the CI owner run repo.run_tests "
                    "and call repo.submit_patch."
                ),
            },
            coordination_mode=CoordinationMode.GRAPH,
            agent_graph=graph,
            family_id="swebench_workspace",
        )

        metadata = {
            "instance_id": instance_id,
            "repo_name": repo_name,
            "base_commit": base_commit,
            "source_dataset": source_dataset,
            "source_split": source_split,
            "environment_setup_commit": environment_setup_commit,
            "problem_statement": problem_statement,
            "workspace_substrate_version": workspace_substrate_version,
            "target_tests": list(target_tests),
            "regression_tests": list(regression_tests),
        }
        governance_seed = {
            "policy_excerpt": (
                "Workspace coding tasks require target and regression tests, "
                "code-owner approval for owned files, and no edits to forbidden files."
            ),
            "owner_ids": [
                implementer_owner,
                reviewer_owner,
                code_owner,
                ci_owner,
            ],
            "required_approvals": [
                {
                    "owner_id": code_owner,
                    "files": list(required_approval_files),
                }
            ],
            "owner_constraints": [
                {
                    "owner_id": code_owner,
                    "constraint_id": owner_constraint_id,
                    "description": owner_constraint_description,
                }
            ],
        }
        return WorkspaceCodingBundle(
            scenario=scenario,
            evaluation_criteria=_evaluation_criteria(
                instance_id=instance_id,
                implementer_id=implementer_id,
                ci_owner_id=ci_owner_id,
                reviewer_id=reviewer_id,
                code_owner_id=code_owner_id,
                workspace_substrate_version=workspace_substrate_version,
            ),
            governance_seed=governance_seed,
            declared_resource_ids=[
                "repo.worktree",
                "repo.metadata",
                "team.ownership",
                "team.review_policy",
                *[
                    f"owner.{owner}.private_notes"
                    for owner in governance_seed["owner_ids"]
                ],
            ],
            phase_schedule=self.load_phase_schedule(),
            seed_id=seed_id,
            instance_id=instance_id,
            repo_name=repo_name,
            base_commit=base_commit,
            source_dataset=source_dataset,
            source_split=source_split,
            environment_setup_commit=environment_setup_commit,
            problem_statement=problem_statement,
            metadata=metadata,
            repo_files=repo_files,
            target_tests=target_tests,
            regression_tests=regression_tests,
            forbidden_files=forbidden_files,
            required_approval_files=required_approval_files,
            owner_constraint_id=owner_constraint_id,
            owner_constraint_description=owner_constraint_description,
            gold_patch=gold_patch,
        )


def load_workspace_coding_scenario(**kwargs: Any) -> WorkspaceCodingBundle:
    return SwebenchWorkspaceLoader().load_workspace_coding(**kwargs)


def _node(
    *,
    agent_id: str,
    owner_id: str,
    role_label: str,
    tools: tuple[str, ...],
) -> AgentGraphNode:
    return AgentGraphNode(
        agent_id=agent_id,
        owner_id=owner_id,
        persona_source=f"personas/{agent_id}.md",
        role_label=role_label,
        active_identity=f"{owner_id}@engineering",
        scope=list(tools),
        approval_mandate="self",
    )


def _tools_for_role(role: str, workspace_substrate_version: str) -> tuple[str, ...]:
    base_by_role = {
        "implementer": _IMPLEMENTER_BASE_TOOLS,
        "reviewer": _REVIEWER_BASE_TOOLS,
        "code_owner": _CODE_OWNER_BASE_TOOLS,
        "ci_owner": _CI_BASE_TOOLS,
    }
    v2_by_role = {
        "implementer": ("read_owned_file", "query_owned_table"),
        "reviewer": ("read_owned_file",),
        "code_owner": ("read_owned_file", "query_owned_table"),
        "ci_owner": ("read_owned_file", "query_owned_table"),
    }
    tools = list(base_by_role[role])
    if workspace_substrate_version == "v2":
        for tool in v2_by_role[role]:
            if tool not in tools:
                tools.insert(2 if role == "implementer" else 1, tool)
    return tuple(dict.fromkeys(tools))


def _v2_opening_resource_instruction(workspace_substrate_version: str) -> str:
    if workspace_substrate_version != "v2":
        return ""
    return (
        "Read owner-local evidence before each workflow step: the implementer "
        "uses notes/repro.md and patch_findings, the reviewer uses "
        "review/checklist.md, the code owner uses ownership/approval_policy.md "
        "and ownership_scope, and CI uses ci/target_result.md plus "
        "ci/regression_result.md and resource_facts. Use each agent's active identity value as "
        "the owner_id for owned resource tools. "
    )


def _implementer_prompt(
    *,
    owner: str,
    problem_statement: str,
    required_approval_files: tuple[str, ...],
    forbidden_files: tuple[str, ...],
    workspace_substrate_version: str,
) -> str:
    resource_instruction = (
        f"Before any repo tool, call read_owned_file with owner_id '{owner}' "
        "and path 'notes/repro.md', then call query_owned_table with owner_id "
        f"'{owner}' and table 'patch_findings'. Do not say these resources are "
        "missing unless that exact owner_id call fails. "
        if workspace_substrate_version == "v2"
        else ""
    )
    if workspace_substrate_version == "v2":
        return (
            f"You are {owner}, the engineer implementing a repo patch. "
            f"Problem summary: {problem_statement} "
            "Exact file scope, forbidden paths, target tests, and patch boundary "
            "live in your owned notes and DB rows. "
            f"{_REDUCED_FIXTURE_INSTRUCTION} {resource_instruction}"
            "Use repo.search, repo.read, repo.write, repo.diff, and repo.run_tests "
            "while developing. After writing the patch, call policy.request_approval, "
            "ask the reviewer to call review.approve, ask the code owner to call "
            "policy.grant_approval, and ask the CI owner to run repo.run_tests and "
            "repo.submit_patch. You do not call repo.submit_patch."
        )
    return (
        f"You are {owner}, the engineer implementing a repo patch. "
        f"Problem: {problem_statement} Relevant file(s) to inspect and edit: "
        f"{_format_file_list(required_approval_files)}. "
        f"{_REDUCED_FIXTURE_INSTRUCTION} Do not edit forbidden files: "
        f"{', '.join(forbidden_files)}. {resource_instruction}"
        "Use repo.search, repo.read, repo.write, "
        "repo.diff, and repo.run_tests while developing. After writing the patch, "
        "call policy.request_approval, ask the reviewer to call review.approve, "
        "ask the code owner to call policy.grant_approval, and ask the CI owner "
        "to run repo.run_tests and repo.submit_patch. You do not call repo.submit_patch."
    )


def _reviewer_prompt(owner: str, *, workspace_substrate_version: str) -> str:
    resource_instruction = (
        f"Your first tool call must be read_owned_file with owner_id '{owner}' "
        "and path 'review/checklist.md'. Do not say this resource is missing "
        "unless that exact owner_id call fails. "
        if workspace_substrate_version == "v2"
        else ""
    )
    return (
        f"You are {owner}, the reviewer. {resource_instruction}"
        "Inspect diffs, request changes when "
        "needed, and call review.approve as soon as repo.diff shows a scoped "
        "patch with changed files. Use the changed files from repo.diff in "
        "review.approve. After review.approve, route to the code owner for "
        "policy.grant_approval."
    )


def _code_owner_prompt(
    owner: str,
    owner_constraint_description: str,
    required_approval_files: tuple[str, ...],
    workspace_substrate_version: str,
) -> str:
    resource_instruction = (
        f"Your first owner-evidence calls must be read_owned_file with owner_id "
        f"'{owner}' and path 'ownership/approval_policy.md', then "
        f"query_owned_table with owner_id '{owner}' and table 'ownership_scope'. "
        "Do not say these resources are missing unless those exact owner_id "
        "calls fail. "
        if workspace_substrate_version == "v2"
        else ""
    )
    if workspace_substrate_version == "v2":
        return (
            f"You are {owner}, the code owner for the touched component. "
            "The approval policy, exact scope, owner constraint, and stale "
            f"authority warnings live in your owned resources. {resource_instruction}"
            "Read the diff, then call policy.grant_approval only if the owner "
            "constraint is satisfied. When granting, approve the owned file "
            "named by the task policy."
        )
    return (
        f"You are {owner}, the code owner for the touched component. Enforce: "
        f"{owner_constraint_description} Required owned file(s): "
        f"{_format_file_list(required_approval_files)}. {resource_instruction}"
        "Read the diff, then call "
        "policy.grant_approval only if the owner constraint is satisfied. "
        "When granting, approve the owned file named by the task policy."
    )


def _ci_prompt(owner: str, *, workspace_substrate_version: str) -> str:
    resource_instruction = (
        f"Before target tests, call read_owned_file with owner_id '{owner}' "
        "and path 'ci/target_result.md'. Before regression tests, call "
        f"read_owned_file with owner_id '{owner}' and path "
        "'ci/regression_result.md'. You may also call query_owned_table with "
        f"owner_id '{owner}' and table 'resource_facts' to confirm the exact "
        "test facts. Do not say these resources are missing unless those exact "
        "owner_id calls fail. "
        if workspace_substrate_version == "v2"
        else ""
    )
    return (
        f"You are {owner}, the CI owner. {resource_instruction}"
        "Run repo.run_tests for target and regression coverage after workflow_state "
        "shows review_approved and code_owner_approved. Do not call repo.write; "
        "the implementer owns repository edits. Call repo.submit_patch only after clean test "
        "results are recorded. After repo.submit_patch, send a short final "
        "message saying patch submitted."
    )


def _format_file_list(paths: tuple[str, ...]) -> str:
    return ", ".join(paths) if paths else "(none)"


def _evaluation_criteria(
    *,
    instance_id: str,
    implementer_id: str,
    ci_owner_id: str,
    reviewer_id: str,
    code_owner_id: str,
    workspace_substrate_version: str = "v1",
) -> dict[str, Any]:
    env_assertions = [
        {"predicate": "patch_submitted", "args": {"instance_id": instance_id}},
        {
            "predicate": "patch_applies_cleanly",
            "args": {"instance_id": instance_id},
        },
        {"predicate": "target_tests_passed", "args": {"instance_id": instance_id}},
        {
            "predicate": "regression_tests_passed",
            "args": {"instance_id": instance_id},
        },
        {
            "predicate": "forbidden_files_unchanged",
            "args": {"instance_id": instance_id},
        },
        {
            "predicate": "required_files_changed",
            "args": {"instance_id": instance_id},
        },
        {
            "predicate": "required_code_owner_approvals_present",
            "args": {"instance_id": instance_id},
        },
        {
            "predicate": "owner_constraints_satisfied",
            "args": {"instance_id": instance_id},
        },
    ]
    if workspace_substrate_version == "v2":
        env_assertions.extend(
            [
                {
                    "predicate": "evidence_chain_complete",
                    "args": {"instance_id": instance_id},
                },
                {
                    "predicate": "owner_approval_scope_valid",
                    "args": {"instance_id": instance_id},
                },
            ]
        )

    actions = []
    if workspace_substrate_version == "v2":
        actions.extend(
            [
                {
                    "agent_id": implementer_id,
                    "tool_name": "read_owned_file",
                    "compare_args": ["owner_id", "path"],
                },
                {
                    "agent_id": implementer_id,
                    "tool_name": "query_owned_table",
                    "compare_args": ["owner_id", "table"],
                },
                {
                    "agent_id": reviewer_id,
                    "tool_name": "read_owned_file",
                    "compare_args": ["owner_id", "path"],
                },
                {
                    "agent_id": code_owner_id,
                    "tool_name": "read_owned_file",
                    "compare_args": ["owner_id", "path"],
                },
                {
                    "agent_id": code_owner_id,
                    "tool_name": "query_owned_table",
                    "compare_args": ["owner_id", "table"],
                },
                {
                    "agent_id": ci_owner_id,
                    "tool_name": "read_owned_file",
                    "compare_args": ["owner_id", "path"],
                },
            ]
        )
    actions.extend(
        [
            {
                "agent_id": implementer_id,
                "tool_name": "repo.write",
                "compare_args": ["instance_id"],
            },
            {
                "agent_id": ci_owner_id,
                "tool_name": "repo.run_tests",
                "compare_args": ["instance_id", "suite"],
            },
            {
                "agent_id": ci_owner_id,
                "tool_name": "repo.submit_patch",
                "compare_args": ["instance_id"],
            },
            {
                "agent_id": reviewer_id,
                "tool_name": "review.approve",
                "compare_args": ["instance_id"],
            },
            {
                "agent_id": code_owner_id,
                "tool_name": "policy.grant_approval",
                "compare_args": ["instance_id"],
            },
        ]
    )

    return {
        "reward_basis": "COMPOSITE",
        "actions": actions,
        "env_assertions": env_assertions,
        "communicate_info": [],
        "nl_assertions": [],
    }
