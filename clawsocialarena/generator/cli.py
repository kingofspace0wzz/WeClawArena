"""Scenario generator CLI.

Usage:
    python -m clawsocialarena.generator.cli \\
        --category CU --family scheduling --n 10 --seed 42 \\
        --out /tmp/generated

Emits, for each scenario, a directory at <out>/<scenario_id>/ containing
scenario.json + scenario.gt.json.

Phase 4 scope: deterministic instantiation only (no LLM calls). LLM-assisted
profile expansion will land in Phase 4.2 via --instantiation-mode=llm once the
LLMClient plumbing is wired.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from clawsocialarena.generator.attack_injection import AttackType, inject_attack
from clawsocialarena.generator.gt_assembly import (
    assemble_gt_bundle,
    assemble_scenario_json,
)
from clawsocialarena.generator.instantiation import instantiate
from clawsocialarena.generator.registry import get_template, list_registered
from clawsocialarena.generator.template import CategoryCode, TaskFamily


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clawsocialarena.generator",
        description="Generate ClawSocialArena scenarios (scenario.json + scenario.gt.json).",
    )
    p.add_argument(
        "--category",
        type=CategoryCode,
        choices=list(CategoryCode),
        required=True,
        help="Scenario category code (CD/MC/CU/MG/HS/CM/AM).",
    )
    p.add_argument(
        "--family",
        type=TaskFamily,
        choices=list(TaskFamily),
        required=True,
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
        required=True,
        help="Output directory. Creates <out>/<scenario_id>/ per scenario.",
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

    if args.attack is not None and not args.attacker_agent:
        print("--attacker-agent is required when --attack is set", file=sys.stderr)
        return 2

    try:
        template = get_template(args.category, args.family)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 2

    out_root: Path = args.out
    out_root.mkdir(parents=True, exist_ok=True)

    for i in range(args.n):
        scenario_id = f"{args.category.value.lower()}-{args.family.value}-{args.seed}-{i:03d}"
        shape = instantiate(
            template, seed=args.seed + i, scenario_id=scenario_id
        )
        if args.attack is not None:
            shape = inject_attack(
                shape=shape,
                attack_type=args.attack,
                attacker_agent_id=args.attacker_agent,
            )

        out_dir = out_root / scenario_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "scenario.json").write_text(
            json.dumps(assemble_scenario_json(shape), indent=2, ensure_ascii=False)
        )
        (out_dir / "scenario.gt.json").write_text(
            json.dumps(assemble_gt_bundle(shape), indent=2, ensure_ascii=False)
        )
        print(f"wrote {out_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
