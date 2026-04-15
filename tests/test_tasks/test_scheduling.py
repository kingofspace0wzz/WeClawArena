from clawsocialarena.tasks.scheduling import scheduling_pinned_slot


def test_accepts_valid_slot():
    spec = {
        "type": "scheduling_pinned_slot",
        "valid_window": {"start": "2026-04-20T09:00:00Z", "end": "2026-04-23T17:00:00Z"},
    }
    state = {"pinned_slot": "2026-04-21T14:00:00Z"}
    assert scheduling_pinned_slot(state=state, spec=spec) is True


def test_rejects_missing_slot():
    spec = {
        "type": "scheduling_pinned_slot",
        "valid_window": {"start": "2026-04-20T09:00:00Z", "end": "2026-04-23T17:00:00Z"},
    }
    assert scheduling_pinned_slot(state={"pinned_slot": None}, spec=spec) is False


def test_rejects_out_of_window_slot():
    spec = {
        "type": "scheduling_pinned_slot",
        "valid_window": {"start": "2026-04-20T09:00:00Z", "end": "2026-04-23T17:00:00Z"},
    }
    state = {"pinned_slot": "2026-05-01T10:00:00Z"}
    assert scheduling_pinned_slot(state=state, spec=spec) is False
