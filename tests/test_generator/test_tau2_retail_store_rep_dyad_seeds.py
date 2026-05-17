"""Sanity tests for store_rep_dyad seed data."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.tau2_retail.seeds import (
    STORE_REP_DYAD_TASK_SEEDS,
)


def test_six_store_rep_dyad_tasks_present() -> None:
    assert len(STORE_REP_DYAD_TASK_SEEDS) == 6
    indices = [seed.task_index for seed in STORE_REP_DYAD_TASK_SEEDS]
    assert indices == [0, 1, 2, 3, 4, 5]


def test_store_rep_carries_verbatim_retail_policy() -> None:
    canon_path = "knowledge/tau2-bench/data/tau2/domains/retail/policy.md"
    canon = open(canon_path).read()
    for seed in STORE_REP_DYAD_TASK_SEEDS:
        retail_files = {f.path: f for f in seed.store_rep_workspace.files}
        assert "retail_policy.md" in retail_files
        assert retail_files["retail_policy.md"].content == canon
        assert retail_files["retail_policy.md"].protected is True


def test_store_rep_inventory_has_protected_vendor_cost() -> None:
    for seed in STORE_REP_DYAD_TASK_SEEDS:
        inv = next(t for t in seed.store_rep_workspace.tables if t.name == "inventory")
        assert "protected" in inv.schema
        assert "vendor_cost" in inv.schema


def test_store_rep_dyad_override_codes_distinct() -> None:
    codes = {s.store_policy_override_authorization_code for s in STORE_REP_DYAD_TASK_SEEDS}
    assert len(codes) == 6
    for code in codes:
        assert code.startswith("STORE-OVERRIDE-")


def test_authentication_methods_mix_includes_email() -> None:
    methods = {s.customer_authentication_method for s in STORE_REP_DYAD_TASK_SEEDS}
    assert "name_zip" in methods
    assert "email" in methods
