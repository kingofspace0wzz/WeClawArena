"""Seed-data provenance tests for swebench_workspace."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.swebench_workspace.seed_data import (
    WORKSPACE_TASK_SEEDS,
)


EXPECTED_SWEBENCH_LITE_IDS = (
    "astropy__astropy-12907",
    "django__django-10914",
    "pydata__xarray-4094",
    "pylint-dev__pylint-7080",
    "pytest-dev__pytest-7432",
    "sympy__sympy-13480",
    "astropy__astropy-14182",
    "astropy__astropy-14365",
    "django__django-11133",
    "django__django-11999",
    "django__django-12308",
    "django__django-13933",
    "django__django-15851",
    "matplotlib__matplotlib-23476",
    "psf__requests-2317",
    "pytest-dev__pytest-7490",
    "scikit-learn__scikit-learn-13439",
    "scikit-learn__scikit-learn-13496",
    "scikit-learn__scikit-learn-25747",
    "sphinx-doc__sphinx-8721",
    "sphinx-doc__sphinx-11445",
    "sympy__sympy-12419",
    "sympy__sympy-13647",
    "sympy__sympy-20590",
    "django__django-11099",
    "sympy__sympy-12481",
    "matplotlib__matplotlib-23299",
    "scikit-learn__scikit-learn-10297",
    "astropy__astropy-14995",
    "django__django-11179",
    "sympy__sympy-13031",
    "matplotlib__matplotlib-23314",
    "scikit-learn__scikit-learn-13142",
    "django__django-11815",
    "sympy__sympy-15345",
    "matplotlib__matplotlib-24149",
    "scikit-learn__scikit-learn-13779",
    "django__django-11848",
    "sympy__sympy-16792",
    "django__django-11964",
    "sympy__sympy-17139",
    "django__django-12125",
    "sympy__sympy-17630",
    "django__django-12708",
    "sympy__sympy-17655",
    "django__django-13028",
    "sympy__sympy-18189",
    "django__django-13033",
    "django__django-13158",
    "django__django-13315",
)


def test_workspace_seeds_are_curated_swebench_lite_rows() -> None:
    assert tuple(seed.instance_id for seed in WORKSPACE_TASK_SEEDS) == (
        EXPECTED_SWEBENCH_LITE_IDS
    )
    for seed in WORKSPACE_TASK_SEEDS:
        assert seed.source_dataset == "princeton-nlp/SWE-bench_Lite"
        assert seed.source_split == "test"
        assert re.fullmatch(r"[0-9a-f]{40}", seed.base_commit)
        assert re.fullmatch(r"[0-9a-f]{40}", seed.environment_setup_commit)
        assert not seed.instance_id.endswith("-0001")
        assert seed.target_tests
        assert seed.regression_tests
        assert seed.gold_patch.startswith("diff --git ")
        assert set(seed.required_approval_files).issubset(seed.repo_files)


def test_workspace_seed_expansion_rows_are_materializable() -> None:
    assert len(WORKSPACE_TASK_SEEDS) == 50
    assert WORKSPACE_TASK_SEEDS[-1].scenario_id == "swebench_workspace_phase5_v49"
    for seed in WORKSPACE_TASK_SEEDS[6:]:
        assert seed.scenario_id == f"swebench_workspace_phase5_v{seed.task_index}"
        assert len(seed.required_approval_files) == 1
        assert set(seed.required_approval_files).issubset(seed.repo_files)
        assert "secrets/prod.env" in seed.repo_files
        assert seed.problem_statement
        assert seed.owner_constraint_description


def test_expanded_source_stubs_preserve_hunk_header_context() -> None:
    seed = next(
        seed
        for seed in WORKSPACE_TASK_SEEDS
        if seed.scenario_id == "swebench_workspace_phase5_v23"
    )

    source_stub = seed.repo_files["sympy/core/_print_helpers.py"]

    assert "class Printable:" in source_stub
    assert '    """\n    This also adds support' in source_stub
    assert "def __str__(self):" in source_stub
    assert "__slots__ = ()" not in source_stub


def test_workspace_seeds_have_local_swebench_environment_resources() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    resource_root = (
        repo_root / "knowledge" / "SWE-bench" / "swebench" / "resources"
        / "swebench-og"
    )
    if not resource_root.is_dir():
        pytest.skip("local SWE-bench environment resource mirror is not present")
    for seed in WORKSPACE_TASK_SEEDS:
        repo_key, issue_id = seed.instance_id.rsplit("-", maxsplit=1)
        assert (
            resource_root / repo_key / issue_id / "environment.yml"
        ).is_file(), seed.instance_id
