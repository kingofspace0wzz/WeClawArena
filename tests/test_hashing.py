from clawsocialarena.hashing import hash_action, GENESIS_HASH


def test_genesis_hash_is_64_zero_chars():
    assert GENESIS_HASH == "0" * 64


def test_hash_action_deterministic():
    payload = {"x": 1, "y": 2}
    h1 = hash_action(prev_hash=GENESIS_HASH, payload=payload)
    h2 = hash_action(prev_hash=GENESIS_HASH, payload=payload)
    assert h1 == h2
    assert len(h1) == 64


def test_hash_action_order_independent_on_payload():
    """Payload key order must not affect the hash (canonical JSON)."""
    h1 = hash_action(prev_hash=GENESIS_HASH, payload={"a": 1, "b": 2})
    h2 = hash_action(prev_hash=GENESIS_HASH, payload={"b": 2, "a": 1})
    assert h1 == h2


def test_hash_action_differs_on_prev_hash_change():
    p = {"a": 1}
    h1 = hash_action(prev_hash=GENESIS_HASH, payload=p)
    h2 = hash_action(prev_hash="1" * 64, payload=p)
    assert h1 != h2
