"""Tests for hub_aggregator seeds."""
from __future__ import annotations


def test_six_hub_aggregator_tasks_present() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail.seeds import HUB_AGGREGATOR_TASK_SEEDS
    assert len(HUB_AGGREGATOR_TASK_SEEDS) == 6


def test_hub_aggregator_has_exactly_three_spokes() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail.seeds import HUB_AGGREGATOR_TASK_SEEDS
    for seed in HUB_AGGREGATOR_TASK_SEEDS:
        assert len(seed.spoke_workspaces) == 3
        spoke_ids = {w.owner_id for w in seed.spoke_workspaces}
        assert len(spoke_ids) == 3  # all spoke owner_ids distinct


def test_hub_aggregator_spokes_have_untrusted_files_only() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail.seeds import HUB_AGGREGATOR_TASK_SEEDS
    for seed in HUB_AGGREGATOR_TASK_SEEDS:
        for spoke in seed.spoke_workspaces:
            for file in spoke.files:
                assert file.protected is False, f"{spoke.owner_id}/{file.path}"


def test_hub_aggregator_shared_orders_table_has_originating_spoke_column() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail.seeds import HUB_AGGREGATOR_TASK_SEEDS
    for seed in HUB_AGGREGATOR_TASK_SEEDS:
        line_items_schema = ""
        for r in seed.shared_resources:
            # search nested tables for line_items
            if r.tables:
                for t in r.tables:
                    if "line_items" in t.name:
                        line_items_schema = t.schema
                        break
        assert "originating_spoke_id" in line_items_schema
