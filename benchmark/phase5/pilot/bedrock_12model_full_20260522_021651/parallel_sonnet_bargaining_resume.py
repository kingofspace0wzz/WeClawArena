#!/usr/bin/env python3
"""Run remaining Sonnet bargaining rows in parallel chunks and merge them."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
BASE_STORE = REPO / "benchmark/scenarios/v2.0.0"
WORK = ROOT / "_resume_remaining_parallel" / "sonnet_45_id" / "bargaining"
BASE_PATCH = ROOT / "_patch_results/sonnet_45_id/bargaining/BARGAINING_STRESS_RESULTS.jsonl"
MAIN = ROOT / "sonnet_45_id/bargaining/BARGAINING_STRESS_RESULTS.jsonl"
COMBINED = WORK / "combined" / "BARGAINING_STRESS_RESULTS.jsonl"
LOG = WORK / "parallel_watch.log"
SCREEN_PREFIX = "csa_sonnet_barg_part_"
MODEL_ENV = "BEDROCK_SONNET_45_ID"
EXPECTED = 120
ERROR_MARKERS = (
    "ExpiredTokenException",
    "security token included in the request is expired",
    "ValidationException",
    "provided model identifier is invalid",
)


def main() -> int:
    args = parse_args()
    if args.watch:
        return watch_and_merge()
    return launch(args.parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parts", type=int, default=4)
    parser.add_argument("--watch", action="store_true")
    return parser.parse_args()


def launch(parts: int) -> int:
    model_id = os.environ.get(MODEL_ENV)
    if not model_id:
        raise RuntimeError(f"missing {MODEL_ENV}")
    remaining = remaining_manifest_rows()
    if not remaining:
        log("no remaining rows; launching watcher only")
    chunks = split_rows(remaining, max(1, parts))
    plan = []
    for idx, rows in enumerate(chunks):
        if not rows:
            continue
        store = write_store(idx, rows)
        out_dir = WORK / "patch_parts" / f"part_{idx:02d}"
        script = write_part_script(idx, store, out_dir, model_id)
        session = f"{SCREEN_PREFIX}{idx:02d}"
        subprocess.run(["screen", "-S", session, "-X", "quit"], cwd=REPO, check=False)
        subprocess.run(["screen", "-dmS", session, "bash", str(script)], cwd=REPO, check=True)
        plan.append(
            {
                "session": session,
                "rows": len(rows),
                "variant_ids": [str(row["variant_id"]) for row in rows],
                "out_dir": str(out_dir),
            }
        )
        log(f"launched {session} rows={len(rows)}")
    (WORK / "plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    watcher = "csa_sonnet_barg_parallel_watch"
    subprocess.run(["screen", "-S", watcher, "-X", "quit"], cwd=REPO, check=False)
    subprocess.run(
        [
            "screen",
            "-dmS",
            watcher,
            "bash",
            "-lc",
            f"set -a; . ./.env; set +a; PYTHONPATH=. {REPO / '.venv/bin/python'} {Path(__file__).resolve()} --watch",
        ],
        cwd=REPO,
        check=True,
    )
    log(f"launched {watcher}")
    return 0


def watch_and_merge() -> int:
    while True:
        update_live_results()
        active = active_part_sessions()
        log(f"watch active_parts={active} base_rows={count_jsonl(BASE_PATCH)} part_rows={part_row_count()}")
        if active == 0:
            break
        time.sleep(120)
    combined = combine_rows()
    if len(combined) < EXPECTED:
        log(f"not merging: only {len(combined)}/{EXPECTED} combined rows")
        return 1
    write_jsonl(COMBINED, combined)
    if scan_markers(COMBINED):
        log("not merging: token/model validation markers found in combined rows")
        return 1
    run([str(REPO / ".venv/bin/python"), str(ROOT / "resume_remaining.py"), "--merge-only", "sonnet_45_id", "bargaining", str(COMBINED)])
    update_live_results()
    if count_jsonl(MAIN) < EXPECTED:
        log(f"not committing: main rows={count_jsonl(MAIN)}")
        return 1
    if scan_markers(MAIN):
        log("not committing: token/model validation markers found in main rows")
        return 1
    run(["git", "add", "-u"])
    run(["git", "add", "-f", str(MAIN), str(Path(__file__).resolve()), str(COMBINED)])
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO).returncode == 0:
        log("nothing to commit")
        return 0
    run(["git", "commit", "-m", "Add completed Sonnet bargaining results"])
    run(["git", "push", "origin", "HEAD:main"])
    log(f"committed and pushed {git_head()}")
    return 0


def remaining_manifest_rows() -> list[dict]:
    existing = {str(row.get("variant_id")) for row in read_jsonl(BASE_PATCH)}
    existing.update(str(row.get("variant_id")) for row in read_jsonl(MAIN))
    rows = [
        row
        for row in manifest_rows()
        if row.get("family_id") == "marble_bargaining"
        and str(row.get("variant_id")) not in existing
    ]
    log(f"remaining rows={len(rows)} existing={len(existing)}")
    return rows


def manifest_rows() -> list[dict]:
    manifest = json.loads((BASE_STORE / "manifest.json").read_text(encoding="utf-8"))
    return list(manifest.get("rows") or manifest.get("main") or [])


def split_rows(rows: list[dict], parts: int) -> list[list[dict]]:
    chunks = [[] for _ in range(parts)]
    for idx, row in enumerate(rows):
        chunks[idx % parts].append(row)
    return chunks


def write_store(idx: int, rows: list[dict]) -> Path:
    store = WORK / "stores" / f"part_{idx:02d}"
    store.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((BASE_STORE / "manifest.json").read_text(encoding="utf-8"))
    manifest["rows"] = rows
    manifest["main"] = rows
    manifest["supplementary"] = []
    manifest["n_variants"] = len(rows)
    manifest["n_bases"] = len({row.get("base_id") for row in rows})
    (store / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    link = store / "bargaining"
    target = BASE_STORE / "bargaining"
    if not link.exists():
        link.symlink_to(target, target_is_directory=True)
    return store


def write_part_script(idx: int, store: Path, out_dir: Path, model_id: str) -> Path:
    script = WORK / "scripts" / f"part_{idx:02d}.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    part_log = WORK / "logs" / f"part_{idx:02d}.log"
    script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -u",
                f"cd {REPO}",
                f"mkdir -p {part_log.parent}",
                f"echo \"[$(date -Is)] start part_{idx:02d}\" | tee -a {part_log}",
                "PYTHONPATH=. .venv/bin/python scripts/run_bargaining_stress_calibration.py "
                f"--store {store} --out-dir {out_dir} --agent-model {json.dumps(model_id)} "
                "--max-turns 36 --modes no_attacker,collaboration,security,privacy,governance "
                "--audit-condition passive --simulation-attempts 1 --quiet "
                f">> {part_log} 2>&1",
                f"status=$?",
                f"echo \"[$(date -Is)] end part_{idx:02d} status=$status\" | tee -a {part_log}",
                "exit $status",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def active_part_sessions() -> int:
    proc = subprocess.run(["screen", "-ls"], cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return sum(1 for line in proc.stdout.splitlines() if SCREEN_PREFIX in line)


def part_row_count() -> int:
    return sum(count_jsonl(path) for path in (WORK / "patch_parts").glob("part_*/BARGAINING_STRESS_RESULTS.jsonl"))


def combine_rows() -> list[dict]:
    by_id: dict[str, dict] = {}
    for row in read_jsonl(BASE_PATCH):
        if row.get("variant_id"):
            by_id[str(row["variant_id"])] = row
    for path in sorted((WORK / "patch_parts").glob("part_*/BARGAINING_STRESS_RESULTS.jsonl")):
        for row in read_jsonl(path):
            if row.get("variant_id"):
                by_id[str(row["variant_id"])] = row
    order = {
        str(row["variant_id"]): idx
        for idx, row in enumerate(manifest_rows())
        if row.get("family_id") == "marble_bargaining"
    }
    out = list(by_id.values())
    out.sort(key=lambda row: order.get(str(row.get("variant_id")), 10**9))
    log(f"combined rows={len(out)}")
    return out


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def count_jsonl(path: Path) -> int:
    return len(read_jsonl(path))


def scan_markers(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    return sum(text.count(marker) for marker in ERROR_MARKERS)


def update_live_results() -> None:
    subprocess.run([str(REPO / ".venv/bin/python"), str(ROOT / "update_live_results.py"), "--root", str(ROOT)], cwd=REPO, check=False)


def run(cmd: list[str]) -> None:
    log("$ " + " ".join(cmd))
    subprocess.run(cmd, cwd=REPO, check=True)


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()


def log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
