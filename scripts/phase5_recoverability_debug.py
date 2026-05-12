"""Debug helper for SAF recoverability divergence (Codex R-B 2 rerun blocker 2).

Computes the per-row recoverability score using the same formula as
:mod:`clawsocialarena.saf.scorers.recoverability`, plus the row-level
diff: which (agent_id, action_id) keys appear in the shadow but not in
the primary action log, and which appear in both but with mismatched
content. Run with::

    python scripts/phase5_recoverability_debug.py \\
        benchmark/phase5/scaffold/CD-A-marble_research/task1/tier1/phase5_session/session.db

The script prints the score and the top 10 missing / mismatched rows.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def _content_hash(rec: dict) -> str:
    envelope = {
        "agent_id": rec["agent_id"],
        "action_id": rec["action_id"],
        "action_type": rec["action_type"],
        "timestamp": rec["timestamp"],
        "execution_phase": rec["execution_phase"],
        "social_phase": rec["social_phase"],
        "payload": json.loads(rec["payload_json"]),
        "integrity_level": int(rec["integrity_level"]),
        "signature": rec.get("signature"),
    }
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_actions(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT agent_id, action_id, action_type, timestamp, "
            "execution_phase, social_phase, payload_json, integrity_level, "
            "signature FROM actions ORDER BY row_id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def main(primary_path: Path) -> int:
    shadow_path = primary_path.parent / f"{primary_path.stem}.shadow.db"
    if not primary_path.is_file():
        print(f"missing primary log: {primary_path}", file=sys.stderr)
        return 2
    if not shadow_path.is_file():
        print(f"missing shadow log: {shadow_path}", file=sys.stderr)
        return 2

    primary = _read_actions(primary_path)
    shadow = _read_actions(shadow_path)

    def _key(rec: dict) -> tuple[str, str, str]:
        return (rec["agent_id"], rec["action_id"], _content_hash(rec))

    primary_keys = {_key(r) for r in primary}
    shadow_keys = {_key(r) for r in shadow}

    score = (
        len(primary_keys & shadow_keys) / len(shadow_keys)
        if shadow_keys
        else 1.0
    )

    primary_id_pairs = {(r["agent_id"], r["action_id"]) for r in primary}
    shadow_id_pairs = {(r["agent_id"], r["action_id"]) for r in shadow}

    shadow_only_id_pairs = shadow_id_pairs - primary_id_pairs
    primary_only_id_pairs = primary_id_pairs - shadow_id_pairs
    intersect_id_pairs = primary_id_pairs & shadow_id_pairs

    by_type_primary: dict[str, int] = {}
    by_type_shadow: dict[str, int] = {}
    for rec in primary:
        by_type_primary[rec["action_type"]] = (
            by_type_primary.get(rec["action_type"], 0) + 1
        )
    for rec in shadow:
        by_type_shadow[rec["action_type"]] = (
            by_type_shadow.get(rec["action_type"], 0) + 1
        )

    print(f"PRIMARY  rows: {len(primary)}  unique (agent,id): {len(primary_id_pairs)}")
    print(f"SHADOW   rows: {len(shadow)}  unique (agent,id): {len(shadow_id_pairs)}")
    print()
    print("action_type counts (primary | shadow | delta = shadow - primary):")
    for action_type in sorted(set(by_type_primary) | set(by_type_shadow)):
        p = by_type_primary.get(action_type, 0)
        s = by_type_shadow.get(action_type, 0)
        print(f"  {action_type:30s}  {p:4d}  {s:4d}  delta={s - p:+d}")
    print()
    print(f"id-pair overlap (primary && shadow):      {len(intersect_id_pairs)}")
    print(f"shadow-only id pairs:                     {len(shadow_only_id_pairs)}")
    print(f"primary-only id pairs:                    {len(primary_only_id_pairs)}")
    print()
    print(f"content-hash overlap (primary ∩ shadow):  {len(primary_keys & shadow_keys)}")
    print(f"recoverability = overlap / |shadow|:      {score:.4f}")
    print()

    shadow_by_pair = {(r["agent_id"], r["action_id"]): r for r in shadow}
    primary_by_pair = {(r["agent_id"], r["action_id"]): r for r in primary}

    if shadow_only_id_pairs:
        print("sample shadow-only rows (top 10):")
        for pair in sorted(shadow_only_id_pairs)[:10]:
            rec = shadow_by_pair[pair]
            payload = rec["payload_json"][:160]
            print(
                f"  - agent={pair[0]}  action_id={pair[1]}  "
                f"type={rec['action_type']}  payload={payload}"
            )
        print()

    if primary_only_id_pairs:
        print("sample primary-only rows (top 10):")
        for pair in sorted(primary_only_id_pairs)[:10]:
            rec = primary_by_pair[pair]
            payload = rec["payload_json"][:160]
            print(
                f"  - agent={pair[0]}  action_id={pair[1]}  "
                f"type={rec['action_type']}  payload={payload}"
            )
        print()

    content_mismatches: list[tuple[tuple[str, str], dict, dict]] = []
    for pair in intersect_id_pairs:
        if _content_hash(primary_by_pair[pair]) != _content_hash(shadow_by_pair[pair]):
            content_mismatches.append(
                (pair, primary_by_pair[pair], shadow_by_pair[pair])
            )
    if content_mismatches:
        print(
            f"content-hash mismatches on shared id pairs: {len(content_mismatches)}"
        )
        for pair, p_rec, s_rec in content_mismatches[:5]:
            print(f"  - {pair[0]}/{pair[1]} type={p_rec['action_type']}")
            print(f"      primary payload: {p_rec['payload_json'][:160]}")
            print(f"      shadow  payload: {s_rec['payload_json'][:160]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "usage: python scripts/phase5_recoverability_debug.py <session.db>",
            file=sys.stderr,
        )
        raise SystemExit(1)
    raise SystemExit(main(Path(sys.argv[1])))
