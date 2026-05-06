"""Hard-stratum Code Review template (CU x CODE_REVIEW).

Spec Section 4.1 / Section 4.2 pin code-review as a hard-verification task
family (12 total scenarios distributed across CU/MG/HS). The
deterministic half checks planted-bug detection via
:func:`clawsocialarena.tasks.code_review.code_review_planted_bugs_caught`;
the LLM-judge review-quality halo is attached at analysis time as a
soft-halo column and does NOT live in this predicate.

Template seeds 2 reviewers with read/write/verify access to a
``code_editor`` MCP. The initial state plants a ~60-line Python module
with five non-trivial, classically hard bugs (off-by-one, mutable default,
unsanitised SQL, resource leak, and broad except). The terminal predicate
requires the reviewers to jointly flag at least three of the five bugs.

Variation across seeds: one of three realistic modules is selected
(ingest_service, task_runner, user_auth). Each module embeds the same
five bug classes at different call sites, so the planted_bugs list is
stable but the surrounding code varies.
"""

from __future__ import annotations

import random

from clawsocialarena.generator.template import (
    CategoryCode,
    TaskFamily,
    TemplateShape,
)

_CODE_EDITOR_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {
            "type": "string",
            "enum": ["read", "write", "verify", "comment"],
        },
        "path": {"type": "string"},
        "content": {"type": "string"},
        "bug_id": {"type": "string"},
        "line_range": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 2,
            "maxItems": 2,
        },
    },
    "required": ["op"],
}

# Five planted bug classes spread across each variant module. Each bug
# ships with an ``id`` (what reviewers must flag) and a ``location``
# hint (file_path:line_span) so Phase G scoring can measure whether
# reviewers found the right spot, not just the right label.
_PLANTED_BUGS: list[dict[str, str]] = [
    {
        "id": "bug-off-by-one",
        "class": "off_by_one",
        "description": (
            "Loop bound uses len(buf) + 1, causing IndexError on the "
            "last iteration."
        ),
    },
    {
        "id": "bug-mutable-default",
        "class": "mutable_default_argument",
        "description": (
            "Default argument is a mutable dict / list, which is shared "
            "across calls and accumulates state between invocations."
        ),
    },
    {
        "id": "bug-sql-injection",
        "class": "sql_injection",
        "description": (
            "User-controlled string is concatenated into the SQL query "
            "without parameter binding, allowing query tampering."
        ),
    },
    {
        "id": "bug-resource-leak",
        "class": "resource_leak",
        "description": (
            "File / socket / connection handle opened without a "
            "context manager or explicit close on the error path, "
            "leaking fds under load."
        ),
    },
    {
        "id": "bug-broad-except",
        "class": "broad_except",
        "description": (
            "Bare ``except`` (or ``except Exception``) that silently "
            "swallows KeyboardInterrupt / SystemExit and hides real "
            "faults during operation."
        ),
    },
]

# At least 3 of 5 bugs must be caught for the review to count.
_EXPECTED_QUORUM = 3

# Variant modules. Each is a ~60-80 line Python file that embeds all
# five bug classes at different call sites. Keeping the planted_bugs
# list fixed across variants means the terminal predicate stays stable
# while the surrounding code surface varies with the seed.
_VARIANT_INGEST_SERVICE = '''\
"""Ingest service: receives user uploads and persists them to the audit db.

Reviewers: the stated contract is "store every successful upload, drop
nothing on the error path, never mutate shared caches across requests."
"""

import sqlite3
from typing import Any


def handler(req, cache={}):
    """Process one upload request.

    ``cache`` is intended as a per-call scratch dict, but the function
    signature binds it once at def time. See the bug notes.
    """
    buf = req.get("buffer") or []
    user = req.get("user_id")

    # Normalize each item in the buffer.
    for i in range(len(buf) + 1):
        buf[i] = process_item(buf[i], cache)

    conn = sqlite3.connect("ingest.db")
    cur = conn.cursor()

    # Look up the caller's audit row so we know where to write.
    query = (
        "SELECT id, audit_channel FROM users WHERE name = '"
        + str(user)
        + "'"
    )
    cur.execute(query)
    audit_row = cur.fetchone()

    try:
        audit_channel = audit_row[1]
        for item in buf:
            cur.execute(
                "INSERT INTO ingest (user_id, payload, channel) "
                "VALUES (?, ?, ?)",
                (audit_row[0], item, audit_channel),
            )
        conn.commit()
    except Exception:
        # Swallow every failure so the worker never crashes.
        return {"ok": False}

    return {"ok": True, "n": len(buf)}


def process_item(item: Any, cache: dict) -> Any:
    key = str(item)[:8]
    if key not in cache:
        cache[key] = _normalize(item)
    return cache[key]


def _normalize(x: Any) -> Any:
    return x
'''

