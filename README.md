# ClawSocialArena

An audit-first Python runtime + benchmark for measuring auditability of LLM agents in persistent social networks. Companion to the design spec at [`docs/design.md`](docs/design.md) and the implementation plan at [`docs/plan.md`](docs/plan.md).

**Status**: Phases 1 through 6 infrastructure complete (149/149 tests, MVP demo end-to-end). Remaining work is data generation and experiment runs — see [§ Next phases](#next-phases).

---

## Install

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
source .venv/bin/activate
```

(Plain `pip install -e ".[dev]"` works too if you have Python 3.11+.)

## Verify

```bash
pytest -q                             # expect 149 passed
python -m scripts.run_mvp              # terminal_predicate_passed=True
python -m clawsocialarena.generator.cli --category CU --family scheduling --n 2 --seed 42 --out /tmp/gen_demo
python -m clawsocialarena.analysis --help
```

---

## What works today

| Component | Module | Notes |
|---|---|---|
| Core runtime | `clawsocialarena/{action_log,bus,runtime,agents,scenario,tasks,types,hashing}.py` | Hash-chained `ActionLog`, `AuditedMessageBus` / `RawMessageBus`, `AuditableAIAgent`, `ScenarioRunner`, scheduling terminal predicate |
| Audit substrate | `clawsocialarena/audit/` | `ShadowLog`, `PhaseTracker`, `PolicyRegistry`, `PolicyCatalog`, `AttributionGraphBuilder` (causal + proximity), `SEMStore` (stub), vendored `error_chains` |
| SAF scorers | `clawsocialarena/saf/` | 5 dimensions + `SAFScorer` geometric-mean orchestrator |
| Evaluation pipeline | `clawsocialarena/eval/` | `EvalRunner` 5-stage + `RunScorecard` JSON schema |
| 3-condition ablation | `bus/audited.py` + `bus/raw.py` | `baseline` uses `RawMessageBus` (no audit infra); `passive` logs + evaluates without blocking; `enforce` rewrites or blocks |
| External baselines | `clawsocialarena/baselines/` + `audit/policies/dlp.py` | Prompt-only L0-L4 ladder, rule-based DLP sanitizer, vanilla-AA post-hoc auditor |
| Scenario generator framework | `clawsocialarena/generator/` | `Template` protocol, attack injection (6 types, 2 families), mechanical GT assembly, CLI |
| Analysis pipeline | `clawsocialarena/analysis/` | Aggregator → long-format CSV, headline/model/rewrite tables (markdown + LaTeX), Wilcoxon / Kruskal-Wallis / Bonferroni, pre-registration reconciler |

### Design decisions captured per phase

- [`docs/reviews/README.md`](docs/reviews/README.md) — index
- [`docs/reviews/phase-1-summary.md`](docs/reviews/phase-1-summary.md), [`phase-2-summary.md`](docs/reviews/phase-2-summary.md), [`phase-3-summary.md`](docs/reviews/phase-3-summary.md)
- [`docs/reviews/HANDOFF-PHASE-4-ONWARDS.md`](docs/reviews/HANDOFF-PHASE-4-ONWARDS.md) — detailed resume guide
- Raw Codex reviews: `docs/reviews/phase-*-codex-raw.md`
- [`docs/preregistration.md`](docs/preregistration.md) — pre-committed hypotheses H1–H5

---

## Next phases

The remaining work needs external resources: LLM API access and compute budget. Each step below is self-contained, with acceptance criteria and the exact command(s) to run.

### Phase 4.2 — LLM-assisted scenario instantiation

**Goal**: replace the deterministic stub in `clawsocialarena/generator/instantiation.py` with an LLM-assisted layer that fills user profiles (names, domains, sensitive items) and scripted NPC content from AgentSocialBench's profile dataset.

**Requires**: one working LLM provider (Bedrock with Anthropic model ID, OpenAI, DeepSeek, or Qwen).

**Steps**:
1. Set up provider credentials (example for Bedrock):
   ```bash
   export AWS_PROFILE=...          # or AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
   export AWS_REGION=us-west-2
   # NOTE (v2): the in-process `clawsocialarena.agents.llm_client` module was
   # removed in Phase B of the v2 refactor. Provider wiring now lives in the
   # gateway_plugin; a refreshed Bedrock smoke snippet will land in Phase G
   # alongside the broader README rewrite.
   ```
2. Add a profile loader:
   ```python
   # clawsocialarena/generator/profiles.py
   # Reads ~/llm/mas/agent-socialn-privacy/prism/data/profiles/*.json
   # Returns a ProfileBank keyed by domain.
   ```
3. Extend `instantiate(template, ..., mode="llm", llm=...)` to:
   - Pull a seeded profile pair from `ProfileBank`.
   - Call LLM with a system prompt asking it to expand the template's scripted NPC lines in the profile's voice.
   - Cache completions to disk (prompt hash → response) so re-runs don't spend tokens.
4. Write tests that use `MockLLMClient` with canned completions to verify the pipeline without burning tokens.
5. Add `--instantiation-mode {deterministic, llm}` + `--llm-provider {bedrock, openai, deepseek, qwen}` + `--llm-model-id <ID>` flags to the generator CLI.

**Acceptance**: `python -m clawsocialarena.generator.cli --category CU --family scheduling --n 3 --seed 42 --instantiation-mode llm --llm-provider bedrock --llm-model-id anthropic.claude-sonnet-4-6-v1:0 --out /tmp/gen_llm` produces 3 scenarios with distinct, profile-conditioned content. Cached completions at `~/.cache/clawsocialarena/instantiation/`.

### Phase 4.5 — Remaining 13 category × task-family templates

**Goal**: add templates for the 13 (category, family) pairs beyond CU×Scheduling that the spec assigns. Per spec §4.2:

| Category | Families | File |
|---|---|---|
| CD | Aggregation, Decision | `templates/cd_aggregation.py`, `templates/cd_decision.py` |
| MC | Scheduling, Aggregation | `templates/mc_scheduling.py`, `templates/mc_aggregation.py` |
| CU | ~~Scheduling~~ (done), Transaction | `templates/cu_transaction.py` |
| MG | Decision, Aggregation | `templates/mg_decision.py`, `templates/mg_aggregation.py` |
| HS | Aggregation, Transaction | `templates/hs_aggregation.py`, `templates/hs_transaction.py` |
| CM | Transaction, Decision | `templates/cm_transaction.py`, `templates/cm_decision.py` |
| AM | Decision, Scheduling | `templates/am_decision.py`, `templates/am_scheduling.py` |

**Steps**:
1. One PR per 2–3 templates for easy review.
2. Each template implements `Template.build(seed, scenario_id) -> TemplateShape` with its own terminal predicate (some require new predicates under `clawsocialarena/tasks/`, e.g. `aggregation.py`, `transaction.py`, `decision.py`).
3. Register each in `clawsocialarena/generator/registry.py`.
4. Add per-template tests mirroring `test_template.py` / `test_gt_assembly.py`.
5. Update the registry's `list_registered()` output.

**Acceptance**: `python -m clawsocialarena.generator.cli --list-templates` shows 14 pairs. Each produces valid `Scenario` + `GTBundle` JSON via `ScenarioLoader`.

### Phase 4.7 — Generate the 70-scenario sample set

**Goal**: ~10 sample scenarios per (category, family) pair × 7 categories × 2 families = ~140 sample scenarios (deduped to 70 unique per spec §4.7). Smaller sanity-check set before the full 250.

**Steps**:
1. With templates from 4.5 and instantiation from 4.2 in place:
   ```bash
   mkdir -p fixtures/scenarios/gen
   for CAT in CD MC CU MG HS CM AM; do
     for FAM in scheduling aggregation transaction decision; do
       python -m clawsocialarena.generator.cli --category "$CAT" --family "$FAM" \
         --n 5 --seed 42 --instantiation-mode llm \
         --llm-provider bedrock --llm-model-id anthropic.claude-sonnet-4-6-v1:0 \
         --out fixtures/scenarios/gen
     done
   done
   ```
   (Skip unregistered pairs — CLI will error cleanly.)
2. Verify each scenario loads: `python -m clawsocialarena.scenario.validate fixtures/scenarios/gen`.
3. Commit the generated fixtures as a sanity baseline.

**Acceptance**: `ls fixtures/scenarios/gen | wc -l` ≥ 70. Every scenario loads via `ScenarioLoader`. Each runs to `terminal_predicate_passed=True` with `MockLLMClient`.

### Phase 5.1 — Full 250-scenario benchmark

**Goal**: produce the benchmark per spec §4.4. 210 main verifiable scenarios + 40 hard-verification (code review / document editing) stratum + 3 named disagreement vignettes.

**Steps**:
1. Add code-review and document-editing task families under `clawsocialarena/tasks/`: `code_review.py`, `doc_editing.py`. Each needs:
   - A planted-bug / schema-check terminal predicate for the deterministic component.
   - An LLM-judged rubric for the soft halo (attach to `RunScorecard.diagnostics`, NOT the headline).
2. Add matching templates (`templates/cu_code_review.py`, etc.) that plant bugs / required fields.
3. Generate the dataset:
   ```bash
   # Main set: 210 scenarios, distributed per §4.4
   python scripts/generate_main_250.py --out benchmark/scenarios/v1.0.0 --seed 1
   # Hard stratum: 40 scenarios
   python scripts/generate_hard_40.py --out benchmark/scenarios/v1.0.0 --seed 2
   ```
   (You'll write `scripts/generate_main_250.py` — wraps the generator CLI with the spec's stratification.)
4. Hand-author the 3 disagreement vignettes under `benchmark/scenarios/v1.0.0/vignettes/`:
   - `cu_inferential_leakage_v1/`
   - `hs_cross_delegation_attr_v1/`
   - `mg_partial_log_recovery_v1/`
   Write assertion tests that confirm `VanillaAAEvalRunner` reports them as compliant AND `EvalRunner` catches the violation on the targeted SAF dimension.
5. Write `benchmark/manifest.json` listing all 250 IDs with metadata `(category, task_family, attacker, expected_phase_count)`. Tests assert manifest is consistent with the files on disk.
6. 40-scenario annotator validation sample: pick 40 IDs (seeded), emit `benchmark/validation_ids.json` + a markdown workbook template. Annotator work is external human labor — do NOT simulate with LLMs.

**Acceptance**: 250 scenario directories under `benchmark/scenarios/v1.0.0/` with valid `Scenario` + `GTBundle` JSON; manifest consistent; 3 vignette assertion tests pass; validation workbook exists.

### Phase 6.1 — Batch runner + real experiment runs

**Goal**: execute ~5,400 runs per the pre-registered compute budget (spec §5.5):

| Bucket | Scenarios × conditions × models | Runs |
|---|---|---|
| Main table | 250 × 1 seed × 1 privacy (L0) × 3 conditions × 4 models | 3,000 |
| Privacy-ladder ablation | 50 × 2 privacy (L0, L2) × 3 conditions × 4 models | 1,200 |
| External-baseline comparison | 40 × 3 baselines × 4 models | 480 |
| Seed-variance spot-check | 20 × 3 seeds × 3 conditions × 4 models | 720 |
| **Total** | | **~5,400** |

**Requires**:
- API keys for **4 providers** (Claude via Bedrock/boto3; GPT-5-mini via OpenAI; DeepSeek; Qwen).
- Cost budget: **$3K–$8K** depending on provider mix and prompt caching.
- Wall-clock: **7–10 days** with 4× provider parallelism.

**Steps**:
1. Write `scripts/run_grid.py`:
   ```python
   # Reads a YAML config of (scenario_id, condition, model) triples,
   # constructs ScenarioRunner per row, persists per-run RunScorecard JSON
   # under results/v1.0.0/<model>/<condition>/<scenario_id>/run_scorecard.json,
   # populating RunScorecard.meta = {condition, model, seed, privacy_level}.
   # Tracks cumulative token/cost via LLMCompletion.usage and dumps to results/v1.0.0/cost.csv.
   # Resumable: skips rows whose scorecard already exists.
   ```
2. Smoke test on 5 scenarios × 3 conditions × 1 model (Mock) to confirm wiring.
3. Pilot ~30 real-LLM runs on Bedrock to sanity-check cost/wall-clock estimates before committing the full budget. **Stop and review actual per-run cost vs. estimate before scaling.**
4. Run main table:
   ```bash
   python scripts/run_grid.py --config configs/main_table.yaml --out results/v1.0.0 --parallel 4
   ```
5. Run privacy-ladder ablation, external-baseline comparison, and seed-variance spot-check similarly.
6. Commit all `run_scorecard.json` files (compressed tarball) under `results/v1.0.0/`.

**Acceptance**: ~5,400 scorecards exist on disk; `cost.csv` shows cumulative budget; no scorecard has `chain_integrity_primary == False`.

### Phase 6.3 — Figures

**Goal**: generate the paper's figure PDFs. Requires real scorecard data from Phase 6.1.

**Steps**:
1. Write `clawsocialarena/analysis/figures.py`:
   - `ablation_figure(df)` — ΔTSR / ΔPrivacy / ΔSecurity baseline→passive→enforce, broken down by attack family (spec §5.6 item 3).
   - `rewrite_quality_figure(df)` — TSR(enforce) − TSR(passive) per category.
   - `disagreement_vignettes_figure(df)` — three-panel case studies (§5.6 item 5).
   - `sensitivity_figure(df)` — binary pass-rate vs threshold ±0.05 (§5.6 item 7).
2. Each function takes the long-format CSV from the aggregator, returns a matplotlib `Figure`, and writes a PDF under `paper/figures/`.
3. Wire into `clawsocialarena.analysis.__main__` as a new `figures` subcommand.
4. Sensitivity analysis: loop thresholds, recompute binary passes from the continuous scores, plot pass-rate deltas.

**Acceptance**: `python -m clawsocialarena.analysis figures --csv results/v1.0.0/long.csv --out paper/figures/` produces 4 PDF files.

### Phase 6 closing — pre-registration reconciliation + reproducibility bundle

**Steps**:
1. Extend `clawsocialarena/analysis/prereg_check.py` with verdicts for H1 (SAF-weakest-dim identification), H3 (TSR cost bounds), H5 (mid-tier enforce vs. frontier baseline composite).
2. Run the reconciler:
   ```bash
   python -m clawsocialarena.analysis prereg --csv results/v1.0.0/long.csv --out results/v1.0.0/prereg_reconciliation.md
   ```
3. Write `scripts/make_repro_bundle.py` — single tarball containing:
   - `benchmark/scenarios/v1.0.0/` (250 scenarios)
   - `results/v1.0.0/` (scorecards + CSVs + figures)
   - `pyproject.toml` + `uv.lock` for dependency pinning
   - `docs/preregistration.md`, `docs/design.md`
   - One-command replay: `bash replay.sh`.
4. Update top-level `README.md` with a "How to reproduce" section pointing at the bundle.

**Acceptance**: `python scripts/make_repro_bundle.py --out /tmp/clawsocialarena-repro-v1.0.0.tar.gz` produces a ≤ 2 GB tarball that unpacks and replays analysis (not runtime — full replay would re-spend the $3–8K budget).

---

## Architecture at a glance

```
ScenarioRunner
 ├── agents: {agent_id → AuditableAIAgent}
 ├── bus:
 │     ├── BASELINE  → RawMessageBus (no hash chain, no hooks, no shadow)
 │     └── PASSIVE / ENFORCE → AuditedMessageBus
 │           ├── action_log  (SQLite, hash-chained, WAL + BEGIN IMMEDIATE)
 │           ├── shadow_log  (independent copy; Recoverability scores against it)
 │           ├── phase_tracker  (social-phase state machine)
 │           └── hooks: list[PolicyHook]  (message-kind + tool-kind)
 └── phase_tracker (passive/enforce only)

Evaluation (pure function of logs + GT):
 ActionLog + ShadowLog + GTBundle
   → EvalRunner
       ├── build PolicyRegistry from gt.policies via PolicyCatalog
       ├── build produced AttributionGraph (causal via source_action_ids, fallback to proximity)
       ├── SAFScorer.score(5 dims)  →  weighted geometric mean
       └── RunScorecard JSON (SAF + task + privacy + security + diagnostics + meta)

Analysis (offline, pure):
 results/*/run_scorecard.json
   → aggregator → long-format CSV
       ├── tables (headline / model / rewrite; markdown + LaTeX)
       ├── stats (Wilcoxon + Kruskal-Wallis + Bonferroni)
       └── prereg_check (H1–H5 verdicts)
```

## Repo conventions

- **Python 3.11+** required (uses `StrEnum`, structural pattern matching).
- **Tests**: `pytest tests/ -v`. `pytest-asyncio` for coroutines.
- **Formatting**: `ruff`. `mypy` available via `.[dev]`.
- **Worktrees**: use `worktree/<name>/`, never `../<repo>-<name>/`. See `.gitignore`.
- **Commits**: conventional (`feat(arena):`, `fix(arena):`, `chore(arena):`, `docs(arena):`, `test(arena):`).
- **Design + plan + reviews** live under `docs/`, not the workspace parent.

## License

Apache-2.0.
