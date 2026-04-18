# ClawSocialArena v2

*An Auditable Runtime System for Benchmarking Multi-Party Collaboration, Security, and Privacy in Human-Centered Agentic Social Networks.*

ClawSocialArena v2 is a runtime-backed benchmark in which auditability is both a measurable property of a deployed multi-party social network and a toggleable intervention. A scenario is one `docker-compose.yml` that brings up N real OpenClaw personal-AI-assistant containers plus a central ClawSocialArena audit gateway. The gateway is the sole cross-container hop; it maintains per-agent hash-chained action logs, a Multi-Party Social World Model (MSWM), an online inference-attribution DAG, a social-phase tracker, and three classes of policy hooks. Evaluation is an offline pure function of `(action_log, shadow_log, cassette, GT bundle)`. Companion to the design spec at [`docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md`](docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md) and the implementation plan at [`docs/superpowers/plans/2026-04-17-clawsocialarena-v2.md`](docs/superpowers/plans/2026-04-17-clawsocialarena-v2.md).

## Status

| Phase | Tag | State | Tests added |
|---|---|---|---|
| A | `phase-A-complete` | done | gateway + plugin + compose E2E |
| A.5 | `phase-A5-complete` | done (spec fix) | no new tests |
| B | `phase-B-complete` | done | v1 surfaces removed |
| C | `phase-C-complete` | done | MSWM + attribution |
| C.5 | `phase-C5-complete` | done (code fix) | provenance tuples |
| D | `phase-D-complete` | done | scenario model v2 + emitters |
| D.5 | `phase-D5-complete` | done (code fix) | validator v2 runtime contract |
| E | untagged | deferred (Phase E) | 1 of 16 templates shipped |
| F | `phase-F-complete` | done | MSWM-aware scorers + cumulative |
| F.5 | `phase-F5-complete` | done (code fix) | eval threading + episode-graph |
| G (infra) | `phase-G-infrastructure-complete` | done | grid config + runner + cost |
| G5-G8 | untagged | deferred (Phase G5-G7) | needs credentials + budget |
| H (infra) | `phase-H-infrastructure-complete` | done | aggregator + tables + figures + stats + prereg + repro bundle |
| H8 | untagged | deferred (Phase H8) | needs E + G outputs |

Final test baseline: **470 Python passed + 2 skipped**, **29 TypeScript passed**, `mypy` and `ruff` clean.

**Autonomous execution stopped at `phase-H-infrastructure-complete`.** Remaining work (Phase E benchmark content, Phase G5-G7 live runs, Phase H8 `v1.0.0` tag) needs human-in-the-loop resources: LLM API credentials, a $4K-$10K compute budget, a Docker host, and three annotators. See the resume sections below.

---

## Install

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
source .venv/bin/activate
```

Plain `pip install -e ".[dev]"` works too if you have Python 3.11+.

For the TypeScript OpenClaw channel plugin:

```bash
npx pnpm -C gateway_plugin install
```

Docker is **not** required for the infrastructure test suite. It **is** required for Phase G5-G7 live runs (the `ComposeRunner` brings up one OpenClaw container per agent alongside the gateway).

## Verify

```bash
pytest -q                                                              # 470 passed + 2 skipped
npx pnpm -C gateway_plugin test                                        # 29 passed
python -m clawsocialarena.generator.cli --list-templates               # 1 template (cu_scheduling)
python -m clawsocialarena.generator.cli \
    --category CU --family scheduling --n 1 --seed 42 --out /tmp/gen_test   # valid bundle under /tmp/gen_test
