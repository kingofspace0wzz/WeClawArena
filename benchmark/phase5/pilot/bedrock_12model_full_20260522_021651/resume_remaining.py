#!/usr/bin/env python3
"""Prepare and launch missing-row resume jobs for the Bedrock 12-model sweep."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
BASE_STORE = REPO / "benchmark/scenarios/v2.0.0"
RESUME = ROOT / "_resume_remaining"
PATCH = ROOT / "_patch_results"
MANIFEST = json.loads((BASE_STORE / "manifest.json").read_text(encoding="utf-8"))
ALL_ROWS = MANIFEST.get("rows") or MANIFEST.get("main") or []

MODELS = {
    "opus_41_id": "BEDROCK_OPUS_41_ID",
    "opus_47_id": "BEDROCK_OPUS_47_ID",
    "deepseek_r1": "BEDROCK_deepseek_r1",
    "deepseek_v32": "BEDROCK_deepseek_v32",
    "kimi_k25": "BEDROCK_kimi_k25",
    "kimi_k2_think": "BEDROCK_kimi_k2_think",
    "minimax_m2": "BEDROCK_minimax_m2",
    "minimax_m25": "BEDROCK_minimax_m25",
    "oss_120b": "BEDROCK_oss_120b",
    "qwen3_235b": "BEDROCK_qwen3_235b",
    "qwen3_32b": "BEDROCK_qwen3_32b",
}

PHASE5_MAX_WORKERS = 1

DOMAINS = {
    "bargaining": {
        "family": "marble_bargaining",
        "result": "BARGAINING_STRESS_RESULTS.jsonl",
        "max_turns": 36,
    },
    "swebench_workspace": {
        "family": "swebench_workspace",
        "result": "BATCH_02_standard_RESULTS.jsonl",
        "max_turns": 90,
    },
    "travel": {
        "family": "travel",
        "result": "BATCH_02_standard_RESULTS.jsonl",
        "max_turns": 36,
    },
}


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def expected_rows(domain: str) -> list[dict]:
    family = DOMAINS[domain]["family"]
    return [row for row in ALL_ROWS if row.get("family_id") == family]


def result_path(model: str, domain: str) -> Path:
    return ROOT / model / domain / DOMAINS[domain]["result"]


def missing_rows(model: str, domain: str) -> list[dict]:
    present = {row.get("variant_id") for row in read_rows(result_path(model, domain))}
    return [row for row in expected_rows(domain) if row.get("variant_id") not in present]


def make_store(model: str, domain: str, rows: list[dict]) -> Path:
    store = RESUME / "stores" / model / domain
    store.mkdir(parents=True, exist_ok=True)
    manifest = dict(MANIFEST)
    manifest["rows"] = rows
    manifest["main"] = rows
    manifest["supplementary"] = []
    (store / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for name in ("bargaining", "swebench_workspace", "travel"):
        link = store / name
        target = BASE_STORE / name
        if link.exists() or link.is_symlink():
            if link.is_symlink() and link.resolve() == target.resolve():
                continue
            raise RuntimeError(f"refusing to replace existing path: {link}")
        link.symlink_to(target, target_is_directory=True)
    return store


def merge_patch(model: str, domain: str, patch_result: Path) -> None:
    if not patch_result.exists():
        raise FileNotFoundError(patch_result)
    original = read_rows(result_path(model, domain))
    patch = read_rows(patch_result)
    by_id = {row.get("variant_id"): row for row in original if row.get("variant_id")}
    for row in patch:
        if domain == "swebench_workspace":
            row = normalize_swebench_workflow_row(row)
        variant_id = row.get("variant_id")
        if variant_id:
            by_id[variant_id] = row
    ordered = [by_id[row["variant_id"]] for row in expected_rows(domain) if row["variant_id"] in by_id]
    write_jsonl(result_path(model, domain), ordered)


def normalize_swebench_workflow_row(row: dict) -> dict:
    item = dict(row)
    extra = dict(item.get("extra") if isinstance(item.get("extra"), dict) else {})
    if "swebench_harness" not in extra:
        value = extra.get("workflow_task_success")
        if not isinstance(value, bool):
            current = item.get("task_success")
            value = current if isinstance(current, bool) else None
        extra["workflow_task_success"] = value
        item["task_success"] = None
    item["extra"] = extra
    return item


def write_model_script(model: str, jobs: list[tuple[str, int]]) -> Path:
    script = RESUME / "scripts" / f"{model}.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    env_var = MODELS[model]
    lines = [
        "#!/usr/bin/env bash",
        "set -u",
        f"cd {REPO}",
        "set -a",
        ". ./.env",
        "set +a",
        f'model_id="${{{env_var}:-}}"',
        'if [ -z "$model_id" ]; then echo "missing model id" >&2; exit 2; fi',
        f'echo "[$(date -Is)] resume start model={model}" | tee -a "{ROOT / model / "resume.log"}"',
    ]
    for domain, _count in jobs:
        store = RESUME / "stores" / model / domain
        out = PATCH / model / domain
        max_turns = DOMAINS[domain]["max_turns"]
        lines.append(f'echo "[$(date -Is)] start {domain}" | tee -a "{ROOT / model / "resume.log"}"')
        if domain == "bargaining":
            lines.append(
                "PYTHONPATH=. .venv/bin/python scripts/run_bargaining_stress_calibration.py "
                f"--store {store} --out-dir {out} --agent-model \"$model_id\" "
                f"--max-turns {max_turns} --modes no_attacker,collaboration,security,privacy,governance "
                "--audit-condition passive --simulation-attempts 1 --quiet"
            )
            patch_result = out / "BARGAINING_STRESS_RESULTS.jsonl"
        else:
            lines.append(
                "COMPOSE_BAKE=true PYTHONPATH=. .venv/bin/python scripts/run_phase5_pilot.py run-batch "
                f"--manifest {store / 'manifest.json'} --base-dir {store} --store {store} "
                f"--out-dir {out} --batch 2 --executor docker --mode full "
                f"--filter family={DOMAINS[domain]['family']} --agent-model \"$model_id\" "
                f"--max-turns {max_turns} --max-workers {PHASE5_MAX_WORKERS} --quiet"
            )
            patch_result = out / "BATCH_02_standard_RESULTS.jsonl"
        lines.append(
            f"PYTHONPATH=. .venv/bin/python {ROOT / 'resume_remaining.py'} "
            f"--merge-only {model} {domain} {patch_result}"
        )
        lines.append(f'echo "[$(date -Is)] end {domain} status=$?" | tee -a "{ROOT / model / "resume.log"}"')
    lines.append(f'echo "[$(date -Is)] resume done model={model}" | tee -a "{ROOT / model / "resume.log"}"')
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def launch() -> None:
    RESUME.mkdir(parents=True, exist_ok=True)
    PATCH.mkdir(parents=True, exist_ok=True)
    plan: dict[str, list[tuple[str, int]]] = {}
    for model in MODELS:
        for domain in DOMAINS:
            rows = missing_rows(model, domain)
            if rows:
                make_store(model, domain, rows)
                plan.setdefault(model, []).append((domain, len(rows)))

    (RESUME / "plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for model, jobs in plan.items():
        script = write_model_script(model, jobs)
        session = f"csa12_resume_{model}"
        subprocess.run(["screen", "-S", session, "-X", "quit"], check=False)
        subprocess.run(["screen", "-dmS", session, "bash", str(script)], check=True)
        print(session, jobs)
    print("models_launched", len(plan))


def main(argv: list[str]) -> int:
    if argv[:1] == ["--merge-only"]:
        if len(argv) != 4:
            raise SystemExit("--merge-only MODEL DOMAIN PATCH_RESULT")
        merge_patch(argv[1], argv[2], Path(argv[3]))
        return 0
    launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
