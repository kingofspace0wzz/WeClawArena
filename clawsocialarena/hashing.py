"""Hash-chain helpers for the append-only action log."""

import hashlib
import json
from typing import Any

GENESIS_HASH: str = "0" * 64


def hash_action(*, prev_hash: str, payload: dict[str, Any]) -> str:
    """Return the SHA-256 hash of (prev_hash || canonical(payload)).

    Payload is canonicalized via sorted-keys JSON so that key order is irrelevant.
    """

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256()
    h.update(prev_hash.encode("ascii"))
    h.update(canonical.encode("utf-8"))
    return h.hexdigest()
