"""Lift TravelBench source records into English-translated travel-pack seeds.

Companion script for Task 1 of the travel first-ship plan
(`docs/superpowers/plans/travel/2026-05-16-travel-family-first-ship.md`).
The shipped `travelbench_lifts.json` was produced by translating six
TravelBench rows (3 for `CU-D-travel`, 3 for `MG-C-travel`) into
English and structuring the user_profile / context blocks. The
translation work was performed by an LLM in a Claude Code session;
this script does NOT call an LLM at runtime. Its responsibilities:

1. Re-verify the sha256 of each shipped lift against the corresponding
   row in `knowledge/TravelBench/datas/{multi_turn,single_turn}.jsonl`.
2. Print a manifest of which TravelBench rows feed which lifts.
3. Provide a hook (`pick_candidate_traces`) that lists TravelBench
   trace_ids matching the lift criteria (rich user_profile for MG,
   discrete bookable intent for CU), so future plan iterations can
   regenerate the lift pool with a different LLM if needed.

Run:
    python scripts/lift_travelbench_seeds.py [--verify-only]

Selection criteria (from the plan):
    CU-D-travel: prefer discrete bookable actions (hotel, route + hotel,
        specific lodging request); rich user_profile is helpful but not
        required (single_turn rows have none and still work).
    MG-C-travel: require populated user_profile of >= 1000 characters
        so each co_traveler agent can be seeded with distinct private
        constraints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
TRAVELBENCH_DATA = REPO_ROOT / "knowledge" / "TravelBench" / "datas"
SHIPPED_LIFTS = (
    REPO_ROOT
    / "clawsocialarena"
    / "generator"
    / "family_packs"
    / "travel"
    / "seed_data"
    / "travelbench_lifts.json"
)


def iter_source_rows(filename: str) -> Iterator[dict]:
    """Yield every row in a TravelBench source file."""
    with (TRAVELBENCH_DATA / filename).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def fetch_row(filename: str, trace_id: str) -> dict:
    """Return the row in ``filename`` with the given ``trace_id``."""
    for row in iter_source_rows(filename):
        if str(row["trace_id"]) == str(trace_id):
            return row
    raise KeyError(f"trace_id={trace_id!r} not found in {filename!r}")


def verify_lift(lift: dict) -> tuple[bool, str]:
    """Recompute the sha256 of the source query and compare to the lift."""
    src = lift["source"]
    row = fetch_row(src["file"], src["trace_id"])
    digest = hashlib.sha256(row["query"].encode("utf-8")).hexdigest()
    if digest != src["original_query_sha256"]:
        return False, (
            f"{lift['lift_id']}: source query sha256 mismatch "
            f"(shipped={src['original_query_sha256']!r}, computed={digest!r}). "
            "Either the source row changed or the translation was based on a "
            "different query string."
        )
    return True, f"{lift['lift_id']}: source fidelity OK"


def pick_candidate_traces(
    filename: str,
    *,
    require_profile_chars: int = 0,
    require_intent_keywords: Iterable[str] = (),
    limit: int = 20,
) -> list[tuple[str, str]]:
    """Return up to ``limit`` (trace_id, intent) candidates matching the filters.

    This helper is used to refresh the candidate pool when adding more
    lifts; it does NOT mutate the shipped lifts.
    """
    keywords = tuple(k for k in require_intent_keywords)
    out: list[tuple[str, str]] = []
    for row in iter_source_rows(filename):
        intent = row.get("intent", "")
        profile = row.get("user_profile", "") or ""
        if len(profile) < require_profile_chars:
            continue
        if keywords and not any(k in intent for k in keywords):
            continue
        out.append((row["trace_id"], intent))
        if len(out) >= limit:
            break
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify source-fidelity of shipped lifts; do not list candidates.",
    )
    args = parser.parse_args()

    data = json.loads(SHIPPED_LIFTS.read_text(encoding="utf-8"))
    lifts = data["lifts"]

    print(f"Verifying {len(lifts)} shipped lifts ...")
    ok_count = 0
    for lift in lifts:
        ok, message = verify_lift(lift)
        print(f"  {'OK' if ok else 'FAIL'}: {message}")
        if ok:
            ok_count += 1
    print(f"Verification: {ok_count}/{len(lifts)} lifts match their source rows.")

    if args.verify_only:
        return 0 if ok_count == len(lifts) else 1

    print()
    print("Candidate MG lifts (multi_turn rows with rich user_profile):")
    for trace_id, intent in pick_candidate_traces(
        "multi_turn.jsonl",
        require_profile_chars=1000,
        require_intent_keywords=("景区", "景点", "酒店", "出游", "推荐"),
        limit=8,
    ):
        print(f"  trace {trace_id}: {intent[:80]}")

    print()
    print("Candidate CU lifts (single_turn or multi_turn with bookable intent):")
    for trace_id, intent in pick_candidate_traces(
        "single_turn.jsonl",
        require_intent_keywords=("酒店", "宾馆", "民宿"),
        limit=8,
    ):
        print(f"  single_turn trace {trace_id}: {intent[:80]}")

    return 0 if ok_count == len(lifts) else 1


if __name__ == "__main__":
    sys.exit(main())
