from pathlib import Path
import json

from clawsocialarena.generator.cli import _write_bundle
from clawsocialarena.generator.gt_assembly import assemble_gt_bundle
from clawsocialarena.generator.registry import get_template
from clawsocialarena.generator.template import CategoryCode, TaskFamily
from clawsocialarena.generator.templates.am_scheduling import AMSchedulingTemplate
from clawsocialarena.generator.world_pack_instantiation import apply_world_pack
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.scenario.validate import validate_bundle
from clawsocialarena.worlds.loader import load_world_packs


def test_apply_world_pack_adds_resource_and_construction_manifests(
    tmp_path: Path,
) -> None:
    template = get_template(CategoryCode.CU, TaskFamily.SCHEDULING)
    shape = template.build(seed=1200, scenario_id="MC_SCHED_001")
    pack = load_world_packs(Path("benchmark/worlds/v1.0.0"))[0]

    enriched = apply_world_pack(
        shape=shape,
        pack=pack,
        task_family="scheduling",
        harm_axis="privacy",
    )

    assert enriched.resource_manifest
    assert enriched.governance_manifest
    assert enriched.resource_fixtures
    assert enriched.attack_plan is not None
    protected_policy_substrings = {
        policy["params"]["substring"]
        for policy in enriched.declared_policies["flat"]
        if policy.get("kind") == "does_not_contain"
    }
    assert "private-medical" not in protected_policy_substrings
    assert "custody mediation and child pickup details" in protected_policy_substrings
    assert enriched.construction_manifest["construction_mode"] == "world_pack"
    assert (
        enriched.construction_manifest["task_schema_version"]
        == "clawsocialarena-task-v0"
    )
    assert enriched.construction_manifest["task_success_spec"]["reward_basis"]
    assert enriched.construction_manifest["audit_events"][0]["visibility"]
    actors = {
        actor["agent_id"]: actor
        for actor in enriched.construction_manifest["actors"]
    }
    alice_visibility = set(actors["alice"]["visibility"])
    bob_visibility = set(actors["bob"]["visibility"])
    assert "file-camila-custody-notes" in alice_visibility
    assert "db-camila-personal" in alice_visibility
    assert "file-sanjay-client-schedule" not in alice_visibility
    assert "file-sanjay-client-schedule" in bob_visibility
    assert "db-sanjay-personal" in bob_visibility
    assert "file-camila-custody-notes" not in bob_visibility
    assert (
        enriched.initial_state["construction_manifest"]["world_id"]
        == "world-asb-camila-sanjay-001"
    )
    assert enriched.agents[0]["user_id"] == "user-camila"
    assert enriched.agents[0]["default_owner_id"] == "owner-camila"
    assert enriched.agents[0]["default_identity_id"] == "identity-owner-camila-primary"
    assert "Camila Mitchell" in enriched.agents[0]["system_prompt_template"]
    assert "World-pack user binding" not in enriched.agents[0]["system_prompt_template"]
    assert "scenario-local agent_id" not in enriched.agents[0]["system_prompt_template"]
    assert enriched.persona_manifest["alice"]["profile_ref"] == (
        "asb://profiles/profile_001"
    )

    gt = assemble_gt_bundle(enriched)
    parsed = GTBundle.model_validate(gt)
    assert parsed.construction_manifest is not None
    assert parsed.construction_manifest.profile_sources[0].dataset == "AgentSocialBench"

    out_dir = tmp_path / enriched.scenario_id
    _write_bundle(enriched, out_dir)

    report = validate_bundle(out_dir)
    assert report.ok, report.errors
    assert (out_dir / "resources" / "home" / "camila" / "custody-notes.md").exists()
    gt_on_disk = json.loads((out_dir / "scenario.gt.json").read_text())
    assert gt_on_disk["construction_manifest"]["construction_mode"] == "world_pack"
    assert (
        gt_on_disk["construction_manifest"]["task_schema_version"]
        == "clawsocialarena-task-v0"
    )


def test_am_world_pack_binding_uses_distinct_users_for_three_participant_task() -> None:
    shape = AMSchedulingTemplate().build(
        seed=1221,
        scenario_id="am-scheduling-realistic-task-01221-no_attacker",
    )
    pack = load_world_packs(Path("benchmark/worlds/v1.0.0"))[0]

    enriched = apply_world_pack(
        shape=shape,
        pack=pack,
        task_family="scheduling",
        harm_axis="benign",
    )

    user_ids = [agent["user_id"] for agent in enriched.agents]
    assert len(user_ids) == 3
    assert len(set(user_ids)) == 3


def test_world_pack_selection_includes_file_and_database_for_every_bound_user() -> None:
    shape = AMSchedulingTemplate().build(
        seed=1221,
        scenario_id="am-scheduling-realistic-task-01221-no_attacker",
    )
    pack = load_world_packs(Path("benchmark/worlds/v1.0.0"))[0]

    enriched = apply_world_pack(
        shape=shape,
        pack=pack,
        task_family="scheduling",
        harm_axis="benign",
    )

    resources = enriched.resource_manifest["resources"]
    by_owner: dict[str, set[str]] = {}
    for entry in resources.values():
        by_owner.setdefault(entry["owner_id"], set()).add(entry["type"])

    assert by_owner["owner-camila"] >= {"file", "sqlite_db"}
    assert by_owner["owner-sanjay"] >= {"file", "sqlite_db"}
    assert by_owner["owner-aisha"] >= {"file", "sqlite_db"}
    assert enriched.construction_manifest["selected_resources_by_user"][
        "user-aisha"
    ]


def test_world_pack_selection_rejects_bound_user_without_resource_coverage() -> None:
    shape = AMSchedulingTemplate().build(
        seed=1221,
        scenario_id="am-scheduling-realistic-task-01221-no_attacker",
    )
    pack = load_world_packs(Path("benchmark/worlds/v1.0.0"))[0]
    missing_aisha = pack.model_copy(
        update={
            "resources": pack.resources.model_copy(
                update={
                    "files": [
                        resource
                        for resource in pack.resources.files
                        if resource.user_id != "user-aisha"
                    ],
                    "databases": [
                        resource
                        for resource in pack.resources.databases
                        if resource.user_id != "user-aisha"
                    ],
                }
            )
        }
    )

    try:
        apply_world_pack(
            shape=shape,
            pack=missing_aisha,
            task_family="scheduling",
            harm_axis="benign",
        )
    except ValueError as exc:
        assert "user-aisha" in str(exc)
    else:
        raise AssertionError("expected missing Aisha resources to be rejected")
