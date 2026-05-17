"""TravelBench seed lifts for the travel family pack.

Each lift is one English-translated TravelBench row, plus the cell
target (`CU-D-travel` or `MG-C-travel`), the original location context,
the user_profile blocks, and a source-fidelity record that includes the
sha256 of the original Chinese query. Reviewers can verify a
translation by recomputing the sha256 from the corresponding row in
``knowledge/TravelBench/datas/{multi_turn,single_turn}.jsonl``.

The seed JSON itself lives in ``travelbench_lifts.json`` next to this
module. Regeneration is handled by ``scripts/lift_travelbench_seeds.py``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TravelBenchLift:
    """One English-translated TravelBench record.

    Fields:
        lift_id: Stable identifier of the form ``tb_<source>_<index>``.
        cell_target: ``"CU-D-travel"`` or ``"MG-C-travel"``.
        query_text: English translation of the original Chinese query.
        intent_text: English translation of the curated intent.
        primary_intent_path: The TravelBench primary_intent taxonomy
            path (e.g. ``application_interaction.notification_trigger``).
        context_block: Location and navigation context (current_city,
            current_lat, current_lon, trip_destination).
        user_profile_blocks: Translated user_profile dict; keys are
            preference axes (demographics, lodging, dining, driving, ...)
            and values are dicts of structured preferences.
        source: Source-fidelity record. Required keys: ``file``,
            ``trace_id``, ``original_query_sha256``.
    """

    lift_id: str
    cell_target: str
    query_text: str
    intent_text: str
    primary_intent_path: str
    context_block: dict[str, Any]
    user_profile_blocks: dict[str, Any]
    source: dict[str, Any]


def load_travelbench_lifts() -> tuple[TravelBenchLift, ...]:
    """Load the frozen TravelBench lifts shipped with the travel pack.

    Returns a tuple in stable, file-order so downstream seed builders
    can deterministically map lift_id -> trip_id.
    """
    path = Path(__file__).parent / "travelbench_lifts.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(TravelBenchLift(**lift) for lift in data["lifts"])


__all__ = ["TravelBenchLift", "load_travelbench_lifts"]
