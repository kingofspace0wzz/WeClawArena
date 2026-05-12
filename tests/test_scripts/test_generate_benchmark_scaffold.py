"""Planning-only tests for the benchmark materialization helper."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from clawsocialarena.generator.templates.cm_coalition import CMCoalitionTemplate
from clawsocialarena.generator.templates.cu_coalition import CUCoalitionTemplate
from clawsocialarena.generator.templates.hs_coalition import HSCoalitionTemplate
from clawsocialarena.generator.templates.mg_coalition import MGCoalitionTemplate
from clawsocialarena.generator.templates.mc_scheduling import MCSchedulingTemplate
from clawsocialarena.scenario.validate import validate_bundle
from scripts import generate_benchmark_scaffold


_REQUIRED_ATTACK_METADATA_KEYS = {
    "attack_recipe",
    "attack_intensity",
    "delivery_surface",
    "attacker_control",
    "stage_expectations",
    "compliance_markers",
}

_REQUIRED_STAGE_EXPECTATION_KEYS = {
    "attack_exposure",
    "target_compliance",
    "partial_compromise",
    "final_harm",
    "policy_would_block",
    "enforce_blocked",
    "cascade_depth_min",
    "cascade_breadth_min",
}


def _assert_attack_plan_metadata(attack_plan: dict[str, object]) -> None:
    assert _REQUIRED_ATTACK_METADATA_KEYS <= set(attack_plan)
    assert attack_plan["compliance_markers"]
    stage_expectations = attack_plan["stage_expectations"]
    assert isinstance(stage_expectations, dict)
    assert _REQUIRED_STAGE_EXPECTATION_KEYS <= set(stage_expectations)


def test_build_plan_represents_126_main_base_tasks_as_matched_attack_blocks() -> None:
    plan = generate_benchmark_scaffold.build_plan(base_seed=1200, strata="main")
    main_rows = plan.by_stratum("main")

    assert plan.count() == 630
    assert len(main_rows) == 630
    assert Counter(row.attack_axis for row in main_rows) == {
        "benign": 126,
        "collaboration": 126,
        "security": 126,
        "privacy": 126,
        "governance": 126,
    }
    assert Counter(row.attack_mode for row in main_rows) == {
        "no_attacker": 126,
        "collaboration": 126,
        "security": 126,
        "privacy": 126,
        "governance": 126,
    }

    blocks: dict[str, list[generate_benchmark_scaffold.PlanRow]] = {}
    for row in main_rows:
        blocks.setdefault(row.base_task_id, []).append(row)

    assert len(blocks) == 126
    for block_id, rows in blocks.items():
        assert [row.attack_mode for row in rows] == [
            "no_attacker",
            "collaboration",
            "security",
            "privacy",
            "governance",
        ]
        assert len({row.category for row in rows}) == 1, block_id
        assert len({row.family for row in rows}) == 1, block_id
        assert len({row.seed for row in rows}) == 1, block_id
        assert len({row.designed_difficulty_tier for row in rows}) == 1, block_id
        assert rows[0].attack_axis == "benign"
        assert rows[0].attack_type is None

    assert Counter(
        (row.category, row.family, row.designed_difficulty_tier)
        for row in main_rows
        if row.attack_mode == "no_attacker"
    ) == {
        (category.value, family.value, tier): 3
        for category, family in generate_benchmark_scaffold._PLANNED_TEMPLATE_CELLS
        for tier in ("easy", "realistic", "stress")
    }

    governance_rows = [row for row in main_rows if row.attack_axis == "governance"]
    assert len(governance_rows) == 126
    assert {row.attack_type for row in governance_rows} == {
        "owner_binding_spoofing",
        "identity_confusion",
        "scope_creep",
        "approval_bypass",
        "mandate_laundering",
        "audit_evasion",
    }


def test_main_plan_reserves_resource_attack_rows_on_resource_template() -> None:
    plan = generate_benchmark_scaffold.build_plan(base_seed=1200, strata="main")
    resource_rows = [
        row for row in plan.rows if row.attack_type in {
            "unauthorized_file_delete",
            "cross_user_file_read",
        }
    ]

    assert resource_rows
    assert {row.category for row in resource_rows} == {"CU"}
    assert {row.family for row in resource_rows} == {"scheduling"}


def test_main_plan_rows_all_use_registered_phase_e_templates() -> None:
    plan = generate_benchmark_scaffold.build_plan(base_seed=1200, strata="main")

    assert all(generate_benchmark_scaffold.is_registered_template(row) for row in plan.rows)
    assert {row.family for row in plan.rows} == {
        "scheduling",
        "consensus",
        "coalition",
        "inference",
    }


def test_main_plan_orders_rows_by_matched_block_for_batch_smoke() -> None:
    plan = generate_benchmark_scaffold.build_plan(base_seed=1200, strata="main")

    assert [row.attack_mode for row in plan.rows[:10]] == [
        "no_attacker",
        "collaboration",
        "security",
        "privacy",
        "governance",
        "no_attacker",
        "collaboration",
        "security",
        "privacy",
        "governance",
    ]
    assert len({row.base_task_id for row in plan.rows[:5]}) == 1
    assert len({row.base_task_id for row in plan.rows[5:10]}) == 1


def test_scheduling_difficulty_profile_preserves_template_participants() -> None:
    shape = MCSchedulingTemplate().build(seed=1200, scenario_id="mc-scheduling-test")
    row = generate_benchmark_scaffold.PlanRow(
        scenario_id="mc-scheduling-test",
        stratum="main",
        category="MC",
        family="scheduling",
        seed=1200,
        attack_axis="benign",
        attack_type=None,
        base_task_id="mc-scheduling-test",
        attack_mode="no_attacker",
        designed_difficulty_tier="realistic",
    )

    shaped = generate_benchmark_scaffold._shape_with_difficulty_profile(shape, row)

    assert shaped.terminal_predicate["participants"] == ["npc-alex", "npc-blair"]
    assert shaped.terminal_predicate["required_participants"] == [
        "npc-alex",
        "npc-blair",
    ]


def test_attack_injection_prefers_template_attacker_hint() -> None:
    cases = {
        "reviewer-secondary": CUCoalitionTemplate().build(
            seed=1,
            scenario_id="cu-coa",
        ),
        "peer-delta": MGCoalitionTemplate().build(
            seed=1,
            scenario_id="mg-coa",
        ),
        "spoke-ops": HSCoalitionTemplate().build(
            seed=1,
            scenario_id="hs-coa",
        ),
        "rival-c": CMCoalitionTemplate().build(
            seed=1,
            scenario_id="cm-coa",
        ),
    }

    for expected_attacker, shape in cases.items():
        assert generate_benchmark_scaffold._select_attacker_agent_id(shape) == expected_attacker


def test_build_plan_all_represents_balanced_difficulty_pilot_contract() -> None:
    plan = generate_benchmark_scaffold.build_plan(base_seed=1200, strata="all")

    assert plan.count() == 680
    assert Counter(row.stratum for row in plan.rows) == {
        "main": 630,
        "hard": 25,
        "episode_graph": 20,
        "audit_challenges": 5,
    }
    assert Counter(row.family for row in plan.by_stratum("hard")) == {
        "code_review": 12,
        "doc_editing": 13,
    }
    assert {row.bundle_path for row in plan.by_stratum("episode_graph")} == {
        f"episode_graphs/episode_graph_{index:02d}" for index in range(1, 6)
    }


@pytest.mark.parametrize(
    ("strata", "expected_count"),
    [
        ("hard", 25),
        ("episode_graph", 20),
        ("audit_challenges", 5),
    ],
)
def test_build_plan_supports_individual_non_main_strata(
    strata: str,
    expected_count: int,
) -> None:
    plan = generate_benchmark_scaffold.build_plan(base_seed=1200, strata=strata)

    assert plan.count() == expected_count
    assert {row.stratum for row in plan.rows} == {strata}


def test_dry_run_prints_plan_and_writes_no_scenarios(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "out"
    rc = generate_benchmark_scaffold.main([
        "--dry-run",
        "--strata",
        "main",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    captured = capsys.readouterr().out
    assert "630 planned scenarios" in captured
    assert "governance=126" in captured
    assert "full generation is intentionally disabled" in captured
    assert not out.exists()


def test_generate_without_dry_run_is_blocked(tmp_path: Path) -> None:
    rc = generate_benchmark_scaffold.main([
        "--strata",
        "main",
        "--seed",
        "1200",
        "--out",
        str(tmp_path / "out"),
    ])

    assert rc == 2
    assert not (tmp_path / "out").exists()


def test_generate_supported_materializes_registered_rows_and_validates(
    tmp_path: Path,
) -> None:
    out = tmp_path / "supported"

    rc = generate_benchmark_scaffold.main([
        "--generate-supported",
        "--strata",
        "main",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    supported_rows = [
        row for row in generate_benchmark_scaffold.build_plan(base_seed=1200, strata="main").rows
        if generate_benchmark_scaffold.is_registered_template(row)
    ]
    generated_dirs = sorted(path for path in out.iterdir() if path.is_dir())
    assert len(generated_dirs) == len(supported_rows)
    assert {path.name for path in generated_dirs} == {
        row.scenario_id for row in supported_rows
    }
    for bundle_dir in generated_dirs:
        report = validate_bundle(bundle_dir)
        assert report.ok, report.errors


def test_materialize_benchmark_writes_balanced_difficulty_layout_and_indexes(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "all",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    assert index["version"] == "v1.0.0"
    assert index["scenario_count"] == 680
    assert index["strata"] == {
        "main": 630,
        "hard": 25,
        "episode_graph": 20,
        "audit_challenges": 5,
    }
    assert len(index["rows"]) == 680
    assert len({row["bundle_path"] for row in index["rows"]}) == 680

    main_rows = [row for row in index["rows"] if row["stratum"] == "main"]
    assert all(row["base_task_id"] for row in main_rows)
    assert {row["designed_difficulty_tier"] for row in main_rows} == {
        "easy",
        "realistic",
        "stress",
    }
    assert {row["attack_mode"] for row in main_rows[:5]} == {
        "no_attacker",
        "collaboration",
        "security",
        "privacy",
        "governance",
    }

    for row in index["rows"]:
        bundle_dir = out / row["bundle_path"]
        assert (bundle_dir / "scenario.json").exists(), row
        assert (bundle_dir / "scenario.gt.json").exists(), row
        assert (bundle_dir / "docker-compose.yml").exists(), row
        assert (bundle_dir / "personas").is_dir(), row
        assert (bundle_dir / "mcp").is_dir(), row
        if row["stratum"] == "audit_challenges":
            assert (bundle_dir / "action_log.json").exists(), row


def test_materialize_benchmark_writes_episode_graph_metadata(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "all",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    episode_index = json.loads((out / "episode_graphs" / "index.json").read_text())
    assert len(episode_index["graphs"]) == 5
    for graph in episode_index["graphs"]:
        graph_json = json.loads((out / graph["graph_path"]).read_text())
        assert graph_json["graph_id"] == graph["graph_id"]
        assert len(graph_json["episodes"]) == 4
        for episode in graph_json["episodes"]:
            assert (out / episode["bundle_path"] / "scenario.json").exists()


def test_materialize_benchmark_validates_every_planned_bundle(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "all",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    for row in index["rows"]:
        report = validate_bundle(out / row["bundle_path"])
        assert report.ok, f"{row['scenario_id']}: {report.errors}"


def test_materialize_benchmark_preserves_declared_axis_in_gt_attack_plan(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "all",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    resource_attack_rows = [
        row
        for row in index["rows"]
        if row["attack_type"]
        in {"unauthorized_file_delete", "cross_user_file_read"}
    ]
    assert resource_attack_rows
    for row in resource_attack_rows:
        gt = json.loads((out / row["bundle_path"] / "scenario.gt.json").read_text())
        assert gt["attack_plan"]["axis"] == row["attack_axis"], row
        invariants = gt["invariants"].get("resource_must_not_happen", [])
        assert invariants, row
        for invariant in invariants:
            assert invariant["axis"] == row["attack_axis"], row


def test_stress_tier_adversarial_rows_emit_stress_attack_metadata(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "main",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    stress_rows = [
        row
        for row in index["rows"]
        if row["designed_difficulty_tier"] == "stress"
        and row["attack_mode"] != "no_attacker"
    ]
    assert stress_rows
    for row in stress_rows:
        gt = json.loads((out / row["bundle_path"] / "scenario.gt.json").read_text())
        attack_plan = gt["attack_plan"]
        _assert_attack_plan_metadata(attack_plan)
        assert attack_plan["attack_intensity"] == "stress"
        assert attack_plan["attack_recipe"]
        assert attack_plan["stage_expectations"]["attack_exposure"] is True


def test_materialize_benchmark_does_not_write_index_after_errors(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"
    plan = generate_benchmark_scaffold.Plan(rows=[
        generate_benchmark_scaffold.PlanRow(
            scenario_id="unsupported-row",
            stratum="main",
            category="missing",
            family="missing",
            seed=1,
            attack_axis="benign",
            attack_type=None,
            base_task_id="unsupported-row",
            attack_mode="no_attacker",
        )
    ])

    rc = generate_benchmark_scaffold._materialize_benchmark(
        plan=plan,
        out=out,
        base_seed=1,
        version="test",
    )

    assert rc == 1
    assert not (out / "index.json").exists()


def test_canonical_benchmark_index_matches_current_plan() -> None:
    index_path = Path("benchmark/scenarios/v1.0.0/index.json")
    if not index_path.exists():
        pytest.skip("canonical benchmark scenario index is not materialized")

    index = json.loads(index_path.read_text())
    expected_rows = [
        generate_benchmark_scaffold._row_index_entry(row)
        for row in generate_benchmark_scaffold.build_plan(base_seed=1200, strata="all").rows
    ]

    assert index["version"] == "v1.0.0"
    assert index["base_seed"] == 1200
    assert index["rows"] == expected_rows


def test_materialize_benchmark_resource_coverage_matrix(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "all",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    resource_rows = []
    for row in index["rows"]:
        bundle_dir = out / row["bundle_path"]
        gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
        resource_manifest = gt.get("resource_manifest")
        if not resource_manifest:
            continue
        resource_rows.append(row)
        construction_manifest = gt.get("construction_manifest")
        assert construction_manifest is not None, row
        assert construction_manifest["construction_mode"] == "world_pack", row
        assert construction_manifest["profile_sources"][0]["dataset"] == (
            "AgentSocialBench"
        )
        assert (bundle_dir / "resources" / "manifest.json").exists(), row
        for resource in resource_manifest["resources"].values():
            assert (bundle_dir / "resources" / resource["path"]).exists(), row
            for rule in resource["allowed_operations"]:
                for operation in rule["operations"]:
                    assert operation in gt["mcp_tool_manifest"], row

        persona_tools = set()
        for tools_path in (bundle_dir / "personas").glob("*.tools.json"):
            persona_tools.update(json.loads(tools_path.read_text()))
        assert {"fs.read", "db.query"} <= persona_tools

    assert len(resource_rows) == 675
    assert Counter(row["stratum"] for row in resource_rows) == {
        "main": 630,
        "hard": 25,
        "episode_graph": 20,
    }
    assert {
        row["scenario_id"]
        for row in index["rows"]
        if row["stratum"] != "audit_challenges"
    } == {row["scenario_id"] for row in resource_rows}


def test_materialized_main_rows_include_task_schema_contract(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "main",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    first_row = index["rows"][0]
    gt = json.loads(
        (out / first_row["bundle_path"] / "scenario.gt.json").read_text()
    )
    manifest = gt["construction_manifest"]

    assert manifest["task_schema_version"] == "clawsocialarena-task-v0"
    assert manifest["designed_difficulty_tier"] == first_row[
        "designed_difficulty_tier"
    ]
    assert manifest["actors"]
    assert manifest["actors"][0]["visibility"]
    assert manifest["initialization"]["data"]
    assert manifest["consensus_rules"]["required_roles"]
    assert manifest["benign_task_objective"]["type"] == first_row["family"]
    assert manifest["task_success_spec"]["terminal_predicate_type"] == (
        gt["terminal_predicate"]["type"]
    )
    assert manifest["task_success_spec"]["reward_basis"]
    assert manifest["audit_events"]
    assert manifest["source_pattern"]["benchmark"] in {
        "tau2-bench",
        "WildClawBench",
    }


def test_materialized_scheduling_rows_keep_duration_and_manifest_contracts_synced(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "main",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    first_row = index["rows"][0]
    scenario = json.loads(
        (out / first_row["bundle_path"] / "scenario.json").read_text()
    )
    gt = json.loads(
        (out / first_row["bundle_path"] / "scenario.gt.json").read_text()
    )

    assert gt["terminal_predicate"]["duration_minutes"] == 30
    assert "30-minute" in scenario["opening_message"]["content"]
    for agent in scenario["agents"]:
        assert "30-minute" in agent["system_prompt_template"]
        assert "1-hour" not in agent["system_prompt_template"]

    scenario_manifest = scenario["initial_state"]["construction_manifest"]
    gt_manifest = gt["construction_manifest"]
    assert scenario_manifest == gt_manifest
    assert scenario_manifest["actors"][0]["user_id"] == scenario["agents"][0]["user_id"]
    assert scenario_manifest["designed_difficulty_tier"] == first_row[
        "designed_difficulty_tier"
    ]
    assert scenario_manifest["source_pattern"] == gt_manifest["source_pattern"]


def test_materialized_am_scheduling_canonical_action_duration_matches_task(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "main",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    target_rows = [
        row
        for row in index["rows"]
        if row["category"] == "AM"
        and row["family"] == "scheduling"
        and row["designed_difficulty_tier"] in {"easy", "realistic"}
    ]

    assert target_rows
    for row in target_rows:
        scenario = json.loads(
            (out / row["bundle_path"] / "scenario.json").read_text()
        )
        gt = json.loads(
            (out / row["bundle_path"] / "scenario.gt.json").read_text()
        )
        duration = gt["terminal_predicate"]["duration_minutes"]
        expected_label = generate_benchmark_scaffold._duration_label(duration)
        canonical_content = gt["canonical_action_stream"][0]["payload"]["content"]

        assert expected_label in scenario["opening_message"]["content"], row
        assert expected_label in canonical_content, row
        assert "1-hour" not in canonical_content, row


def test_materialized_worldpack_scaffold_uses_display_names_in_agent_facing_text(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "main",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    bundle = out / "main" / "cu-scheduling-stress-task-01206-no_attacker"
    scenario = json.loads((bundle / "scenario.json").read_text())
    agent_text = "\n".join(
        str(agent["system_prompt_template"]) for agent in scenario["agents"]
    )
    opening = scenario["opening_message"]["content"]
    persona_text = "\n".join(
        path.read_text() for path in sorted((bundle / "personas").glob("*.system.md"))
    )

    assert "You are Alice's personal agent" not in agent_text
    assert "You are Bob's personal agent" not in agent_text
    assert "Alice is available" not in agent_text
    assert "Bob is available" not in agent_text
    assert "Hi Bob" not in opening
    assert "decoy bad slot" not in opening.lower()
    assert "Sanjay" in opening
    assert "Scenario agent id" not in persona_text
    assert "Backing user id" not in persona_text
    assert "user-camila" not in persona_text
    assert "user-sanjay" not in persona_text


def test_materialized_mc_scaffold_uses_human_participant_labels_in_agent_text(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "main",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    bundle = out / "main" / "mc-scheduling-easy-task-01209-no_attacker"
    scenario = json.loads((bundle / "scenario.json").read_text())
    agent_text = "\n".join(
        str(agent["system_prompt_template"]) for agent in scenario["agents"]
    )
    opening = scenario["opening_message"]["content"]
    persona_text = "\n".join(
        path.read_text() for path in sorted((bundle / "personas").glob("*.system.md"))
    )
    terminal = json.loads((bundle / "scenario.gt.json").read_text())[
        "terminal_predicate"
    ]

    assert "npc-alex" not in agent_text
    assert "npc-blair" not in agent_text
    assert "npc-alex" not in opening
    assert "npc-blair" not in opening
    assert "npc-alex" not in persona_text
    assert "npc-blair" not in persona_text
    assert "Alex" in agent_text
    assert "Blair" in agent_text
    assert terminal["participants"] == ["npc-alex", "npc-blair"]


def test_materialized_attack_rows_carry_self_contained_attack_metadata(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "main",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    attack_rows = [row for row in index["rows"] if row["attack_type"]]
    assert attack_rows
    for row in attack_rows:
        gt = json.loads((out / row["bundle_path"] / "scenario.gt.json").read_text())
        _assert_attack_plan_metadata(gt["attack_plan"])

    collaboration = next(
        row for row in index["rows"] if row["attack_mode"] == "collaboration"
    )
    collaboration_gt = json.loads(
        (out / collaboration["bundle_path"] / "scenario.gt.json").read_text()
    )
    attack_plan = collaboration_gt["attack_plan"]
    assert attack_plan["axis"] == "collaboration"
    assert attack_plan["attack_type"] == collaboration["attack_type"]
    assert attack_plan["attacker_agent_id"]
    assert attack_plan["target_action_ids"]
    assert attack_plan["action_type"] == "outbound_message"
    assert attack_plan["target_recipient_id"]
    assert attack_plan["seed_message"]
    assert attack_plan["mentioned_items"]
    assert attack_plan["expected_bad_outcome"]

    privacy = next(row for row in index["rows"] if row["attack_mode"] == "privacy")
    privacy_gt = json.loads((out / privacy["bundle_path"] / "scenario.gt.json").read_text())
    privacy_plan = privacy_gt["attack_plan"]
    assert privacy_plan["target_action_ids"]
    assert privacy_plan["action_type"] == "tool_call"
    assert privacy_plan["tool_name"] in {"fs.read", "db.query"}
    assert privacy_plan["target_identity_id"] in privacy_gt["governance_manifest"][
        "identities"
    ]
    assert privacy_plan["target_scope_id"] in privacy_gt["governance_manifest"][
        "authorization_scopes"
    ]
    assert privacy_plan["expected_bad_outcome"]
    privacy_action = privacy_gt["canonical_action_stream"][0]
    assert (
        privacy_action["payload"]["arguments"]["identity_id"]
        == privacy_plan["target_identity_id"]
    )
    assert (
        privacy_action["payload"]["arguments"]["scope_id"]
        == privacy_plan["target_scope_id"]
    )
    target_resource_id = privacy_gt["attack_plan"]["target_resource_id"]
    target_resource = privacy_gt["resource_manifest"]["resources"][target_resource_id]
    assert "attack_target" in target_resource["metadata"]["world_resource_roles"]

    governance = next(row for row in index["rows"] if row["attack_mode"] == "governance")
    governance_gt = json.loads(
        (out / governance["bundle_path"] / "scenario.gt.json").read_text()
    )
    governance_plan = governance_gt["attack_plan"]
    assert governance_plan["action_type"] == "outbound_message"
    assert governance_plan["target_resource_id"]
    assert governance_plan["target_recipient_id"]
    assert governance_plan["seed_message"]
    assert governance_plan["expected_bad_outcome"]
    assert governance_plan["expected_governance"]
    assert governance_plan["observed_governance"]
    owners = governance_gt["governance_manifest"]["owners"]
    assert "owner-alice-spoofed" not in owners
    assert all(owner.get("user_id") != "user-alice" for owner in owners.values())

    identity_confusion = next(
        row
        for row in index["rows"]
        if row["attack_mode"] == "governance"
        and row["attack_type"] == "identity_confusion"
    )
    identity_confusion_gt = json.loads(
        (out / identity_confusion["bundle_path"] / "scenario.gt.json").read_text()
    )
    identity_confusion_text = json.dumps(identity_confusion_gt)
    assert "identity-alice-excluded" not in identity_confusion_text


def test_materialized_audit_challenge_rows_include_task_schema_contract(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "audit_challenges",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    assert index["rows"]
    for row in index["rows"]:
        gt = json.loads((out / row["bundle_path"] / "scenario.gt.json").read_text())
        manifest = gt["construction_manifest"]
        attack_plan = gt["attack_plan"]
        _assert_attack_plan_metadata(attack_plan)
        assert attack_plan["attack_intensity"] == "stress"
        assert attack_plan["attacker_control"] == "seeded_challenge"
        assert manifest["task_schema_version"] == "clawsocialarena-task-v0"
        assert manifest["construction_mode"] == "audit_challenge"
        assert manifest["actors"]
        assert manifest["task_success_spec"]["reward_basis"]
        assert manifest["audit_events"][0]["required_log_level"]


def test_materialize_benchmark_keeps_world_pack_fixed_within_main_attack_block(
    tmp_path: Path,
) -> None:
    out = tmp_path / "benchmark"

    rc = generate_benchmark_scaffold.main([
        "--materialize-benchmark",
        "--strata",
        "all",
        "--seed",
        "1200",
        "--out",
        str(out),
    ])

    assert rc == 0
    index = json.loads((out / "index.json").read_text())
    main_rows = [row for row in index["rows"] if row["stratum"] == "main"]
    manifests_by_block: dict[str, list[tuple[str, tuple[object, ...]]]] = {}
    for row in main_rows:
        gt = json.loads((out / row["bundle_path"] / "scenario.gt.json").read_text())
        construction_manifest = gt.get("construction_manifest")
        if not construction_manifest:
            continue
        payload = (
            construction_manifest["world_id"],
            tuple(
                source["profile_ref"]
                for source in construction_manifest["profile_sources"]
            ),
            tuple(
                (source["resource_id"], source["source_ref"])
                for source in construction_manifest["resource_sources"]
            ),
        )
        manifests_by_block.setdefault(row["base_task_id"], []).append(
            (row["attack_mode"], payload)
        )

    assert manifests_by_block
    for block_id, manifests in manifests_by_block.items():
        assert [attack_mode for attack_mode, _ in manifests] == [
            "no_attacker",
            "collaboration",
            "security",
            "privacy",
            "governance",
        ], block_id
        assert len({payload for _, payload in manifests}) == 1, block_id


def test_audit_challenge_contract_lists_governance_cases() -> None:
    assert generate_benchmark_scaffold.audit_challenge_case_ids() == (
        "inferential_leakage_v1",
        "cross_delegation_attr_v1",
        "partial_log_recovery_v1",
        "mandate_laundering_v1",
        "approval_bypass_v1",
    )
