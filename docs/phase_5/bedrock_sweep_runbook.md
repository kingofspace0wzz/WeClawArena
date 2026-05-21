# Bedrock Multi-Model Sweep Runbook (v2.0.0)

This runbook documents `scripts/launch_bedrock_v2_0_0_sweep.sh`, which runs
the full 5-mode v2.0.0 sweep across the four published scenario families
(`bargaining`, `bidding`, `swebench_workspace`, `travel`) against two
Anthropic Claude models served by AWS Bedrock. It is the multi-model
complement to the per-family READMEs:

- `benchmark/scenarios/v2.0.0/bargaining/README.md`
- `benchmark/scenarios/v2.0.0/bidding/README.md`
- `benchmark/scenarios/v2.0.0/swebench_workspace/README.md`
- `benchmark/scenarios/v2.0.0/travel/README.md`

## Scope

Each (family, model) pair runs as one `screen` session, eight sessions total:

| Scenario | Rows (5 modes) | Cap turns | Workers |
|---|---:|---:|---:|
| bargaining | 24 × 5 = 120 | 36 | runner default |
| bidding | 12 × 5 = 60 | 36 | 1 |
| swebench_workspace | 50 × 5 = 250 | 90 | 4 |
| travel | 20 × 5 = 100 | 36 | 4 |

Modes per sweep: `no_attacker, collaboration, security, privacy, governance`.

Per-model totals: **530 rows**. Both models together: **1060 rows**.

## Default Bedrock Model IDs

Override via env when launching; defaults assume the global cross-region
inference profiles enabled on AWS account `<AWS_ACCOUNT_ID>`:

| Tag | Default `--agent-model` |
|---|---|
| `sonnet46` | `global.anthropic.claude-sonnet-4-6` |
| `opus47` | `global.anthropic.claude-opus-4-7` |

Both invoke cleanly from any region (the launcher does not set
`BEDROCK_REGION`, so the boto3 client uses `AWS_REGION` /
`AWS_DEFAULT_REGION` or falls back to `us-east-1`).

## Bedrock Wiring

`--agent-model` flows verbatim into `ProviderDispatchClient`
(`clawsocialarena/llm/openai_client.py`), which routes model ids matching
`anthropic.*`, `us.anthropic.*`, `eu.anthropic.*`, `apac.anthropic.*`, or
`global.anthropic.*` (case-insensitive) to `BedrockJsonClient`
(`clawsocialarena/llm/bedrock_client.py`). The Bedrock client speaks the
Anthropic Messages API on Bedrock via `boto3.client("bedrock-runtime")` and
adapts OpenAI Responses-API tool schemas to the Anthropic
`{"name", "input_schema"}` shape, then maps `tool_use` / `text` content
blocks back into the existing `OpenAIToolCall` / `OpenAIToolCallResult`
types so downstream code remains provider-agnostic. GPT-style ids continue
to route through `OpenAIResponsesJsonClient`.

Useful env vars (all optional):

| Var | Default | Effect |
|---|---|---|
| `BEDROCK_REGION` | `AWS_REGION` → `AWS_DEFAULT_REGION` → `us-east-1` | Region for `bedrock-runtime` |
| `BEDROCK_REQUEST_TIMEOUT_SECONDS` | 300 | `read_timeout` on the boto3 client |
| `BEDROCK_MAX_TOKENS` | 4096 | `max_tokens` on every Messages request |

## Prerequisites

Run from the repo root.

1. **AWS credentials** that can call `bedrock-runtime:InvokeModel` on the
   chosen inference profile. The launcher does not source `.env`-style AWS
   keys; it relies on the standard boto3 chain
   (`~/.aws/credentials` / `AWS_*` env vars / IAM role).
2. **Docker daemon** running. Each row spins compose containers.
3. **Project venv** at `.venv/`. The committed pyproject does not pin
   `jinja2` (used by `compose_emitter.py`) or `scipy` as runtime deps, so
   install both:

   ```bash
   uv sync --extra dev
   ```

4. **pnpm-workspace allowlist.** The gateway plugin's Docker build runs
   `pnpm install --frozen-lockfile`, and pnpm 11 (corepack default) rejects
   any transitive postinstall script that is not approved. The committed
   `gateway_plugin/pnpm-workspace.yaml` carries the allowlist with the eight
   transitive openclaw deps flipped to `true`. If you regenerate the
   workspace file via `pnpm approve-builds`, double-check it still lists
   `esbuild`, `sharp`, `koffi`, `@discordjs/opus`,
   `@matrix-org/matrix-sdk-crypto-nodejs`, `@whiskeysockets/baileys`,
   `protobufjs`, and `openclaw` as `true`. The Dockerfile's install-cache
   COPY step (line 32 in `docker/openclaw-with-plugin.Dockerfile`) must
   include `gateway_plugin/pnpm-workspace.yaml` so the file is present
   when install runs.

