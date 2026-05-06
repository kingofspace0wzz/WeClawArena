"""Code Review hard-stratum task family terminal predicate (spec §4.1 / §4.2).

The code-review stratum is "hard" because it mixes a deterministic
planted-bug detection rate with an orthogonal LLM-judge review-quality
halo; the halo never enters this predicate. This module only evaluates
the deterministic half, which is what makes the task admissible to the
main SAF pipeline.

A reviewer is credited with catching a planted bug when any of the
following appears in the final review state:

- ``state["code_review"]["caught_bugs"]`` contains the bug id
- ``state["code_review"]["review_comments"]`` has an entry whose
  ``text`` field mentions the bug id as a substring

The spec declares the planted bug ids and the minimum number of bugs
that need to be caught for the review to count as successful
(``expected_quorum``).

Spec shape:

    {
        "type": "code_review_planted_bugs_caught",
        "planted_bugs": ["bug-null-deref", "bug-off-by-one", ...],
        "expected_quorum": 2
    }

When either the planted_bugs list is empty or the quorum is zero, the
predicate returns True (vacuous). When no review state exists, it
returns False.
"""

from __future__ import annotations

from typing import Any, Mapping


def code_review_planted_bugs_caught(*, state: dict, spec: dict) -> bool:
    """Return True when the review caught at least ``expected_quorum`` bugs."""
    planted = [str(x) for x in spec.get("planted_bugs") or []]
    expected_quorum = int(spec.get("expected_quorum", 0))

    if expected_quorum <= 0:
        # No quorum required -> vacuously satisfied.
        return True
    if not planted:
        # No bugs to catch but a positive quorum cannot be satisfied.
        return False

    review = state.get("code_review")
    if not isinstance(review, Mapping):
        return False

    caught: set[str] = set()
    raw_caught = review.get("caught_bugs")
    if isinstance(raw_caught, (list, tuple, set)):
        caught.update(str(x) for x in raw_caught)

    comments = review.get("review_comments")
    if isinstance(comments, (list, tuple)):
        for entry in comments:
            if not isinstance(entry, Mapping):
                continue
            text = entry.get("text")
            if not isinstance(text, str):
                continue
            for bug in planted:
                if bug in text:
                    caught.add(bug)

    hits = sum(1 for bug in planted if bug in caught)
    return hits >= expected_quorum


def _as_comment_text(value: Any) -> str | None:  # pragma: no cover - thin helper
    return value if isinstance(value, str) else None