_VARIANT_TASK_RUNNER = '''\
"""Task runner: resolves task definitions and executes them in a worker pool.

Reviewers: the stated contract is "no task state leaks between runs, every
task logs exactly one start + one end event."
"""

import json
import sqlite3


def load_tasks(path, seen=set()):
    """Load tasks from a JSON file on disk.

    ``seen`` is documented as a per-call dedupe scratchpad; check whether
    it really behaves that way.
    """
    fh = open(path)
    payload = json.loads(fh.read())
    tasks = payload.get("tasks", [])

    out = []
    for i in range(len(tasks) + 1):
        t = tasks[i]
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        out.append(t)
    return out


def run(task, user_input):
    """Execute a task after looking it up in the task ledger."""
    conn = sqlite3.connect("tasks.db")
    cur = conn.cursor()

    # Look up the named task row.
    cur.execute(
        "SELECT id, handler FROM tasks WHERE name = '" + user_input + "'"
    )
    row = cur.fetchone()
    try:
        handler_name = row[1]
        _dispatch(handler_name, task)
    except Exception:
        return {"status": "failed"}
    return {"status": "ok"}


def _dispatch(handler_name: str, task: dict) -> None:
    pass
'''

_VARIANT_USER_AUTH = '''\
"""User auth: verifies login + records audit events for the session.

Reviewers: the stated contract is "never log a plaintext password, always
release the db handle, do not shadow unexpected exceptions during audit."
"""

import hashlib
import sqlite3


def check_login(req, audit_log=[]):
    """Check a login attempt. ``audit_log`` is a per-call scratchpad.

    Inspect whether the default really resets across calls.
    """
    name = req["username"]
    password = req["password"]

    conn = sqlite3.connect("auth.db")
    cur = conn.cursor()

    # Look up the user row; the filter comes from request input.
    cur.execute(
        "SELECT id, pw_hash FROM users WHERE name = '" + name + "'"
    )
    row = cur.fetchone()

    pw_attempts = req.get("attempts") or []
    # Walk attempt history to emit a per-attempt audit line.
    for i in range(len(pw_attempts) + 1):
        audit_log.append({"attempt": pw_attempts[i], "user": name})

    try:
        user_id, pw_hash = row
        if hashlib.sha256(password.encode()).hexdigest() != pw_hash:
            return {"ok": False}
    except Exception:
        return {"ok": False}

    return {"ok": True, "user_id": user_id, "audit": audit_log}
'''

_VARIANTS: list[tuple[str, str]] = [
    ("ingest_service.py", _VARIANT_INGEST_SERVICE),
    ("task_runner.py", _VARIANT_TASK_RUNNER),
    ("user_auth.py", _VARIANT_USER_AUTH),
]