5. **Build-context symlink (Linux hosts only).** The committed
   `docker-compose.yml` files under `benchmark/scenarios/v2.0.0/**` hardcode
   the original author's macOS build context:
   `/Users/princewang/llm/mas/clawsocialarena`. To let `docker compose build`
   resolve on a Linux host without rewriting 1260 files:

   ```bash
   sudo mkdir -p /Users/princewang/llm/mas
   sudo ln -sfn "$(pwd)" /Users/princewang/llm/mas/clawsocialarena
   ```

   The symlink is reversible (`sudo rm -rf /Users`). The long-term fix is
   to teach `compose_emitter.py` to write the build context relative to
   the repo root or read it from an env var; that is out of scope for the
   sweep itself.

## Launch

Inspect the plan first:

```bash
bash scripts/launch_bedrock_v2_0_0_sweep.sh --dry-run
```

Launch all eight sessions in detached `screen` mode:

```bash
bash scripts/launch_bedrock_v2_0_0_sweep.sh
```

Output lands under `benchmark/phase5/pilot/bedrock_sweep_<timestamp>/`
with one subdirectory per (scenario, model) pair. Each subdirectory holds
the runner's `BATCH_02_standard_RESULTS.jsonl` / `_REPORT.json` (or, for
bargaining, `BARGAINING_STRESS_RESULTS.jsonl` / `_REPORT.json`) plus the
session's `run.log`.

Override a model id for one run:

```bash
BEDROCK_SONNET_46_ID=global.anthropic.claude-sonnet-4-6 \
BEDROCK_OPUS_47_ID=global.anthropic.claude-opus-4-7 \
bash scripts/launch_bedrock_v2_0_0_sweep.sh
```

Land into an existing run dir (relaunching one model after the other
finished, for example) by exporting `OUT_ROOT`. The launcher uses the
provided path verbatim and the per-screen `mkdir -p` is idempotent, so
sessions that already exist for the other model are skipped while the
new sessions land alongside the prior results:

```bash
OUT_ROOT=benchmark/phase5/pilot/bedrock_sweep_20260520_093504 \
bash scripts/launch_bedrock_v2_0_0_sweep.sh
```

## Monitoring

```bash
screen -ls | grep csa_                                  # session list
screen -r csa_swebench_sonnet46                         # attach (Ctrl-A d detaches)
tail -f benchmark/phase5/pilot/bedrock_sweep_*/swebench_workspace_*/run.log
```

Session naming: `csa_<scenario>_<model_tag>` where `<scenario>` is
`bargaining` / `bidding` / `swebench` / `travel` and `<model_tag>` is
`sonnet46` / `opus47`.

## SWE-bench Workspace Strict Task Success

The `swebench_workspace` Phase 5 run records workflow completion. For the
single reportable `task_success` value, post-process each reported mode through
the official SWE-bench harness and merge the result back:

```bash
.venv/bin/python scripts/export_swebench_workspace_predictions.py \
  benchmark/phase5/pilot/<run>/swebench_workspace_<model>/BATCH_02_standard_RESULTS.jsonl \
  --store benchmark/scenarios/v2.0.0 \
  --mode no_attacker \
  --model-name <model> \
  --out benchmark/phase5/pilot/<run>/swebench_workspace_<model>/swebench_no_attacker_predictions.jsonl

python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --predictions_path benchmark/phase5/pilot/<run>/swebench_workspace_<model>/swebench_no_attacker_predictions.jsonl \
  --max_workers 8 \
  --run_id weclaw_<model>_no_attacker

.venv/bin/python scripts/merge_swebench_harness_results.py \
  benchmark/phase5/pilot/<run>/swebench_workspace_<model>/BATCH_02_standard_RESULTS.jsonl \
  --predictions-map benchmark/phase5/pilot/<run>/swebench_workspace_<model>/swebench_no_attacker_predictions.jsonl.map.jsonl \
  --harness-results evaluation_results/<run_id>/instance_results.jsonl \
  --out-results benchmark/phase5/pilot/<run>/swebench_workspace_<model>/BATCH_02_standard_RESULTS.strict.jsonl \
  --out-report benchmark/phase5/pilot/<run>/swebench_workspace_<model>/BATCH_02_standard_RESULTS.strict.report.json
```

