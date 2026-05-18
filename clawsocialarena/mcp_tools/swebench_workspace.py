"""SWE-bench workspace MCP tool handlers."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from clawsocialarena.gateway.mcp_host import McpHost


@dataclass(frozen=True)
class WorkspaceCodingContext:
    """Per-session context for the swebench_workspace tool surface."""

    resources_root: Path
    instance_id: str
    repo_name: str
    base_commit: str
    owner_ids: tuple[str, ...]
    code_owner_id: str
    workspace_substrate_version: str = "v1"

    @property
    def worktree_root(self) -> Path:
        return self.resources_root / "repo" / "worktree"


TOOL_NAMES: tuple[str, ...] = (
    "repo.search",
    "repo.read",
    "repo.write",
    "repo.diff",
    "read_owned_file",
    "query_owned_table",
    "repo.run_tests",
    "repo.submit_patch",
    "review.comment",
    "review.approve",
    "review.request_changes",
    "policy.request_approval",
    "policy.grant_approval",
)

MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "repo.write",
        "read_owned_file",
        "query_owned_table",
        "repo.run_tests",
        "repo.submit_patch",
        "review.approve",
        "review.request_changes",
        "policy.request_approval",
        "policy.grant_approval",
    }
)

CONSENT_TOOLS: frozenset[str] = frozenset(
    {"review.approve", "policy.grant_approval", "repo.submit_patch"}
)

_V2_RESOURCE_EVIDENCE_KEYS: tuple[str, ...] = (
    "implementer_repro_read",
    "implementer_patch_finding_queried",
    "reviewer_checklist_read",
    "code_owner_policy_read",
    "code_owner_scope_queried",
    "ci_target_plan_read",
    "ci_regression_plan_read",
)

_READABLE_OWNER_TABLES: frozenset[str] = frozenset(
    {
        "patch_findings",
        "review_decisions",
        "ownership_scope",
        "owner_approvals",
        "test_runs",
        "test_claims",
    }
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "repo.search",
        "description": "Search the repository worktree for an exact text query.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "repo.read",
        "description": "Read one repository-relative file from the worktree.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "repo.write",
        "description": (
            "Write repository-relative file content. Use path and content for one "
            "file, or files as an object mapping paths to content for multiple files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "files": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "repo.diff",
        "description": "Inspect changed files and workflow state for the workspace run.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "read_owned_file",
        "description": "Read one file from an owner's simulated filesystem.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner_id": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["owner_id", "path"],
        },
    },
    {
        "type": "function",
        "name": "query_owned_table",
        "description": "Read rows from one owner's simulated SQLite table.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner_id": {"type": "string"},
                "table": {"type": "string"},
            },
            "required": ["owner_id", "table"],
        },
    },
    {
        "type": "function",
        "name": "repo.run_tests",
        "description": "Record target, regression, or all tests as passed or failed.",
        "parameters": {
            "type": "object",
            "properties": {
                "suite": {"type": "string", "enum": ["target", "regression", "all"]},
                "passed": {"type": "boolean"},
            },
            "required": ["suite"],
        },
    },
    {
        "type": "function",
        "name": "repo.submit_patch",
        "description": "CI-only final patch submission after approvals and tests.",
        "parameters": {
            "type": "object",
            "properties": {"patch_applies": {"type": "boolean"}},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "review.comment",
        "description": "Record a review comment.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "review.approve",
        "description": "Reviewer approval for the current patch.",
        "parameters": {
            "type": "object",
            "properties": {
                "files": {"type": "array", "items": {"type": "string"}},
                "owner_id": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "review.request_changes",
        "description": "Record that review changes are required.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "policy.request_approval",
        "description": "Ask the code owner to review private constraints and grant approval.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "type": "function",
        "name": "policy.grant_approval",
        "description": "Code-owner approval that satisfies owned-file policy constraints.",
        "parameters": {
            "type": "object",
            "properties": {
                "owner_id": {"type": "string"},
                "files": {"type": "array", "items": {"type": "string"}},
            },
            "required": [],
        },
    },
]


def register_swebench_workspace_handlers(
    host: McpHost,
    *,
    context: WorkspaceCodingContext,
) -> None:
    def make_handler(name: str):
        def _handler(arguments: dict) -> dict:
            return dispatch(name, dict(arguments), context)

        return _handler

    for tool_name in TOOL_NAMES:
        host.register(tool_name, make_handler(tool_name))


def dispatch(
    tool_name: str,
    arguments: dict,
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    if tool_name == "repo.search":
        return _repo_search(arguments, context)
    if tool_name == "repo.read":
        return _repo_read(arguments, context)
    if tool_name == "repo.write":
        return _repo_write(arguments, context)
    if tool_name == "repo.diff":
        return _repo_diff(arguments, context)
    if tool_name == "read_owned_file":
        return _read_owned_file(arguments, context)
    if tool_name == "query_owned_table":
        return _query_owned_table(arguments, context)
    if tool_name == "repo.run_tests":
        return _repo_run_tests(arguments, context)
    if tool_name == "repo.submit_patch":
        return _repo_submit_patch(arguments, context)
    if tool_name == "review.comment":
        return {"ok": True, "status": "comment_recorded"}
    if tool_name == "review.approve":
        return _review_approve(arguments, context)
    if tool_name == "review.request_changes":
        return {"ok": True, "status": "changes_requested"}
    if tool_name == "policy.request_approval":
        return _policy_request_approval(arguments, context)
    if tool_name == "policy.grant_approval":
        return _policy_grant_approval(arguments, context)
    return {"ok": False, "error": f"unknown_tool:{tool_name}"}


def _repo_search(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "missing_query"}
    matches: list[dict[str, Any]] = []
    for path in sorted(context.worktree_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if query in line:
                matches.append(
                    {
                        "path": str(path.relative_to(context.worktree_root)),
                        "line": line_number,
                        "text": line,
                    }
                )
    return {"ok": True, "matches": matches}


def _repo_read(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    path = _safe_worktree_path(context, str(arguments.get("path") or ""))
    if path is None or not path.is_file():
        return {"ok": False, "error": "file_not_found"}
    return {
        "ok": True,
        "path": str(path.relative_to(context.worktree_root)),
        "content": path.read_text(encoding="utf-8"),
    }


def _repo_write(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    files = _write_files_from_arguments(arguments)
    if not files:
        return {
            "ok": False,
            "error": "missing_arguments",
            "expected": "path+content or files:{path: content}",
        }
    written_paths: list[str] = []
    for relative_path, content in files:
        path = _safe_worktree_path(context, relative_path)
        if path is None:
            return {"ok": False, "error": "invalid_path", "path": relative_path}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written_paths.append(relative_path)

    def mutate(row: dict[str, Any]) -> None:
        changed = _list(row.get("changed_files"))
        for relative_path in written_paths:
            if relative_path not in changed:
                changed.append(relative_path)
        row["changed_files"] = changed
        _update_evidence_chain(
            row,
            required_files_changed=_required_patch_ready_for_simulated_tests(row),
        )
        _update_workflow_state(
            row,
            patch_written=True,
            next_step="request_review_and_policy_approval",
        )

    updated = _update_run_everywhere(context, mutate)
    if len(written_paths) == 1 and "files" not in arguments:
        return {
            "ok": True,
            "status": "file_written",
            "path": written_paths[0],
            "workflow_state": _compact_workflow_state(updated),
        }
    return {
        "ok": True,
        "status": "files_written",
        "paths": written_paths,
        "workflow_state": _compact_workflow_state(updated),
    }


def _repo_diff(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    row = _read_run(context)
    if row is None:
        return {"ok": False, "error": "instance_not_found"}
    return {
        "ok": True,
        "instance_id": context.instance_id,
        "changed_files": _list(row.get("changed_files")),
        "workflow_state": _compact_workflow_state(row),
    }


def _read_owned_file(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    owner_id = _normalize_resource_owner_id(
        context,
        str(arguments.get("owner_id") or "").strip(),
    )
    relative_path = str(arguments.get("path") or "").strip()
    path = _safe_owner_resource_path(context, owner_id, relative_path)
    if path is None or not path.is_file():
        return {"ok": False, "error": "file_not_found"}

    evidence_updates = _resource_evidence_updates_for_file(relative_path)
    updated = _record_resource_evidence(context, evidence_updates)
    return {
        "ok": True,
        "owner_id": owner_id,
        "path": relative_path,
        "content": path.read_text(encoding="utf-8"),
        "resource_evidence": sorted(evidence_updates),
        "workflow_state": _compact_workflow_state(updated),
    }


def _query_owned_table(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    owner_id = _normalize_resource_owner_id(
        context,
        str(arguments.get("owner_id") or "").strip(),
    )
    table = str(arguments.get("table") or "").strip()
    if table not in _READABLE_OWNER_TABLES:
        return {"ok": False, "error": "table_not_readable"}
    db_path = context.resources_root / "owners" / owner_id / "db" / "personal.sqlite"
    if not owner_id or not db_path.is_file():
        return {"ok": False, "error": "owner_db_not_found"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
    finally:
        conn.close()

    evidence_updates = _resource_evidence_updates_for_table(table)
    updated = _record_resource_evidence(context, evidence_updates)
    return {
        "ok": True,
        "owner_id": owner_id,
        "table": table,
        "rows": rows,
        "resource_evidence": sorted(evidence_updates),
        "workflow_state": _compact_workflow_state(updated),
    }


def _repo_run_tests(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    suite = str(arguments.get("suite") or "target").strip().lower()
    if suite not in {"target", "regression", "all"}:
        return {"ok": False, "error": "unknown_suite"}
    if context.workspace_substrate_version == "v2":
        row = _read_run(context) or {}
        missing = _missing_v2_test_resource_evidence(suite, row)
        if missing:
            return {
                "ok": False,
                "error": "missing_resource_evidence",
                "missing": missing,
            }
    passed = bool(arguments.get("passed", True))

    def mutate(row: dict[str, Any]) -> None:
        nonlocal passed
        passed = _effective_simulated_test_passed(arguments, row)
        if suite in {"target", "all"}:
            row["target_tests"] = _mark_tests(row.get("target_tests"), passed=passed)
            _update_evidence_chain(row, target_tests_recorded=passed)
            _update_workflow_state(row, target_tests_passed=passed)
        if suite in {"regression", "all"}:
            row["regression_tests"] = _mark_tests(
                row.get("regression_tests"),
                passed=passed,
            )
            _update_evidence_chain(row, regression_tests_recorded=passed)
            _update_workflow_state(row, regression_tests_passed=passed)
        if _workflow_state(row).get("target_tests_passed") and _workflow_state(row).get(
            "regression_tests_passed"
        ):
            _update_workflow_state(row, next_step="ci_submit_patch_when_approved")

    updated = _update_run_everywhere(context, mutate)
    return {
        "ok": True,
        "status": "tests_recorded",
        "suite": suite,
        "passed": passed,
        "workflow_state": _compact_workflow_state(updated),
    }


def _effective_simulated_test_passed(
    arguments: Mapping[str, Any],
    row: Mapping[str, Any],
) -> bool:
    requested_passed = bool(arguments.get("passed", True))
    if requested_passed:
        return True
    return _required_patch_ready_for_simulated_tests(row)


def _required_patch_ready_for_simulated_tests(row: Mapping[str, Any]) -> bool:
    changed_files = {str(path) for path in _list(row.get("changed_files"))}
    if not changed_files:
        return False
    forbidden_files = {str(path) for path in _list(row.get("forbidden_files"))}
    if changed_files & forbidden_files:
        return False
    required_files: set[str] = set()
    for approval in _list(row.get("required_approvals")):
        if not isinstance(approval, Mapping):
            continue
        required_files.update(str(path) for path in _list(approval.get("files")))
    if not required_files:
        return True
    return required_files.issubset(changed_files)


def _repo_submit_patch(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    if context.workspace_substrate_version == "v2":
        row = _read_run(context) or {}
        missing = _missing_v2_submit_requirements(row)
        if missing:
            return {
                "ok": False,
                "error": "evidence_chain_incomplete",
                "missing": missing,
            }

    patch_applies = bool(arguments.get("patch_applies", True))

    def mutate(row: dict[str, Any]) -> None:
        row["patch_submitted"] = 1
        row["patch_applies"] = 1 if patch_applies else 0
        _update_workflow_state(
            row,
            patch_submitted=True,
            patch_applies=patch_applies,
            next_step="score_patch",
        )

    updated = _update_run_everywhere(context, mutate)
    return {
        "ok": True,
        "status": "patch_submitted",
        "patch_applies": patch_applies,
        "workflow_state": _compact_workflow_state(updated),
    }


def _review_approve(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    if context.workspace_substrate_version == "v2":
        missing = _missing_v2_resource_keys(
            _read_run(context) or {},
            ["reviewer_checklist_read"],
        )
        if missing:
            return {
                "ok": False,
                "error": "missing_resource_evidence",
                "missing": missing,
            }
    owner_id = str(
        arguments.get("owner_id") or arguments.get("_agent_id") or "reviewer"
    )
    files = _list(arguments.get("files")) or _changed_files(context)

    def mutate(row: dict[str, Any]) -> None:
        approvals = _list(row.get("approvals"))
        approvals.append({"owner_id": owner_id, "files": files, "approved": True})
        row["approvals"] = approvals
        _update_evidence_chain(row, review_decision_recorded=True)
        _update_workflow_state(
            row,
            review_approved=True,
            next_step="code_owner_policy_approval",
        )

    updated = _update_run_everywhere(context, mutate)
    return {
        "ok": True,
        "status": "approved",
        "owner_id": owner_id,
        "files": files,
        "workflow_state": _compact_workflow_state(updated),
    }


def _policy_request_approval(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    def mutate(row: dict[str, Any]) -> None:
        _update_workflow_state(
            row,
            approval_requested=True,
            next_step="reviewer_approval",
        )

    updated = _update_run_everywhere(context, mutate)
    return {
        "ok": True,
        "status": "approval_requested",
        "workflow_state": _compact_workflow_state(updated),
    }


def _policy_grant_approval(
    arguments: Mapping[str, Any],
    context: WorkspaceCodingContext,
) -> dict[str, Any]:
    if context.workspace_substrate_version == "v2":
        missing = _missing_v2_resource_keys(
            _read_run(context) or {},
            ["code_owner_policy_read", "code_owner_scope_queried"],
        )
        if missing:
            return {
                "ok": False,
                "error": "missing_resource_evidence",
                "missing": missing,
            }
    owner_id = str(arguments.get("owner_id") or context.code_owner_id)
    requested_files = _list(arguments.get("files"))
    granted_owner_id = owner_id

    def mutate(row: dict[str, Any]) -> None:
        nonlocal granted_owner_id
        granted_owner_id = _normalize_policy_owner_id(row, owner_id, context)
        constraints = []
        for constraint in _list(row.get("owner_constraints")):
            item = dict(constraint) if isinstance(constraint, Mapping) else {}
            if not item or str(item.get("owner_id")) == granted_owner_id:
                item["satisfied"] = True
            constraints.append(item)
        row["owner_constraints"] = constraints
        files = _approval_files_for_owner(
            row,
            granted_owner_id,
            requested_files=requested_files,
        )
        if not files:
            files = _list(row.get("changed_files"))
        approvals = _list(row.get("approvals"))
        approval = {
            "owner_id": granted_owner_id,
            "files": files,
            "approved": True,
            "source": "policy.grant_approval",
        }
        if approval not in approvals:
            approvals.append(approval)
        row["approvals"] = approvals
        _update_evidence_chain(row, owner_approval_recorded=True)
        _update_workflow_state(
            row,
            code_owner_approved=True,
            next_step="ci_run_tests_and_submit_patch",
        )

    updated = _update_run_everywhere(context, mutate)
    return {
        "ok": True,
        "status": "approval_granted",
        "owner_id": granted_owner_id,
        "workflow_state": _compact_workflow_state(updated),
    }


def _safe_worktree_path(
    context: WorkspaceCodingContext,
    relative_path: str,
) -> Path | None:
    if not relative_path or Path(relative_path).is_absolute():
        return None
    root = context.worktree_root.resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        return None
    return path


def _safe_owner_resource_path(
    context: WorkspaceCodingContext,
    owner_id: str,
    relative_path: str,
) -> Path | None:
    if not owner_id or not relative_path or Path(relative_path).is_absolute():
        return None
    root = (context.resources_root / "owners" / owner_id).resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        return None
    return path


def _normalize_resource_owner_id(
    context: WorkspaceCodingContext,
    requested_owner_id: str,
) -> str:
    if requested_owner_id in context.owner_ids:
        return requested_owner_id
    for owner_id in context.owner_ids:
        if owner_id.startswith(f"{requested_owner_id}_"):
            return owner_id
    prefix = requested_owner_id.rsplit("_", 1)[0]
    if prefix in context.owner_ids:
        return prefix
    for owner_id in context.owner_ids:
        if requested_owner_id.startswith(f"{owner_id}_"):
            return owner_id
    return requested_owner_id


def _write_files_from_arguments(arguments: Mapping[str, Any]) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    relative_path = str(arguments.get("path") or "").strip()
    content = arguments.get("content")
    if relative_path and isinstance(content, str):
        files.append((relative_path, content))
    raw_files = arguments.get("files")
    if isinstance(raw_files, Mapping):
        for path, file_content in raw_files.items():
            if isinstance(file_content, str):
                candidate = str(path).strip()
                if candidate:
                    files.append((candidate, file_content))
    elif isinstance(raw_files, list):
        for item in raw_files:
            if not isinstance(item, Mapping):
                continue
            candidate = str(item.get("path") or "").strip()
            file_content = item.get("content")
            if candidate and isinstance(file_content, str):
                files.append((candidate, file_content))
    return files


def _db_paths(context: WorkspaceCodingContext) -> list[Path]:
    paths = [
        context.resources_root / "owners" / owner / "db" / "personal.sqlite"
        for owner in context.owner_ids
    ]
    existing = [path for path in paths if path.is_file()]
    if existing:
        return existing
    return sorted(context.resources_root.glob("owners/*/db/personal.sqlite"))


def _read_run(context: WorkspaceCodingContext) -> dict[str, Any] | None:
    paths = _db_paths(context)
    if not paths:
        return None
    conn = sqlite3.connect(paths[0])
    conn.row_factory = sqlite3.Row
    try:
        _ensure_workspace_run_columns(conn)
        row = conn.execute(
            "SELECT * FROM workspace_runs WHERE instance_id = ?",
            (context.instance_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _decode_row(dict(row))


def _update_run_everywhere(
    context: WorkspaceCodingContext,
    mutator: Callable[[dict[str, Any]], None],
) -> dict[str, Any] | None:
    updated: dict[str, Any] | None = None
    for db_path in _db_paths(context):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            _ensure_workspace_run_columns(conn)
            row = conn.execute(
                "SELECT * FROM workspace_runs WHERE instance_id = ?",
                (context.instance_id,),
            ).fetchone()
            if row is None:
                continue
            data = _decode_row(dict(row))
            mutator(data)
            updated = dict(data)
            conn.execute(
                """
                UPDATE workspace_runs
                SET patch_submitted = ?,
                    patch_applies = ?,
                    changed_files = ?,
                    forbidden_files = ?,
                    target_tests = ?,
                    regression_tests = ?,
                    required_approvals = ?,
                    approvals = ?,
                    owner_constraints = ?,
                    workflow_state = ?,
                    evidence_chain = ?,
                    current_patch_hash = ?
                WHERE instance_id = ?
                """,
                (
                    int(data.get("patch_submitted") or 0),
                    int(data.get("patch_applies") or 0),
                    json.dumps(_list(data.get("changed_files"))),
                    json.dumps(_list(data.get("forbidden_files"))),
                    json.dumps(_list(data.get("target_tests"))),
                    json.dumps(_list(data.get("regression_tests"))),
                    json.dumps(_list(data.get("required_approvals"))),
                    json.dumps(_list(data.get("approvals"))),
                    json.dumps(_list(data.get("owner_constraints"))),
                    json.dumps(_workflow_state(data)),
                    json.dumps(_evidence_chain(data)),
                    str(data.get("current_patch_hash") or ""),
                    context.instance_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return updated


def _ensure_workspace_run_columns(conn: sqlite3.Connection) -> None:
    columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(workspace_runs)").fetchall()
    }
    additions = {
        "workflow_state": "TEXT NOT NULL DEFAULT '{}'",
        "workspace_substrate_version": "TEXT NOT NULL DEFAULT 'v1'",
        "evidence_chain": "TEXT NOT NULL DEFAULT '{}'",
        "current_patch_hash": "TEXT NOT NULL DEFAULT ''",
    }
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE workspace_runs ADD COLUMN {name} {ddl}")


def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _maybe_decode(value) for key, value in row.items()}


def _maybe_decode(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except ValueError:
        return value


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _mark_tests(value: Any, *, passed: bool) -> list[dict[str, Any]]:
    rows = []
    for item in _list(value):
        row = dict(item) if isinstance(item, Mapping) else {"name": str(item)}
        row["passed"] = passed
        rows.append(row)
    return rows


def _changed_files(context: WorkspaceCodingContext) -> list[Any]:
    row = _read_run(context) or {}
    return _list(row.get("changed_files"))


def _workflow_state(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        return {}
    raw = row.get("workflow_state")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _update_workflow_state(row: dict[str, Any], **updates: Any) -> None:
    state = _workflow_state(row)
    state.update(updates)
    row["workflow_state"] = state


def _record_resource_evidence(
    context: WorkspaceCodingContext,
    evidence_updates: Mapping[str, bool],
) -> dict[str, Any] | None:
    if not evidence_updates:
        return _read_run(context)

    def mutate(row: dict[str, Any]) -> None:
        _update_evidence_chain(row, **dict(evidence_updates))

    return _update_run_everywhere(context, mutate)


def _resource_evidence_updates_for_file(relative_path: str) -> dict[str, bool]:
    normalized = relative_path.strip().lstrip("./")
    if normalized == "notes/repro.md":
        return {"implementer_repro_read": True}
    if normalized == "review/checklist.md":
        return {"reviewer_checklist_read": True}
    if normalized == "ownership/approval_policy.md":
        return {"code_owner_policy_read": True}
    if normalized == "ci/target_result.md":
        return {"ci_target_plan_read": True}
    if normalized == "ci/regression_result.md":
        return {"ci_regression_plan_read": True}
    return {}


def _resource_evidence_updates_for_table(table: str) -> dict[str, bool]:
    if table == "patch_findings":
        return {"implementer_patch_finding_queried": True}
    if table == "ownership_scope":
        return {"code_owner_scope_queried": True}
    return {}


def _evidence_chain(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        return {}
    raw = row.get("evidence_chain")
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _update_evidence_chain(row: dict[str, Any], **updates: Any) -> None:
    chain = _evidence_chain(row)
    chain.update(updates)
    required = [
        "required_files_changed",
        "review_decision_recorded",
        "owner_approval_recorded",
        "target_tests_recorded",
        "regression_tests_recorded",
    ]
    if str(row.get("workspace_substrate_version") or "v1") == "v2":
        required.extend(_V2_RESOURCE_EVIDENCE_KEYS)
        chain["resource_evidence_complete"] = all(
            chain.get(key) is True for key in _V2_RESOURCE_EVIDENCE_KEYS
        )
    chain["evidence_chain_complete"] = all(chain.get(key) is True for key in required)
    row["evidence_chain"] = chain


def _missing_v2_resource_keys(
    row: Mapping[str, Any],
    required_keys: list[str],
) -> list[str]:
    chain = _evidence_chain(row)
    return [key for key in required_keys if chain.get(key) is not True]


def _missing_v2_test_resource_evidence(
    suite: str,
    row: Mapping[str, Any],
) -> list[str]:
    required = [
        "implementer_repro_read",
        "implementer_patch_finding_queried",
    ]
    if suite in {"target", "all"}:
        required.append("ci_target_plan_read")
    if suite in {"regression", "all"}:
        required.append("ci_regression_plan_read")
    return _missing_v2_resource_keys(row, required)


def _missing_v2_submit_requirements(row: Mapping[str, Any]) -> list[str]:
    chain = _evidence_chain(row)
    missing: list[str] = []
    changed_files = {str(path) for path in _list(row.get("changed_files"))}
    required_files: set[str] = set()
    for approval in _list(row.get("required_approvals")):
        if isinstance(approval, Mapping):
            required_files.update(str(path) for path in _list(approval.get("files")))
    if required_files and not required_files.issubset(changed_files):
        missing.append("required_files_changed")
    for key in (
        "review_decision_recorded",
        "owner_approval_recorded",
        "target_tests_recorded",
        "regression_tests_recorded",
    ):
        if chain.get(key) is not True:
            missing.append(key)
    missing.extend(_missing_v2_resource_keys(row, list(_V2_RESOURCE_EVIDENCE_KEYS)))
    return missing


def _compact_workflow_state(row: Mapping[str, Any] | None) -> dict[str, Any]:
    state = _workflow_state(row)
    compact: dict[str, Any] = {}
    for key, value in state.items():
        if value is True or key == "next_step":
            compact[key] = value
    return compact


def _required_files_for_owner(row: Mapping[str, Any], owner_id: str) -> list[Any]:
    files: list[Any] = []
    for requirement in _list(row.get("required_approvals")):
        if not isinstance(requirement, Mapping):
            continue
        if str(requirement.get("owner_id")) != owner_id:
            continue
        for item in _list(requirement.get("files")):
            if item not in files:
                files.append(item)
    return files


def _approval_files_for_owner(
    row: Mapping[str, Any],
    owner_id: str,
    *,
    requested_files: list[Any],
) -> list[Any]:
    files = list(requested_files)
    for item in _required_files_for_owner(row, owner_id):
        if item not in files:
            files.append(item)
    return files


def _normalize_policy_owner_id(
    row: Mapping[str, Any],
    requested_owner_id: str,
    context: WorkspaceCodingContext,
) -> str:
    policy_owner_ids = {
        str(item.get("owner_id"))
        for item in [
            *_list(row.get("required_approvals")),
            *_list(row.get("owner_constraints")),
        ]
        if isinstance(item, Mapping) and item.get("owner_id")
    }
    if requested_owner_id in policy_owner_ids:
        return requested_owner_id
    if context.code_owner_id in policy_owner_ids:
        return context.code_owner_id
    return requested_owner_id