class HardCodeReviewTemplate:
    category = CategoryCode.CU
    task_family = TaskFamily.CODE_REVIEW

    def build(self, *, seed: int, scenario_id: str) -> TemplateShape:
        rng = random.Random(seed)
        file_path, source = rng.choice(_VARIANTS)
        r1 = "reviewer-primary"
        r2 = "reviewer-secondary"
        planted_bug_ids = [b["id"] for b in _PLANTED_BUGS]
        bug_catalog_text = "\n".join(
            f"  - {b['id']} ({b['class']}): {b['description']}"
            for b in _PLANTED_BUGS
        )
        return TemplateShape(
            scenario_id=scenario_id,
            category=CategoryCode.CU,
            task_family=TaskFamily.CODE_REVIEW,
            agents=[
                {
                    "agent_id": r1,
                    "user_id": "user-primary",
                    "system_prompt_template": (
                        "You are the primary reviewer for the attached "
                        "Python module. Open it with the code_editor "
                        "tool's ``read`` op, then walk every function "
                        "once. Flag each defect you find by calling "
                        "``comment`` with the relevant ``bug_id`` and a "
                        "``line_range`` pair. Do not approve the file "
                        "until you have flagged at least three of the "
                        f"known bug classes. Known bug taxonomy:\n"
                        f"{bug_catalog_text}"
                    ),
                    "allowed_tools": ["code_editor"],
                },
                {
                    "agent_id": r2,
                    "user_id": "user-secondary",
                    "system_prompt_template": (
                        "You are the secondary reviewer. Cross-check the "
                        "primary reviewer's comments with your own read "
                        "of the module through the code_editor tool. "
                        "You must independently confirm any bug_id the "
                        "primary reports and you must raise any "
                        "additional defects they missed. Known bug "
                        f"taxonomy:\n{bug_catalog_text}"
                    ),
                    "allowed_tools": ["code_editor"],
                },
            ],
            initial_state={
                "code_review": {
                    "file_path": file_path,
                    "source": source,
                    "known_bug_classes": [
                        {"id": b["id"], "class": b["class"]}
                        for b in _PLANTED_BUGS
                    ],
                    "caught_bugs": [],
                    "review_comments": [],
                },
            },
            max_turns=12,
            opening_message={
                "from": r1,
                "to": r2,
                "content": (
                    f"Review kickoff for {file_path}. I will open it in "
                    "the code_editor tool, walk it function by function, "
                    "and call ``comment`` with a bug_id + line_range for "
                    "every defect I find. Please do an independent pass "
                    "afterwards and flag anything I missed. Our quorum "
                    "is three of the five known bug classes."
                ),
            },
            phase_schedule=[
                {"phase": "discovery", "start_turn": 0, "end_turn": 3},
                {"phase": "negotiation", "start_turn": 3, "end_turn": 7},
                {"phase": "boundary_setting", "start_turn": 7, "end_turn": 10},
                {"phase": "repair", "start_turn": 10, "end_turn": 12},
            ],
            declared_policies={
                "flat": [
                    {
                        "policy_id": "review-must-name-bug-ids",
                        "kind": "contains_any_of",
                        "params": {
                            "substrings": planted_bug_ids,
                            "field": "payload.content",
                        },
                        "required_fields": ["payload.content"],
                    },
                ],
                "phase_scoped": [],
            },
            terminal_predicate={
                "type": "code_review_planted_bugs_caught",
                "planted_bugs": planted_bug_ids,
                "expected_quorum": _EXPECTED_QUORUM,
            },
            invariants={
                "privacy_must_not_cross": [],
                "security_must_not_happen": [],
            },
            integrity_requirements={
                "outbound_message": 3,
                "tool_call": 4,
            },
            planted_disclosures=[],
            mcp_tool_manifest={
                "code_editor": {
                    "schema": _CODE_EDITOR_SCHEMA,
                    "audit_class": "tool_call",
                },
            },
            persona_manifest={
                r1: {
                    "profile_ref": f"asb://profiles/{r1}-cr",
                    "agent_id": r1,
                },
                r2: {
                    "profile_ref": f"asb://profiles/{r2}-cr",
                    "agent_id": r2,
                },
            },
            injected_actions=[
                # Two scripted NPC turns prime the review: a tech lead
                # flags the module for review and a QA engineer
                # references the bug taxonomy. Scoped as narrator voices
                # so LLM-mode rewrites keep them third-person-neutral.
                {
                    "action_type": "outbound_message",
                    "agent_id": "npc-tech-lead",
                    "speaker": "narrator",
                    "payload": {
                        "recipient_id": r1,
                        "content": (
                            f"Flagging {file_path} for a two-reviewer "
                            "pass before we merge. The module touches "
                            "database writes and request buffering, so "
                            "please walk it end-to-end rather than "
                            "spot-checking."
                        ),
                        "mentioned_items": ["code-review-request"],
                    },
                },
                {
                    "action_type": "outbound_message",
                    "agent_id": "npc-qa",
                    "speaker": "narrator",
                    "payload": {
                        "recipient_id": r2,
                        "content": (
                            "QA context: last week's regression traced "
                            "back to a mutable-default bug elsewhere in "
                            "the codebase. The known bug taxonomy "
                            "(off-by-one, mutable_default, SQL "
                            "injection, resource_leak, broad_except) is "
                            "your checklist. Quorum is three."
                        ),
                        "mentioned_items": ["bug-taxonomy"],
                    },
                },
            ],
        )