```

The generator CLI emits `scenario.json`, `scenario.gt.json`, `docker-compose.yml`, `personas/*.system.md`, `personas/*.tools.json`, and `mcp/*.json` under `/tmp/gen_test/<scenario_id>/`.

---

## What's in the box

| Path | Contents |
|---|---|
| `clawsocialarena/gateway/` | audit gateway (HTTP server, session, MSWM wiring, MCP host, cassette recorder, compose runner, replay driver) |
| `clawsocialarena/audit/` | action log, phase tracker, shadow log, MSWM, attribution builder, policy registry / catalog, DLP and MSWM-aware policies, error-chain classifier |
| `clawsocialarena/saf/` | five SAF scorers (recoverability, policy-checkability, attribution-F1, evidence-integrity, phase-scoped) and the overall geometric-mean orchestrator |
| `clawsocialarena/eval/` | `EvalRunner` five-stage, scorecard v2 schema, cumulative module, `EpisodeGraphEvalRunner`, leak detector |
| `clawsocialarena/scenario/` | models v2 (MCP + persona manifests), loader v2, validator v2 |
| `clawsocialarena/generator/` | template protocol, deterministic instantiation (LLM stub), attack injection, GT assembly, compose / persona / MCP emitters, CLI |
| `clawsocialarena/baselines/` | prompt-ladder L0-L4, vanilla-AA post-hoc auditor, rule-based DLP sanitizer |
| `clawsocialarena/analysis/` | aggregator, headline / model / rewrite tables, four paper figures, Wilcoxon / Kruskal-Wallis / Bonferroni / sensitivity, pre-registration reconciler |
| `clawsocialarena/experiments/` | grid config schema, USD-per-million rate table |
| `clawsocialarena/mcp_tools/` | scenario tool stubs (currently `noop`) |
| `gateway_plugin/` | TypeScript OpenClaw channel plugin (`src/index.ts`, `src/channel.ts`, `src/gateway-client.ts`) |
| `docker/` | `gateway.Dockerfile`, `openclaw-with-plugin.Dockerfile`, `compose-templates/minimal.yml`, `agent-entrypoint.sh` |
| `scripts/` | `run_mvp.py`, `run_grid.py`, `make_repro_bundle.py`, `build_openclaw_image.sh` |
| `configs/` | `main_table.yaml`, `ablations.yaml` |

---

## How to pick up Phase E (generate the 150-scenario benchmark)

Goal: produce 150 scenario bundles under `benchmark/scenarios/v1.0.0/` — 100 main verifiable + 25 hard stratum (12 code-review + 13 doc-editing) + 20 episode-graph scenarios (5 graphs × 4 linked episodes) + 5 named disagreement vignettes (see spec §3.1 and §4.1).

**Requirements.**

- LLM API credentials for at least one provider: Bedrock (Anthropic), OpenAI, DeepSeek, or Qwen.
- A profile dataset. The spec draws profiles from AgentSocialBench; the relevant files live under the sibling repository `../agent-socialn-privacy/prism/data/profiles/`. Copy or reference paths as needed.
- The generator CLI, already shipped: `python -m clawsocialarena.generator.cli`.

**Steps.**

1. **Add the 13 missing (category, family) templates** (plan tasks E1 through E14, minus E5 which is already shipped as `cu_scheduling`). Each lives at `clawsocialarena/generator/templates/<template_id>.py`. Start by copying `cu_scheduling.py` as a skeleton and edit the `build(seed, scenario_id)` method. Register each new template in `clawsocialarena/generator/registry.py`. The 13 pairs are:
    `cd_aggregation`, `cd_decision`, `mc_scheduling`, `mc_decision`, `cu_coalition`, `mg_aggregation`, `mg_coalition`, `hs_aggregation`, `hs_coalition`, `cm_aggregation`, `cm_coalition`, `am_scheduling`, `am_decision`.
2. **Add the 2 hard-stratum templates**: `clawsocialarena/generator/templates/hard_code_review.py` and `hard_doc_editing.py` (plan task E15). These carry planted-bug and planted-field lists in the GT bundle for the deterministic halo; the LLM-judged halo attaches later at analysis time and never enters SAF.
3. **Hand-author the 5 disagreement vignettes** under `benchmark/scenarios/v1.0.0/vignettes/` (plan task E16). Each is a full scenario bundle constructed so vanilla-AA scores it compliant and SAF catches the targeted SAF-dimension violation. Spec §3.1 names three: `inferential_leakage_v1`, `cross_delegation_attr_v1`, `partial_log_recovery_v1`. Pick two more per spec §4.1 (suggested: `consensus_sabotage_v1` and `mswm_privileged_delegation_v1`). Write assertion tests under `tests/vignettes/` that confirm `VanillaAAEvalRunner` passes each vignette while `EvalRunner` fails on the right dimension.
4. **Implement LLM-assisted instantiation.** The current stub at `clawsocialarena/generator/instantiation.py` falls back to deterministic mode when `--instantiation-mode llm` is set. Fill the `llm` branch with a Bedrock or OpenAI client call that expands each template's scripted NPC lines in the voice of a seeded profile pair. Cache completions by prompt hash to `~/.cache/clawsocialarena/instantiation/` so re-runs do not spend tokens. Write tests using a `MockLLMClient` with canned completions.
5. **Run batch generation.** Write `scripts/generate_main_150.py` (plan task E18) as a thin wrapper around `clawsocialarena.generator.cli` that honors the per-category stratification from spec §4.4. Run:
    ```bash
    python scripts/generate_main_150.py \
        --out benchmark/scenarios/v1.0.0 \
        --seed 1 \
        --instantiation-mode llm \
        --llm-provider bedrock \
        --llm-model-id anthropic.claude-sonnet-4-6-v1:0
    ```
6. **Run the 3-annotator validation on 40 scenarios.** Write `scripts/pick_validation_sample.py` (does not yet exist) that seeds a 40-scenario id list into `benchmark/validation_ids.json` and emits a markdown workbook template for human annotators. Annotator work is external human labor; target Cohen's κ ≥ 0.80 per spec §4.9.

**Acceptance.** 150 scenario directories under `benchmark/scenarios/v1.0.0/`; `python -m clawsocialarena.scenario.validate benchmark/scenarios/v1.0.0` passes every bundle; the five vignette assertion tests pass; `benchmark/validation_ids.json` plus the annotator workbook exist.

---

## How to pick up Phase G5-G7 (run the 4,440 experiments)

Goal: produce ~4,440 `run_scorecard.json` files covering the spec §5.4 budget (main table live + replay + privacy-ladder ablation + external-baseline comparison + seed-variance spot-check + episode-graph stratum).

**Requirements.**

- LLM API credentials for 4 providers: `AWS_PROFILE` (or `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`) for Bedrock; `OPENAI_API_KEY`; `DEEPSEEK_API_KEY`; `DASHSCOPE_API_KEY` for Qwen.
- Docker installed and running. Verify with `docker info`.
- Cost budget: $4K-$10K depending on provider mix and prompt caching.
- Wall-clock: 10-14 days with 4× provider parallelism plus container-orchestration overhead.

**Steps.**

1. **Configure credentials** (one-time):
    ```bash
    export AWS_PROFILE=<profile> AWS_REGION=us-west-2
    export OPENAI_API_KEY=...
    export DEEPSEEK_API_KEY=...
    export DASHSCOPE_API_KEY=...
    aws sts get-caller-identity   # confirm Bedrock credentials
    ```
2. **Build the two Docker images.**
    ```bash
    bash scripts/build_openclaw_image.sh clawsocialarena/openclaw-with-plugin:v1
    docker build -f docker/gateway.Dockerfile -t clawsocialarena/gateway:v1 .
    ```
3. **Pilot smoke (30 live Bedrock runs; plan task G5).** Author `configs/pilot_30.yaml` with 30 live rows. Run:
    ```bash
    python scripts/run_grid.py \
        --config configs/pilot_30.yaml \
        --out results/pilot-2026-MM \
        --parallel 2
    ```
    Review `results/pilot-2026-MM/cost.csv` against the spec §5.4 envelope. Only proceed to the full runs if the extrapolated cost matches.
4. **Full main table (plan task G6).**
    ```bash
    python scripts/run_grid.py \
        --config configs/main_table.yaml \
        --out results/v1.0.0 \
        --parallel 4
    ```
    Expects 1,800 runs (150 scenarios × 3 conditions × 4 models, split live / replay per spec §2.11). The runner is resumable; rerunning skips rows whose scorecard already exists with `status != "pending"`.
5. **Ablations (plan task G7a).**
    ```bash
    python scripts/run_grid.py --config configs/ablations.yaml --out results/v1.0.0
    ```
6. **Seed-variance spot-check (plan task G7b).** Write `configs/seeds.yaml` and run it the same way. Spec §5.4 gives 720 runs.
7. **Episode-graph stratum (plan task G7c).** Write `configs/episode_graphs.yaml` and run it. Spec §5.4 gives 240 runs.
8. **Verify.**
    ```bash
    find results/v1.0.0 -name 'run_scorecard.json' | wc -l   # ~4,440
    python scripts/audit_scorecards.py --out results/v1.0.0  # no chain_integrity_primary == False
    ```
    (`scripts/audit_scorecards.py` is a small helper to write before the final Phase G tag.)

**Acceptance.** ~4,440 scorecards under `results/v1.0.0/`; `results/v1.0.0/cost.csv` within the $4K-$10K envelope; no scorecard reports a broken hash chain.

---

## How to pick up Phase H8 (analysis + v1.0.0 tag)

Goal: run the full analysis pipeline against real scorecard data, assemble the reproducibility bundle, and tag `v1.0.0`. Every analysis subcommand is already implemented and tested against synthetic scorecards; Phase H8 runs them against the real `results/v1.0.0/` tree.

**Steps.**

```bash
python -m clawsocialarena.analysis aggregate --scorecard-dir results/v1.0.0 --out results/v1.0.0/long.csv
python -m clawsocialarena.analysis tables --csv results/v1.0.0/long.csv --out paper/tables/
python -m clawsocialarena.analysis figures --csv results/v1.0.0/long.csv --out paper/figures/
python -m clawsocialarena.analysis prereg --csv results/v1.0.0/long.csv --out results/v1.0.0/prereg_reconciliation.md
python -m clawsocialarena.analysis sensitivity --csv results/v1.0.0/long.csv --out paper/figures/sensitivity.pdf
python scripts/make_repro_bundle.py --version 1.0.0 --out /tmp/clawsocialarena-repro-v1.0.0.tar.gz
git tag v1.0.0
```

`scripts/make_repro_bundle.py` packs benchmark scenarios, results, the lockfile, the design spec, the pre-registration, and a one-command `replay.sh` driver. Target size ≤ 2 GB.

---

## Key docs

- **Design spec:** [`docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md`](docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md)
- **Implementation plan:** [`docs/superpowers/plans/2026-04-17-clawsocialarena-v2.md`](docs/superpowers/plans/2026-04-17-clawsocialarena-v2.md)
- **Pre-registered hypotheses:** [`docs/preregistration.md`](docs/preregistration.md) (carries over from v1; review before live runs)
- **Phase G resume note:** [`docs/superpowers/plans/phase-G-deferred.md`](docs/superpowers/plans/phase-G-deferred.md)
- **Phase H resume note:** [`docs/superpowers/plans/phase-H-deferred.md`](docs/superpowers/plans/phase-H-deferred.md)
- **Phase retrospectives:** [`docs/reviews/`](docs/reviews/) carries v1 phase summaries and Codex reviews; v2 per-phase context lives in the commit log — run `git log --grep="phase-"` for the commit-level timeline.

---

## License

Apache-2.0. See `pyproject.toml`.
