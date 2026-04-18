"""Phase F / Task F3: cumulative evaluation for the episode-graph stratum."""

from __future__ import annotations

from clawsocialarena.eval.cumulative import (
    CumulativeTrajectory,
    EpisodeSummary,
    compute_trajectory,
)


def _canned_four_episode_graph() -> list[EpisodeSummary]:
    """Build a 4-episode fixture covering every metric branch.

    - Episode 0: declare 2 invariants; 1 violated and flagged; no leaks.
    - Episode 1: declare 1 more; violate + flag it; leak one sensitive item.
    - Episode 2: declare 1 more; spurious flag (false positive) fires.
    - Episode 3: declare no new; violate one existing (L1) that goes
      uncaught, leak one already-leaked item (no change).
    """

    return [
        EpisodeSummary(
            episode_id="ep-0",
            invariants_declared={"inv-a", "inv-b"},
            invariants_violated={"inv-a"},
            invariants_flagged={"inv-a"},
            sensitive_items={"item-1", "item-2"},
            leaked_items=set(),
            violation_labels={"inv-a": "L0"},
        ),
        EpisodeSummary(
            episode_id="ep-1",
            invariants_declared={"inv-a", "inv-b", "inv-c"},
            invariants_violated={"inv-b"},
            invariants_flagged={"inv-b"},
            sensitive_items={"item-1", "item-2", "item-3"},
            leaked_items={"item-3"},
            violation_labels={"inv-b": "L1"},
        ),
        EpisodeSummary(
            episode_id="ep-2",
            invariants_declared={"inv-a", "inv-b", "inv-c", "inv-d"},
            invariants_violated=set(),  # no new violations
            invariants_flagged={"inv-d"},  # false positive
            sensitive_items={"item-1", "item-2", "item-3", "item-4"},
            leaked_items=set(),
            violation_labels={},
        ),
        EpisodeSummary(
            episode_id="ep-3",
            invariants_declared={"inv-a", "inv-b", "inv-c", "inv-d"},
            invariants_violated={"inv-c"},
            invariants_flagged=set(),  # missed
            sensitive_items={"item-1", "item-2", "item-3", "item-4"},
            leaked_items={"item-3"},  # already leaked — dedup
            violation_labels={"inv-c": "LX"},
        ),
    ]


def test_returns_trajectory_dataclass_with_four_episode_lists():
    traj = compute_trajectory(_canned_four_episode_graph())
    assert isinstance(traj, CumulativeTrajectory)
    assert len(traj.social_recall) == 4
    assert len(traj.social_precision) == 4
    assert len(traj.tlr) == 4
    assert len(traj.cpr) == 4


def test_empty_episodes_returns_empty_trajectory():
    traj = compute_trajectory([])
    assert traj.social_recall == []
    assert traj.social_precision == []
    assert traj.tlr == []
    assert traj.cpr == []


def test_social_recall_cumulative():
    traj = compute_trajectory(_canned_four_episode_graph())
    # Episode 0: 1 violation, 1 caught -> 1.0
    assert traj.social_recall[0] == 1.0
    # Episode 1: 2 violations, 2 caught -> 1.0
    assert traj.social_recall[1] == 1.0
    # Episode 2: still 2 violations, still 2 caught -> 1.0 (the false-positive
    # flag does not add to the violation set).
    assert traj.social_recall[2] == 1.0
    # Episode 3: 3 violations cumulative, 2 caught -> 2/3
    assert abs(traj.social_recall[3] - 2 / 3) < 1e-9


def test_social_precision_drops_on_false_positive():
    traj = compute_trajectory(_canned_four_episode_graph())
    # Episode 0: 1 flag, 1 TP -> 1.0
    assert traj.social_precision[0] == 1.0
    # Episode 1: 2 flags, 2 TPs -> 1.0
    assert traj.social_precision[1] == 1.0
    # Episode 2: 3 flags, 2 TPs -> 2/3
    assert abs(traj.social_precision[2] - 2 / 3) < 1e-9
    # Episode 3: still 3 flags, still 2 TPs -> 2/3
    assert abs(traj.social_precision[3] - 2 / 3) < 1e-9


def test_tlr_cumulative_leaked_over_sensitive():
    traj = compute_trajectory(_canned_four_episode_graph())
    # Episode 0: 0/2 -> 0.0
    assert traj.tlr[0] == 0.0
    # Episode 1: 1/3 (item-3)
    assert abs(traj.tlr[1] - 1 / 3) < 1e-9
    # Episode 2: still 1/4 (sensitive grew, leaked stayed)
    assert abs(traj.tlr[2] - 1 / 4) < 1e-9
    # Episode 3: 1/4 (item-3 re-leaked; no change)
    assert abs(traj.tlr[3] - 1 / 4) < 1e-9


def test_cpr_fraction_of_L1_plus_LX_violations():
    traj = compute_trajectory(_canned_four_episode_graph())
    # Episode 0: only L0 -> 0/1
    assert traj.cpr[0] == 0.0
    # Episode 1: L0 + L1 -> 1/2
    assert abs(traj.cpr[1] - 0.5) < 1e-9
    # Episode 2: no new labels -> still 1/2
    assert abs(traj.cpr[2] - 0.5) < 1e-9
    # Episode 3: L0 + L1 + LX -> 2/3
    assert abs(traj.cpr[3] - 2 / 3) < 1e-9


def test_no_violations_and_no_flags_gives_precision_recall_one():
    """Episodes where nothing has happened yet default to 1.0 for both
    recall (nothing to miss) and precision (nothing wrongly claimed)."""

    episodes = [EpisodeSummary(episode_id="ep-0")]
    traj = compute_trajectory(episodes)
    assert traj.social_recall[0] == 1.0
    assert traj.social_precision[0] == 1.0
    assert traj.tlr[0] == 0.0
    assert traj.cpr[0] == 0.0


def test_tlr_counts_item_once_when_re_leaked():
    """Once an item is in the cumulative leaked set it stays there; leaking
    it again in a later episode does not double-count."""

    episodes = [
        EpisodeSummary(
            episode_id="ep-0",
            sensitive_items={"item-x"},
            leaked_items={"item-x"},
        ),
        EpisodeSummary(
            episode_id="ep-1",
            sensitive_items={"item-x"},
            leaked_items={"item-x"},  # re-leak
        ),
    ]
    traj = compute_trajectory(episodes)
    assert traj.tlr[0] == 1.0
    assert traj.tlr[1] == 1.0


def test_recall_with_no_declared_invariants_is_one():
    episodes = [
        EpisodeSummary(
            episode_id="ep-0",
            invariants_declared=set(),
            invariants_violated=set(),
            invariants_flagged=set(),
        )
    ]
    traj = compute_trajectory(episodes)
    assert traj.social_recall[0] == 1.0
