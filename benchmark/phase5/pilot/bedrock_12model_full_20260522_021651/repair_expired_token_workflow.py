#!/usr/bin/env python3
"""Repair ExpiredTokenException rows and resume dependent evaluations."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
PYTHON = REPO / ".venv/bin/python"
WORK = ROOT / "_expired_token_repair"

SONNET_MODEL = "sonnet_45_id"
QWEN_MODEL = "qwen3_235b"
ATTACK_MODES = ("collaboration", "security", "privacy", "governance")
ALL_MODES = ("no_attacker", *ATTACK_MODES)
EXPIRED_MARKERS = (
    "ExpiredTokenException",
    "security token included in the request is expired",
)


def main() -> int:
    args = parse_args()
    log("repair workflow start")
    cleanup_done = cleanup_expired_rows()
    if args.cleanup_only:
        log("cleanup-only requested")
        update_live_results()
        return 0
    if cleanup_done["sonnet_swe"]:
        rerun_sonnet_swe(cleanup_done["sonnet_swe"])
        rerun_sonnet_swe_strict()
        rerun_domain_asr(SONNET_MODEL, "swebench_workspace", expected=200)
    if cleanup_done["qwen_bidding"]:
        rerun_qwen_bidding(cleanup_done["qwen_bidding"])
        rerun_bidding_asr(QWEN_MODEL)
    update_live_results()
    launch_remaining_monitor()
    log("repair workflow complete; remaining monitor is running")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup-only", action="store_true")
    return parser.parse_args()


def cleanup_expired_rows() -> dict[str, set[str]]:
    WORK.mkdir(parents=True, exist_ok=True)
    out: dict[str, set[str]] = {"sonnet_swe": set(), "qwen_bidding": set()}

    sonnet_results = ROOT / SONNET_MODEL / "swebench_workspace" / "BATCH_02_standard_RESULTS.jsonl"
    out["sonnet_swe"] = expired_variant_ids(sonnet_results)
    if out["sonnet_swe"]:
        filter_jsonl(sonnet_results, out["sonnet_swe"])
        filter_jsonl(
            ROOT / "_llm_asr_inputs" / SONNET_MODEL / "swebench_workspace_attack_modes.jsonl",
            out["sonnet_swe"],
        )
        filter_jsonl(
            ROOT / "_llm_asr" / SONNET_MODEL / "swebench_workspace_attack_modes_ASR.jsonl",
            out["sonnet_swe"],
            drop_all_expired=True,
        )
        reset_strict_swe(SONNET_MODEL)
        log(f"removed sonnet swe expired rows: {len(out['sonnet_swe'])}")

    qwen_results = (
        REPO
        / "benchmark/phase5/pilot/bidding_v2_1_0_11model_20260524_105507"
        / QWEN_MODEL
        / "BATCH_02_standard_RESULTS.jsonl"
    )
    out["qwen_bidding"] = expired_variant_ids(qwen_results)
    if out["qwen_bidding"]:
        filter_jsonl(qwen_results, out["qwen_bidding"])
        filter_jsonl(qwen_results.with_name("BATCH_02_standard_RESULTS.bidding_asr.jsonl"), out["qwen_bidding"])
        log(f"removed qwen bidding expired rows: {len(out['qwen_bidding'])}")

    update_live_results()
    return out


def rerun_sonnet_swe(variant_ids: set[str]) -> None:
    store = make_slim_store(
        name="sonnet_swe",
        source_store=REPO / "benchmark/scenarios/v2.0.0",
        variant_ids=variant_ids,
        family="swebench_workspace",
    )
    patch_dir = WORK / "patch" / SONNET_MODEL / "swebench_workspace"
    env_name = "BEDROCK_SONNET_45_ID"
    run_batch(
        store=store,
        out_dir=patch_dir,
        family="swebench_workspace",
        model_env=env_name,
        max_turns=90,
        max_workers=1,
    )
    patch_results = patch_dir / "BATCH_02_standard_RESULTS.jsonl"
    merge_rows(
        target=ROOT / SONNET_MODEL / "swebench_workspace" / "BATCH_02_standard_RESULTS.jsonl",
        patch=patch_results,
        source_store=REPO / "benchmark/scenarios/v2.0.0",
        family="swebench_workspace",
    )
    update_live_results()


def rerun_qwen_bidding(variant_ids: set[str]) -> None:
    store = make_slim_store(
        name="qwen_bidding_v2_1",
        source_store=REPO / "benchmark/scenarios/v2.0.0",
        variant_ids=variant_ids,
        family="marble_bidding",
    )
    patch_dir = WORK / "patch" / "bidding_v2_1" / QWEN_MODEL
    run_batch(
        store=store,
        out_dir=patch_dir,
        family="marble_bidding",
        model_env="BEDROCK_qwen3_235b",
        max_turns=60,
        max_workers=1,
    )
    target_dir = (
        REPO
        / "benchmark/phase5/pilot/bidding_v2_1_0_11model_20260524_105507"
        / QWEN_MODEL
    )
    merge_rows(
        target=target_dir / "BATCH_02_standard_RESULTS.jsonl",
        patch=patch_dir / "BATCH_02_standard_RESULTS.jsonl",
        source_store=REPO / "benchmark/scenarios/v2.0.0",
        family="marble_bidding",
    )


def rerun_sonnet_swe_strict() -> None:
    log("rerunning true SWE-bench TSR for sonnet swebench_workspace")
    run(
        [
            str(PYTHON),
            str(ROOT / "run_completed_swebench_strict.py"),
            "--models",
            SONNET_MODEL,
            "--modes",
            *ALL_MODES,
            "--max-workers",
            "1",
            "--timeout",
            "1800",
        ]
    )
    update_live_results()


def rerun_domain_asr(model: str, domain: str, *, expected: int) -> None:
    rows = read_jsonl(ROOT / model / domain / "BATCH_02_standard_RESULTS.jsonl")
    attack_rows = [row for row in rows if row.get("attack_mode") in ATTACK_MODES]
    if len(attack_rows) != expected:
        raise RuntimeError(f"{model}/{domain} attack rows {len(attack_rows)} != {expected}")
    input_path = ROOT / "_llm_asr_inputs" / model / f"{domain}_attack_modes.jsonl"
    out_path = ROOT / "_llm_asr" / model / f"{domain}_attack_modes_ASR.jsonl"
    write_jsonl(input_path, attack_rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log(f"rerunning {model}/{domain} LLM-ASR rows={len(attack_rows)}")
    run(
        [
            str(PYTHON),
            "-m",
            "clawsocialarena.eval.workspace_asr_judge",
            "--input-jsonl",
            str(input_path),
            "--output-jsonl",
            str(out_path),
            "--run-dir",
            str(ROOT / model / domain),
            "--judge-model",
            os.environ["BEDROCK_OPUS_47_ID"],
            "--max-workers",
            "1",
        ]
    )
    update_live_results()


def rerun_bidding_asr(model: str) -> None:
    model_dir = (
        REPO
        / "benchmark/phase5/pilot/bidding_v2_1_0_11model_20260524_105507"
        / model
    )
    log(f"rerunning bidding v2.1 ASR for {model}")
    run(
        [
            str(PYTHON),
            "-m",
            "clawsocialarena.eval.bidding_asr_judge",
            "--batch-results",
            str(model_dir / "BATCH_02_standard_RESULTS.jsonl"),
            "--base-dir",
            str(model_dir),
            "--out",
            str(model_dir / "BATCH_02_standard_RESULTS.bidding_asr.jsonl"),
            "--judge-model",
            os.environ["BEDROCK_OPUS_47_ID"],
            "--max-workers",
            "1",
        ],
        stdout=model_dir / "bidding_asr_judge.summary.json",
    )
    update_live_results()


def launch_remaining_monitor() -> None:
    session = "csa_remaining_workflow"
    subprocess.run(["screen", "-S", session, "-X", "quit"], cwd=REPO, check=False)
    cmd = (
        "set -a; . ./.env; set +a; "
        f"PYTHONPATH=. {PYTHON} {ROOT / 'resume_remaining.py'} "
        f"> {ROOT / '_remaining_workflow_monitor.log'} 2>&1"
    )
    subprocess.run(["screen", "-dmS", session, "bash", "-lc", cmd], cwd=REPO, check=True)
    log(f"launched {session}")


def run_batch(
    *,
    store: Path,
    out_dir: Path,
    family: str,
    model_env: str,
    max_turns: int,
    max_workers: int,
) -> None:
    model_id = os.environ.get(model_env)
    if not model_id:
        raise RuntimeError(f"missing {model_env}")
    log(f"rerunning raw rows family={family} out={out_dir}")
    run(
        [
            str(PYTHON),
            "scripts/run_phase5_pilot.py",
            "run-batch",
            "--manifest",
            str(store / "manifest.json"),
            "--base-dir",
            str(store),
            "--store",
            str(store),
            "--out-dir",
            str(out_dir),
            "--batch",
            "2",
            "--executor",
            "docker",
            "--mode",
            "full",
            "--filter",
            f"family={family}",
            "--agent-model",
            model_id,
            "--max-turns",
            str(max_turns),
            "--max-workers",
            str(max_workers),
            "--quiet",
        ]
    )


def make_slim_store(
    *,
    name: str,
    source_store: Path,
    variant_ids: set[str],
    family: str,
) -> Path:
    rows = read_manifest_rows(source_store / "manifest.json")
    selected = [
        row for row in rows
        if row.get("family_id") == family and str(row.get("variant_id")) in variant_ids
    ]
    if len(selected) != len(variant_ids):
        found = {str(row.get("variant_id")) for row in selected}
        missing = sorted(variant_ids - found)
        raise RuntimeError(f"manifest missing {len(missing)} rows for {name}: {missing[:5]}")
    store = WORK / "stores" / name
    store.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((source_store / "manifest.json").read_text(encoding="utf-8"))
    manifest["rows"] = selected
    manifest["main"] = selected
    manifest["supplementary"] = []
    manifest["n_variants"] = len(selected)
    manifest["n_bases"] = len({row.get("base_id") for row in selected})
    (store / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for row in selected:
        first = str(row["bundle_dir"]).split("/", 1)[0]
        src = source_store / first
        dst = store / first
        if not dst.exists():
            dst.symlink_to(src.resolve(), target_is_directory=True)
    return store


def merge_rows(*, target: Path, patch: Path, source_store: Path, family: str) -> None:
    target_rows = read_jsonl(target)
    patch_rows = read_jsonl(patch)
    patch_ids = {str(row.get("variant_id")) for row in patch_rows}
    if not patch_rows:
        raise RuntimeError(f"patch produced no rows: {patch}")
    merged = [row for row in target_rows if str(row.get("variant_id")) not in patch_ids]
    merged.extend(patch_rows)
    order = {
        str(row["variant_id"]): idx
        for idx, row in enumerate(read_manifest_rows(source_store / "manifest.json"))
        if row.get("family_id") == family
    }
    merged.sort(key=lambda row: order.get(str(row.get("variant_id")), 10**9))
    write_jsonl(target, merged)
    if any(is_expired(row) for row in merged):
        raise RuntimeError(f"expired token rows remain after merge: {target}")
    log(f"merged repaired rows target={target} rows={len(merged)}")


def reset_strict_swe(model: str) -> None:
    strict = ROOT / "_swebench_harness_strict" / model
    if strict.exists():
        backup = WORK / "strict_backups" / model
        if backup.exists():
            shutil.rmtree(backup)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(strict), str(backup))
        log(f"moved stale strict swe artifacts to {backup}")


def filter_jsonl(path: Path, variant_ids: set[str], *, drop_all_expired: bool = False) -> None:
    if not path.exists():
        return
    rows = read_jsonl(path)
    kept = []
    removed = []
    for row in rows:
        variant_id = str(row.get("variant_id") or "")
        drop = variant_id in variant_ids or (drop_all_expired and is_expired(row))
        if drop:
            removed.append(row)
        else:
            kept.append(row)
    if removed:
        backup = WORK / "removed_rows" / (path.as_posix().replace("/", "__") + ".jsonl")
        write_jsonl(backup, removed)
        write_jsonl(path, kept)
        log(f"filtered {len(removed)} rows from {path}")


def expired_variant_ids(path: Path) -> set[str]:
    return {
        str(row.get("variant_id"))
        for row in read_jsonl(path)
        if row.get("variant_id") and is_expired(row)
    }


def is_expired(row: dict[str, Any]) -> bool:
    text = json.dumps(row, sort_keys=True)
    return any(marker in text for marker in EXPIRED_MARKERS)


def read_manifest_rows(path: Path) -> list[dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    rows = manifest.get("main") or manifest.get("rows") or []
    return list(rows)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def update_live_results() -> None:
    subprocess.run([str(PYTHON), str(ROOT / "update_live_results.py"), "--root", str(ROOT)], cwd=REPO, check=False)


def run(cmd: list[str], *, stdout: Path | None = None) -> None:
    log("$ " + " ".join(cmd))
    if stdout is None:
        subprocess.run(cmd, cwd=REPO, check=True)
    else:
        stdout.parent.mkdir(parents=True, exist_ok=True)
        with stdout.open("w", encoding="utf-8") as handle:
            subprocess.run(cmd, cwd=REPO, check=True, stdout=handle)


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    print(f"[{stamp}] {message}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
