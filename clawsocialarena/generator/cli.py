"""Scenario generator CLI (v2; Task D7).

Usage:
    python -m clawsocialarena.generator.cli \\
        --category CU --family scheduling --n 1 --seed 42 \\
        --out /tmp/gen_test

For each scenario, emits a full v2 bundle under ``<out>/<scenario_id>/``:

    scenario.json
    scenario.gt.json
    docker-compose.yml
    personas/<agent_id>.system.md
    personas/<agent_id>.tools.json
    mcp/<tool>.json

``--instantiation-mode llm`` is accepted as a forward-compatibility flag but
currently silently falls back to deterministic instantiation until the
LLMClient plumbing lands (Phase 4.2).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from clawsocialarena.baselines.prompt_ladder import (
    PrivacyLevel,
    system_prompt_with_level,
)
from clawsocialarena.generator.attack_injection import AttackType, inject_attack
from clawsocialarena.generator.compose_emitter import emit_compose_yaml
from clawsocialarena.generator.gt_assembly import (
    assemble_gt_bundle,
    assemble_scenario_json,
)
from clawsocialarena.generator.governance_emitter import (
    emit_governance_manifest_files,
)
from clawsocialarena.generator.instantiation import instantiate
from clawsocialarena.generator.mcp_emitter import emit_mcp_configs
from clawsocialarena.generator.persona_emitter import emit_persona_files
from clawsocialarena.generator.registry import get_template, list_registered
from clawsocialarena.generator.resource_emitter import write_resource_bundle
from clawsocialarena.generator.task_patterns import pattern_for
from clawsocialarena.generator.task_success_specs import task_success_metadata
from clawsocialarena.generator.template import CategoryCode, TaskFamily
from clawsocialarena.scenario.models import Scenario


INSTANTIATION_MODES = ("deterministic", "llm")

# Repo root (the directory that holds ``docker/`` + ``pyproject.toml``).
# The compose emitter writes this path into every ``build.context`` so the
# generated compose file resolves identically regardless of how deep the
# bundle lives on disk.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clawsocialarena.generator",
        description=(
            "Generate ClawSocialArena scenarios (scenario.json + "
            "scenario.gt.json + compose + personas + mcp)."
        ),
    )
    p.add_argument(
        "--category",
        type=CategoryCode,
        choices=list(CategoryCode),
        help="Scenario category code (CD/MC/CU/MG/HS/CM/AM).",
    )
    p.add_argument(
        "--family",
        type=TaskFamily,
        choices=list(TaskFamily),
        help="Verifiable task family.",
    )
    p.add_argument("--n", type=int, default=1, help="Number of scenarios to generate.")
    p.add_argument("--seed", type=int, default=0, help="Base random seed.")
    p.add_argument(
        "--attack",
        type=AttackType,
        choices=list(AttackType),
        default=None,
        help="Optional attacker type. If omitted, benign scenarios are generated.",
    )
    p.add_argument(
        "--attacker-agent",
        default=None,
        help="Agent id to mark as the attacker (required if --attack is set).",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Output directory. Creates <out>/<scenario_id>/ per scenario.",
    )
    p.add_argument(
        "--instantiation-mode",
        choices=INSTANTIATION_MODES,
        default="deterministic",
        help=(
            "Instantiation mode. 'llm' is a forward-compat flag and currently "
            "falls back to 'deterministic' until the LLMClient lands."
        ),
    )
    p.add_argument(
        "--privacy-level",
        type=int,
        choices=[0, 1, 2, 3, 4],
        default=None,
        help=(
            "AgentSocialBench L0-L4 prompt privacy level. When set, the "
            "prompt-ladder baseline's level prefix is appended to every "
            "agent's system prompt before persona files are emitted. "
            "Omit this flag to emit the base scenario unchanged."
        ),
    )
    p.add_argument(
        "--list-templates",
        action="store_true",
        help="List registered (category, family) pairs and exit.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.list_templates:
        for cat, fam in list_registered():
            print(f"{cat.value} × {fam.value}")
        return 0

    # For a normal generation run, category/family/out are required.
    missing = [
        name for name, val in (
            ("--category", args.category),
            ("--family", args.family),
            ("--out", args.out),
        )
        if val is None
    ]
    if missing:
        print(
            "missing required argument(s): " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    if args.attack is not None and not args.attacker_agent:
        print("--attacker-agent is required when --attack is set", file=sys.stderr)
        return 2

    if args.instantiation_mode == "llm":
        # Forward-compat stub. Announce the fallback so callers know their
        # LLM-mode run was actually deterministic.
        print(
            "note: --instantiation-mode=llm is stubbed; "
            "falling back to deterministic.",
            file=sys.stderr,
        )

    try:
        template = get_template(args.category, args.family)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 2

    out_root: Path = args.out
    out_root.mkdir(parents=True, exist_ok=True)

    for i in range(args.n):
        scenario_id = (
            f"{args.category.value.lower()}-{args.family.value}-"
            f"{args.seed}-{i:03d}"
        )
        shape = instantiate(
            template, seed=args.seed + i, scenario_id=scenario_id
        )
        if args.attack is not None:
            shape = inject_attack(
                shape=shape,
                attack_type=args.attack,
                attacker_agent_id=args.attacker_agent,
            )

        _write_bundle(
            shape,
            out_root / scenario_id,
            privacy_level=(
                PrivacyLevel(args.privacy_level)
                if args.privacy_level is not None
                else None
            ),
        )
        print(f"wrote {out_root / scenario_id}")

    return 0


def _write_bundle(
    shape, out_dir: Path, *, privacy_level: PrivacyLevel | None = None
) -> None:
    """Write a complete v2 bundle to ``out_dir``.

    When ``privacy_level`` is supplied, every agent's
    ``system_prompt_template`` gets the corresponding prompt-ladder
    prefix appended. This is the data-producing side of the Phase F
    prompt-ladder baseline (spec §5.2 item 1): agents run with
    progressively stronger privacy instructions while the gateway
    stack stays untouched. The injection lands on both
    ``scenario.json`` and the persona files so every downstream
    consumer sees the adjusted prompt uniformly.
    """

    _clean_generated_bundle_entries(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not shape.construction_manifest:
        shape = shape.model_copy(
            update={"construction_manifest": _default_construction_manifest(shape)}
        )

    scenario_dict = assemble_scenario_json(shape)
    gt_dict = assemble_gt_bundle(shape)

    if privacy_level is not None:
        for agent_entry in scenario_dict.get("agents", []):
            base = agent_entry.get("system_prompt_template", "")
            agent_entry["system_prompt_template"] = system_prompt_with_level(
                base, privacy_level
            )

    (out_dir / "scenario.json").write_text(
        json.dumps(scenario_dict, indent=2, ensure_ascii=False)
    )
    (out_dir / "scenario.gt.json").write_text(
        json.dumps(gt_dict, indent=2, ensure_ascii=False)
    )

    # Build the Scenario pydantic model for the emitters that want typed input.
    scenario = Scenario.model_validate(scenario_dict)

    # docker-compose.yml -- absolute build context so the emitted compose
    # resolves identically no matter how deep the bundle sits on disk.
    (out_dir / "docker-compose.yml").write_text(
        emit_compose_yaml(
            scenario,
            compose_build_root=_REPO_ROOT,
            include_resources=bool(gt_dict.get("resource_manifest")),
        )
    )

    # personas/
    # Phase D.5 Fix 4: respect each agent's `allowed_tools`. When an agent
    # sets the field, the emitter writes that subset; when it is `None`
    # the emitter falls back to the full `mcp_tool_manifest`, which
    # preserves the previous "every agent gets every tool" default so
    # legacy templates keep working.
    personas_dir = out_dir / "personas"
    personas_dir.mkdir(parents=True, exist_ok=True)
    full_manifest = list(gt_dict.get("mcp_tool_manifest", {}).keys())
    tool_allowlist_by_agent = {
        agent.agent_id: (
            list(agent.allowed_tools)
            if agent.allowed_tools is not None
            else list(full_manifest)
        )
        for agent in scenario.agents
    }
    for filename, contents in emit_persona_files(
        scenario, tool_allowlist_by_agent=tool_allowlist_by_agent
    ).items():
        (personas_dir / filename).write_text(contents)

    # mcp/
    mcp_dir = out_dir / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    for filename, contents in emit_mcp_configs(
        gt_dict.get("mcp_tool_manifest", {})
    ).items():
        (mcp_dir / filename).write_text(contents)

    # governance/
    governance_files = emit_governance_manifest_files(
        gt_dict.get("governance_manifest")
    )
    if governance_files:
        governance_dir = out_dir / "governance"
        governance_dir.mkdir(parents=True, exist_ok=True)
        for filename, contents in governance_files.items():
            (governance_dir / filename).write_text(contents)

    # resources/
    write_resource_bundle(
        out_dir / "resources",
        gt_dict.get("resource_manifest"),
        getattr(shape, "resource_fixtures", {}),
    )


def _clean_generated_bundle_entries(out_dir: Path) -> None:
    """Remove stale generated files before rewriting a bundle in place."""

    for name in (
        "scenario.json",
        "scenario.gt.json",
        "docker-compose.yml",
        "personas",
        "mcp",
        "governance",
        "resources",
    ):
        path = out_dir / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def _default_construction_manifest(shape) -> dict:
    manifest = {
        "construction_mode": "template_world_pack",
        "world_id": f"template://{shape.category.value}/{shape.task_family.value}",
        "world_schema_version": "clawsocialarena-template-v0",
        "profile_sources": _profile_sources(shape),
        "resource_sources": [
            {
                "resource_id": resource_id,
                "resource_type": str(resource.get("type") or "unknown"),
                "source_ref": f"template://{shape.scenario_id}/{resource_id}",
                "materialized_path": resource.get("path"),
            }
            for resource_id, resource in shape.resource_manifest.get(
                "resources",
                {},
            ).items()
        ],
        "source_pattern": pattern_for(
            family=shape.task_family.value,
            tier="realistic",
        ),
        "naturalization": {"method": "deterministic_template"},
        "realism_status": "structural_draft",
    }
    manifest.update(
        task_success_metadata(
            family=shape.task_family.value,
            terminal_predicate=dict(shape.terminal_predicate),
            designed_difficulty_tier="realistic",
            expected_task_failure_modes=[],
            agents=[dict(agent) for agent in shape.agents],
            initial_state=dict(shape.initial_state),
            resource_manifest=dict(shape.resource_manifest),
        )
    )
    return manifest


def _profile_sources(shape) -> list[dict]:
    sources = []
    persona_manifest = shape.persona_manifest or {}
    for agent in shape.agents:
        agent_id = str(agent.get("agent_id"))
        user_id = str(agent.get("user_id") or agent_id)
        profile = persona_manifest.get(agent_id, {})
        sources.append(
            {
                "user_id": user_id,
                "agent_id": agent_id,
                "dataset": "AgentSocialBench",
                "dataset_version": "template_fixture",
                "profile_ref": str(
                    profile.get("profile_ref") or f"asb://profiles/{user_id}"
                ),
                "profile_hash": "sha256:" + ("0" * 64),
            }
        )
    return sources


if __name__ == "__main__":
    raise SystemExit(main())