Run the same export, harness, and merge sequence per attack mode before quoting
mode-specific utility. The merged strict file preserves the workflow-only value
as `extra.workflow_task_success` and sets `task_success` to:

```text
workflow_task_success AND swebench_harness.resolved
```

## Post-Run

Per-family LLM-ASR judge invocations are unchanged from the per-family
READMEs. The Bedrock dispatch also applies to the judge model when you
pass an `anthropic.*` id to `--judge-model`. To keep the judge on OpenAI,
pass a non-Bedrock id (for example `gpt-5.2`).

## Parse-Error Retry

Both Sonnet 4.6 and Opus 4.7 occasionally wrap a valid JSON response in
conversational preamble (`I'll start by ...\n\n```json\n{...}\n```\n`).
The agent loop's `_loads_response_json_object()` now invokes
`_salvage_first_json_object()` (in `clawsocialarena/llm/openai_client.py`)
to recover the inner object via fenced-block regex plus a brace-counting
parser that respects string boundaries. Rows that errored out before
the salvage landed can be rerun in isolation without touching the rest
of the sweep:

1. Enumerate parse-error variant_ids per scenario:

   ```bash
   python3 - <<'PY'
   import json, os
   root = "benchmark/phase5/pilot/bedrock_sweep_<stamp>"
   scens = {
       "bargaining_opus47":         ("BARGAINING_STRESS_RESULTS.jsonl", "marble_bargaining"),
       "bidding_opus47":            ("BATCH_02_standard_RESULTS.jsonl", "marble_bidding"),
       "swebench_workspace_opus47": ("BATCH_02_standard_RESULTS.jsonl", "swebench_workspace"),
       "travel_opus47":             ("BATCH_02_standard_RESULTS.jsonl", "travel"),
   }
   out = {}
   for sd, (fname, family) in scens.items():
       rows = []
       with open(os.path.join(root, sd, fname)) as f:
           for line in f:
               r = json.loads(line)
               err = r.get("error") or ""
               if "Expecting" in err or "Unterminated string" in err:
                   rows.append({k: r.get(k) for k in (
                       "variant_id","base_scenario_id","attack_mode",
                       "family_id","task_index","tier_index",
                   )} | {"error": err[:120]})
       out[sd] = {"family": family, "n": len(rows), "rows": rows}
   open(os.path.join(root, "retry_index.json"), "w").write(
       json.dumps(out, indent=2, sort_keys=True))
   PY
   ```

2. Launch 4 retry screens (one per scenario). The helper builds a slim
   in-memory manifest containing only the listed `variant_id`s for the
   phase5 families, and calls `run_bargaining_stress_calibration`'s
   `run_calibration_rows()` with hand-trimmed rows for bargaining:

   ```bash
   bash scripts/launch_parse_error_retry.sh benchmark/phase5/pilot/bedrock_sweep_<stamp>
   ```

   Output lands in `<run_dir>/<scen>_retry/` with the same RESULTS /
   REPORT filenames the original sweep used.

3. Merge retry rows back into the originals by `variant_id`:

   ```bash
   PYTHONPATH=. .venv/bin/python scripts/merge_retry_into_sweep.py \
     --run-dir benchmark/phase5/pilot/bedrock_sweep_<stamp>
   ```

   This writes `*.merged.jsonl` / `*.merged.json` next to the originals
   (which are left untouched) and prints the recomputed headline TSR /
   ASR. The merged TSR can be **lower** than the original when many
   rows turn from "error excluded from denominator" into "turn-cap
   counted as task_success=false" — that is the real number; the
   original was inflated by the parse-error exclusion.

## Known Caveats

- **AWS account scope.** The `global.` Claude 4.6 / 4.7 profiles must be
  enabled on the account. Check via
  `aws bedrock list-inference-profiles --region us-east-1`; if the profile
  is missing, the account owner has to request access in the Bedrock
  console.
- **Bedrock prompt caching.** The Bedrock client does not currently emit
  `cache_control` markers. `OpenAIJsonResult.usage.cached_input_tokens`
  reports `cache_read_input_tokens` when Anthropic supplies it but the
  client does not opt into caching itself.
- **Smoke before paying.** A direct one-call smoke covers auth + model
  reachability without spinning Docker:

  ```bash
  PYTHONPATH=. .venv/bin/python -c "
  from clawsocialarena.llm.bedrock_client import BedrockJsonClient
  c = BedrockJsonClient(region='us-east-1', max_tokens=64)
  print(c.create_json(model='global.anthropic.claude-sonnet-4-6',
                      system_prompt='Reply {\"ok\": true}.', payload={}).data)
  "
  ```
