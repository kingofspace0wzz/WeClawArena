"""Document Editing hard-stratum task family terminal predicate (spec §4.1 / §4.2).

Doc-editing is "hard" because it pairs a deterministic required-fields
check (the portion evaluated here) with an orthogonal LLM coherence
halo (not attached by this predicate). Only the deterministic half
feeds SAF scoring.

Required-field matching rules:

- A field entry may provide a ``regex`` (matched with :func:`re.search`
  against the field value as a string) or a ``value`` (equality check
  against the field value after string normalization).
- When both are provided, both must hold.
- When neither is provided, the entry is treated as "presence-only"
  and the field is satisfied whenever it is present and non-empty.
- The field value is read from ``state["shared_doc"]["fields"][name]``.

Spec shape:

    {
        "type": "doc_editing_required_fields_satisfied",
        "required_fields": [
            {"name": "title", "regex": r"^\\w+$"},
            {"name": "status", "value": "approved"},
            {"name": "summary"}
        ]
    }

When ``required_fields`` is empty the predicate returns True.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


def doc_editing_required_fields_satisfied(*, state: dict, spec: dict) -> bool:
    """Return True when every required field is present and matches its rule."""
    required = list(spec.get("required_fields") or [])
    if not required:
        return True

    doc = state.get("shared_doc")
    if not isinstance(doc, Mapping):
        return False
    fields = doc.get("fields")
    if not isinstance(fields, Mapping):
        return False

    for entry in required:
        if not isinstance(entry, Mapping):
            return False
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            return False
        if name not in fields:
            return False
        value = fields.get(name)
        if value is None or (isinstance(value, str) and value == ""):
            return False
        if not _field_matches(value, entry):
            return False
    return True


def _field_matches(value: Any, entry: Mapping[str, Any]) -> bool:
    regex = entry.get("regex")
    expected_value = entry.get("value")
    if regex is None and expected_value is None:
        # Presence-only.
        return True
    text = value if isinstance(value, str) else str(value)
    if regex is not None:
        try:
            pattern = re.compile(str(regex))
        except re.error:
            return False
        if pattern.search(text) is None:
            return False
    if expected_value is not None:
        expected_text = (
            expected_value
            if isinstance(expected_value, str)
            else str(expected_value)
        )
        if text != expected_text:
            return False
    return True
