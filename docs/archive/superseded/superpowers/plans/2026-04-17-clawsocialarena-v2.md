# Superseded Historical Document

This file is archived for history. It is not the current execution plan.

Current entry point: `docs/project_status.md`

Current plan index: `docs/DOCUMENTATION_INDEX.md`

The active benchmark construction plans are the May 2026 plans under `docs/superpowers/plans/`.

---

# ClawSocialArena v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status as of 2026-04-18

Autonomous execution paused after `phase-H-infrastructure-complete`. Remaining work (Phase E benchmark content, Phase G5-G7 live runs, Phase H8 `v1.0.0` tag) needs human-in-the-loop resources: LLM API credentials, compute budget, annotators. See `docs/superpowers/plans/phase-G-deferred.md` and `docs/superpowers/plans/phase-H-deferred.md` for the resume instructions.

Test baseline at pause: Python 470 passed + 2 skipped; TypeScript 29 passed; mypy + ruff clean.

## Planning revision as of 2026-04-24

Before Phase E or any main experimental run, add **Phase I: governance-aware audit revision**. This phase expands SAF from five to six dimensions by adding Identity-Governance Auditability, and expands the attacker taxonomy from three axes to four: Collaboration, Security, Privacy, and Governance. The code currently implements the earlier five-dimension SAF; Phase I is the new bridge between the shipped infrastructure and the revised paper scope.

## Planning revision as of 2026-05-05

Phase E now treats the generated 550-variant tree as a pre-calibration scaffold, not the final benchmark. The active construction plan adds task schema v0, deterministic source-pattern metadata adapted from tau2-bench and WildClawBench motifs, designed difficulty tiers, strict task-success contracts, and a calibration report before paid scale-out. The next generation target is a 680-variant balanced difficulty pilot: 630 main matched variants, 25 hard variants, 20 episode-graph variants, and 5 audit challenge cases. If the pilot validates the designed difficulty rubric against observed simulation outcomes, the recommended release grid expands to 1100 total variants with 1050 main matched variants.

### Phase rollup

| Phase | Tag | Status | Notes |
|---|---|---|---|
| A | `phase-A-complete` | done | Gateway + Session + cassette + MCP host + plugin + Docker + minimal compose + E2E smoke (tasks A1-A15). |
| A.5 | `phase-A5-complete` | done (fix) | Spec §2.9 baseline row reconciled with code: baseline keeps no records. |
| B | `phase-B-complete` | done | v1 bus / agents / runtime / sem deleted; SEM -> MSWM rename complete (tasks B1-B8). |
| C | `phase-C-complete` | done | MSWM + attribution DAG + labels (tasks C1-C10). |
| C.5 | `phase-C5-complete` | done (fix) | MSWM rewrite-reconcile ordering; `self_knowledge` carries `(item_id, action_id)` provenance. |
| D | `phase-D-complete` | done | Scenario model v2, compose / persona / MCP emitters, GT v2, CLI, loader, validator (tasks D1-D10). |
| D.5 | `phase-D5-complete` | done (fix) | Absolute compose build paths; per-agent `allowed_tools`; validator enforces runtime contract; `McpToolSpec.schema` marked advisory. |
| E | not tagged | deferred | Active main only registers `cu_scheduling`; the Phase E worktrees already contain the broader template set. Needs template integration, resource-aware scenario construction, task schema v0, source-pattern adaptation, designed difficulty calibration, 2 hard-stratum templates, 5 audit challenge cases, 5 episode graphs, and the balanced difficulty materializer. Requires LLM-assisted instantiation plus hand-authoring plus 3-annotator validation. |
| F | `phase-F-complete` | done | Psi / tau scorers consume MSWM, cumulative module, scorecard v2, EvalRunner v2, replay driver, leak detector, baselines updated (tasks F1-F10). |
| F.5 | `phase-F5-complete` | done (fix) | Fix 1: MSWM inferential policies wired through EvalRunner into SAFScorer. Fix 2: attribution preserves pre-rewrite causal item under enforce. Fix 3: `EpisodeGraphEvalRunner` + cumulative adapter added. |
| G | `phase-G-infrastructure-complete` | partial | Infrastructure tasks (G1-G4) done. Tasks G5 (pilot), G6 (full main table), G7 (ablations + seed + episode), G8 (tag) deferred; see `phase-G-deferred.md`. |
| H | `phase-H-infrastructure-complete` | partial | Analysis infrastructure tasks (H1-H7) done; tests run against synthetic scorecards. Task H8 (`v1.0.0` tag + CHANGELOG) deferred; see `phase-H-deferred.md`. |
| I | not tagged | new | Governance-aware audit revision. Adds governance manifest, per-action governance object, sixth SAF scorer, governance attack taxonomy, governance audit challenge cases, updated analysis and preregistration. Must run before Phase E/G live work. |
| E0 | not tagged | new | Template worktree integration. Imports the existing Phase E templates from `worktree/phase-I-governance`, reconciles task-family taxonomy, and adapts them to the current governance / MSWM schema before resource fixtures are added. |
| I.5 | not tagged | new | Resource-aware scenario construction. Adds per-user filesystem and personal database fixtures, resource manifests, gateway-hosted `fs.*` / `db.*` MCP tools, resource attack cases, and validator / scoring hooks. Must run before final Phase E regeneration. |

### Fix phases in one line each

- **A.5 (Spec update).** Spec §2.9 originally described baseline as a "minimal transport log"; code leaves the action log off under baseline. Took the spec-edit path: `baseline` now reads `no records`.
- **C.5 (MSWM provenance).** `MSWM.self_knowledge` was a `dict[agent_id, set[item_id]]` which lost the introducing action; changed to `dict[agent_id, set[(item_id, action_id)]]` so Phase F attribution can trace self-known items.
- **D.5 (Runtime contract).** Compose emitter now uses absolute `build.context`; `agent-entrypoint.sh` waits for gateway health; per-agent `allowed_tools` flow into persona manifests; validator checks services, env vars, personas, MCP manifests, and allowed-tools coverage.
- **F.5 (Eval threading + episode graphs).** MSWM inferential policies now reach the offline scorers via `EvalRunner`; attribution keeps the pre-rewrite causal item under enforce; `EpisodeGraphEvalRunner` drives per-episode eval and feeds the cumulative module so episode-graph fixtures produce usable trajectories end-to-end.

### Resume pointers

- **Phase I:** New section in this plan. Complete before Phase E so generated scenarios include governance manifests and attacks from the start.
- **Phase E0:** New template-integration phase. Complete before Phase I.5 so resource fixtures are added to imported templates rather than to a one-template main checkout.
- **Phase I.5:** New resource-aware construction phase. Complete before Phase E final generation so scenario IDs, GT, compose mounts, MCP manifests, and final-state checks are generated once.
- **Phase E:** README top-level "How to pick up Phase E" section (worktree root) walks through LLM-assisted instantiation, template copy pattern, audit challenge authoring, batch generation, and annotator validation.
- **Phase G5-G7:** `docs/superpowers/plans/phase-G-deferred.md` is the canonical resume note (credentials + Docker + materialised grids + resumable runner).
- **Phase H8:** `docs/superpowers/plans/phase-H-deferred.md` is the resume note (analysis one-liners + repro bundle + tag).

---

**Goal:** Refactor ClawSocialArena from the single-process Python runtime (v1) to an audit-first runtime around real OpenClaw containers in Docker Compose, with MSWM as the runtime centerpiece and an AgentSocialBench-extension benchmark spanning collaboration, security, privacy, and governance. The 550-variant tree is now a pre-calibration scaffold. The active Phase E target is the 680-variant balanced difficulty pilot, followed by a possible 1100-variant release grid if calibration supports the larger run.

**Architecture:** A scenario is a `docker-compose.yml` bringing up N OpenClaw containers + one ClawSocialArena audit gateway. The gateway is the sole cross-container hop: it hosts the action log, MSWM, policy hooks, phase tracker, MCP tool servers, resource fixtures, and cassette recorder. Each OpenClaw container preloads a ClawSocialArena TypeScript channel plugin that routes its outbound traffic through the gateway. Evaluation is an offline pure function of `(action_log, shadow_log, cassette, GT bundle, final_state)`.

**Tech Stack:** Python 3.11+ (gateway, evaluation, generator, analysis, tests), TypeScript (OpenClaw channel plugin, targeting `openclaw/plugin-sdk/channel-contract`), Docker + Docker Compose (orchestration), SQLite WAL (action log + shadow log), HTTP + JSON between agent containers and gateway, MCP via `mcporter`, `pytest` + `pytest-asyncio` + `docker-compose` Python bindings for E2E tests, `ruff` + `mypy`.

**Source spec:** `docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md`.

**Migration reference:** `docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md` Appendix A lists which v1 modules survive, which get rewritten, and which are new.

---

## Phase overview

| Phase | Deliverable | Tasks | Gated by |
|---|---|---|---|
| A | Gateway skeleton + channel plugin + minimal compose E2E | 15 | nothing |
| B | Migrate surviving v1 modules into gateway; delete obsolete bus/agent; SEM -> MSWM rename | 8 | A |
| C | MSWM online state machine and attribution walker | 10 | B |
| D | Scenario generator v2 (compose + personas + MCP + v2 GT bundle) | 10 | C |
| I | Governance-aware audit revision: sixth SAF dimension + fourth attack axis | 6 | D, F, H-infra |
| E0 | Template worktree integration and task-family reconciliation | 1 | I |
| I.5 | Resource-aware scenario construction: personal files, personal DB, resource MCP tools | 5 | I, E0 |
| E | Benchmark content: 100 main + 25 hard + 20 episode-graph + 5 audit challenge cases | 19 | D, I, E0, I.5 |
| F | Evaluation pipeline v2 (MSWM-aware scorers + cumulative metrics + cassette) | 10 | C, E |
| G | Batch runner + cassette replay + cost tracking | 8 | F |
| H | Analysis, figures, pre-registration reconciliation | 8 | G |
| **Total** | | **100** | |

Each phase ends with a green test run and a tagged commit (e.g., `phase-A-complete`). Phase boundaries are safe points to pause, review, or hand off to a fresh subagent.

---

## Repo layout after v2

```
clawsocialarena/
├── gateway/                        # NEW — the audit gateway (Python)
│   ├── __init__.py
│   ├── server.py                   # aiohttp HTTP server
│   ├── routes.py                   # /send /recv /tool_call /tool_observation /memory_write /llm_call
│   ├── session.py                  # per-scenario Session object holding action_log, MSWM, hooks, phase, shadow, cassette
│   ├── mcp_host.py                 # in-process MCP server multiplexer
│   ├── compose_runner.py           # drives docker-compose up/down per scenario
│   └── cassette.py                 # CassetteRecorder
├── gateway_plugin/                 # NEW — TypeScript OpenClaw plugin
│   ├── package.json
│   ├── src/
│   │   ├── index.ts                # plugin entry
│   │   ├── channel.ts              # ChannelContract implementation
│   │   └── gateway-client.ts       # HTTP client to the Python gateway
│   └── tests/
├── action_log.py                   # SURVIVES v1 — gateway-internal
├── hashing.py                      # SURVIVES v1
├── types.py                        # SURVIVES v1 — add MSWM, GatewayState types
├── audit/
│   ├── shadow_log.py               # SURVIVES v1
│   ├── phase_tracker.py            # SURVIVES v1
│   ├── mswm.py                     # NEW — per-agent peer beliefs (replaces sem.py)
│   ├── error_chains.py             # SURVIVES v1
│   ├── policies/
│   │   ├── registry.py             # SURVIVES v1
│   │   ├── catalog.py              # SURVIVES v1
│   │   ├── dlp.py                  # SURVIVES v1
│   │   ├── mswm_aware.py           # NEW — the joint-decidability hook
│   │   └── governance.py           # Phase I — owner / identity / scope / mandate hook
│   └── attribution.py              # rewritten — MSWM-aware graph builder
├── mcp_tools/                      # NEW — scenario-specific MCP servers (Python)
│   ├── calendar.py
│   ├── ledger.py
│   ├── runbook.py
│   ├── pr_review.py
│   ├── shared_doc.py
│   └── delegate.py
├── saf/                            # SURVIVES v1 (small rename)
│   ├── recoverability.py
│   ├── policy_checkability.py      # updated to consume MSWM
│   ├── attribution_f1.py           # updated to consume MSWM-built DAG
│   ├── evidence_integrity.py
│   ├── phase_scoped.py
│   ├── identity_governance.py      # Phase I — owner / identity / scope / mandate auditability
│   └── scorer.py
├── eval/                           # SURVIVES v1 mostly
│   ├── runner.py
│   ├── scorecard.py
│   └── cumulative.py               # NEW — Social Recall/Precision trajectory, TLR(t), CPR(t)
├── scenario/                       # SURVIVES v1
│   ├── loader.py                   # updated to load compose + personas + mcp + governance
│   ├── models.py                   # updated to hold mcp_tool_manifest + persona_manifest + governance_manifest
│   └── validate.py                 # updated
├── generator/                      # extends v1
│   ├── cli.py
│   ├── template.py
│   ├── instantiation.py
│   ├── attack_injection.py
│   ├── gt_assembly.py              # updated for v2 GT bundle
│   ├── compose_emitter.py          # NEW — emits docker-compose.yml
│   ├── persona_emitter.py          # NEW — emits personas/*.system.md + *.tools.json
│   ├── mcp_emitter.py              # NEW — emits mcp/*.json manifests
│   ├── governance_emitter.py       # Phase I — emits governance/manifest.json
│   ├── registry.py                 # extended with new (cat, family) pairs
│   └── templates/
│       ├── cd_consensus.py         # NEW
│       ├── cd_inference.py         # NEW
│       ├── mc_scheduling.py        # NEW
│       ├── mc_inference.py         # NEW
│       ├── cu_scheduling.py        # replaces v1 template (task family renamed)
│       ├── cu_coalition.py         # NEW
│       ├── mg_consensus.py         # NEW
│       ├── mg_coalition.py         # NEW
│       ├── hs_consensus.py         # NEW
│       ├── hs_coalition.py         # NEW
│       ├── cm_consensus.py         # NEW
│       ├── cm_coalition.py         # NEW
│       ├── am_scheduling.py        # NEW
│       ├── am_inference.py         # NEW
│       ├── hard_code_review.py    # NEW
│       └── hard_doc_editing.py     # NEW
├── tasks/                          # verifiable terminal predicates
│   ├── scheduling.py               # SURVIVES v1
│   ├── consensus.py                # NEW
│   ├── coalition.py                # NEW
│   └── inference.py                # NEW
├── analysis/                       # SURVIVES v1, extended
│   ├── aggregator.py
│   ├── tables.py
│   ├── stats.py
│   ├── prereg_check.py
│   └── figures.py                  # NEW — 4 paper figures
├── baselines/                      # SURVIVES v1 mostly
│   ├── prompt_ladder.py
│   ├── vanilla_aa.py
│   └── dlp_external.py
├── DELETED/                        # explicit record of v1 deletions
│   ├── agents/auditable_agent.py
│   ├── agents/llm_client.py        # moved into OpenClaw provider plugins
│   ├── agents/tools.py             # replaced by mcp_tools/
│   ├── bus/in_process.py
│   ├── bus/raw.py
│   ├── bus/audited.py
│   ├── runtime/runner.py
│   └── audit/sem.py                # replaced by audit/mswm.py
├── scripts/
│   ├── run_mvp.py                  # updated for v2 (end-to-end compose)
│   ├── run_grid.py                 # NEW — batch runner
│   └── make_repro_bundle.py        # NEW
├── benchmark/                      # NEW — scenario content
│   └── scenarios/v1.0.0/
├── fixtures/
│   ├── scenarios/                  # 2-agent E2E fixture used by phase A
│   └── cassettes/
├── tests/
│   ├── gateway/                    # NEW
│   ├── audit/
│   ├── saf/
│   ├── eval/
│   ├── generator/
│   └── e2e/                        # NEW — compose-based E2E
├── docker/                         # NEW
│   ├── gateway.Dockerfile
│   ├── openclaw-with-plugin.Dockerfile
│   └── compose-templates/
└── pyproject.toml                  # updated deps: aiohttp, docker, testcontainers
```

---

## Phase A: Gateway skeleton + channel plugin + minimal compose E2E

Delivers: a runnable two-container compose (one OpenClaw + one gateway) where the OpenClaw sends a message through the plugin to the gateway and receives one back. No MSWM, no policy hooks, no scenarios yet.

### Task A1: Gateway HTTP scaffold

**Files:**
- Create: `gateway/__init__.py`, `gateway/server.py`, `gateway/routes.py`
- Test: `tests/gateway/test_server_smoke.py`

**Acceptance:** `aiohttp` server starts on a configurable port, `GET /healthz` returns `{"ok": true}`.

- [ ] Step 1: Write failing test `test_server_health` that starts the server on a free port and asserts `/healthz` returns `{"ok": true}`.
- [ ] Step 2: Run test, confirm failure (`ModuleNotFoundError: gateway.server`).
- [ ] Step 3: Implement `server.py` with `build_app()` returning an `aiohttp.web.Application` with one GET route wired to a handler in `routes.py`.
- [ ] Step 4: Run test, confirm pass.
- [ ] Step 5: Commit: `feat(arena): gateway HTTP scaffold with healthz`.

### Task A2: Gateway Session object

**Files:**
- Create: `gateway/session.py`
- Test: `tests/gateway/test_session.py`

**Acceptance:** `Session` dataclass holds `scenario_id`, `action_log` (v1 `ActionLog`), `shadow_log`, `phase_tracker`, `cassette`, `hooks`, `condition`. Constructor wires them given `AuditCondition`.

- [ ] Step 1: Write failing test `test_session_baseline_has_no_audit_substrate` and `test_session_passive_has_full_substrate`.
- [ ] Step 2: Run, confirm fail.
- [ ] Step 3: Implement `Session` with conditional construction mirroring v1 `ScenarioRunner.__init__` (lines 41-85 in `clawsocialarena/runtime/runner.py`) but without the agent registry.
- [ ] Step 4: Run, confirm pass.
- [ ] Step 5: Commit: `feat(arena): gateway Session object`.

### Task A3: `/send` and `/recv` endpoints (no hooks yet)

**Files:**
- Modify: `gateway/routes.py`
- Modify: `gateway/server.py`
- Test: `tests/gateway/test_send_recv.py`

**Acceptance:** `POST /send {sender_id, recipient_id, content}` appends an `outbound_message` action to the log (when condition != baseline) and enqueues the message for the recipient. `POST /recv {recipient_id}` returns the next inbound message or `null`.

- [ ] Step 1: Write failing test `test_send_recv_roundtrip` with a passive-condition session: send from "alice" to "bob", recv as "bob", assert content.
- [ ] Step 2: Run, confirm fail.
- [ ] Step 3: Implement `/send` handler that calls `session.record_outbound(...)` (wrap `action_log.append` with an `outbound_message` ActionRecord) and pushes onto an in-memory `asyncio.Queue` keyed by `recipient_id`. Implement `/recv` handler that pops from the queue non-blocking or returns 204.
- [ ] Step 4: Run, confirm pass.
- [ ] Step 5: Commit: `feat(arena): gateway /send and /recv`.

### Task A4: `/tool_call`, `/tool_observation_return`, `/memory_write`, `/llm_call` endpoints

**Files:**
- Modify: `gateway/routes.py`
- Test: `tests/gateway/test_side_channels.py`

**Acceptance:** Each side-channel endpoint appends the corresponding action type to the log with the right payload schema.

- [ ] Step 1: Write one failing test per endpoint asserting the action appears in the log with the expected `action_type` and payload keys.
- [ ] Step 2: Run, confirm fail.
- [ ] Step 3: Implement handlers using `session.record_<type>(...)` helpers; payload field names match the v1 ActionRecord schema.
- [ ] Step 4: Run all four tests, confirm pass.
- [ ] Step 5: Commit: `feat(arena): gateway side-channel endpoints`.

### Task A5: CassetteRecorder

**Files:**
- Create: `gateway/cassette.py`
- Test: `tests/gateway/test_cassette.py`

**Acceptance:** Every append to the action log also writes a line to a `cassette.jsonl` under `session.work_dir`. Format: `{timestamp, kind, payload}`.

- [ ] Step 1: Write failing test `test_cassette_captures_every_action`.
- [ ] Step 2: Run, confirm fail.
- [ ] Step 3: Implement `CassetteRecorder` with a `record(kind, payload)` method writing one JSON line per call. Wire it into `session.record_*` helpers.
- [ ] Step 4: Run, confirm pass.
- [ ] Step 5: Commit: `feat(arena): cassette recorder`.

### Task A6: MCP host inside the gateway

**Files:**
- Create: `gateway/mcp_host.py`, `mcp_tools/__init__.py`, `mcp_tools/noop.py`
- Test: `tests/gateway/test_mcp_host.py`

**Acceptance:** Gateway can host a registered MCP tool server (stub `noop` tool returning `{"ok": true}`) and dispatch `tool_call` JSON-RPC requests to it in-process. Every call also records `tool_call` + `tool_observation_return` actions via the session.

- [ ] Step 1: Write failing test `test_mcp_noop_tool_logs_both_actions`.
- [ ] Step 2: Implement `McpHost.register(tool_name, handler)` plus a `/mcp/<tool_name>` HTTP route that reads JSON, dispatches to the handler, records the pair of actions, and returns the observation.
- [ ] Step 3: Run, confirm pass.
- [ ] Step 4: Commit: `feat(arena): in-gateway MCP host`.

### Task A7: TypeScript plugin scaffold

**Files:**
- Create: `gateway_plugin/package.json`, `gateway_plugin/tsconfig.json`, `gateway_plugin/src/index.ts`
- Test: `gateway_plugin/tests/index.test.ts` (vitest)

**Acceptance:** `pnpm test` passes a smoke test asserting the plugin entry exports the expected shape defined by `openclaw/plugin-sdk/channel-contract`. Use OpenClaw plugin SDK as a peer dependency.

- [ ] Step 1: Write `package.json` with `openclaw` as a devDependency (reading from `knowledge/openclaw` via a `file:` link for local dev).
- [ ] Step 2: Write smoke test importing the entry and checking type conformance.
- [ ] Step 3: Write minimal `index.ts` that exports a `ChannelPlugin` object.
- [ ] Step 4: Run `pnpm test`, confirm pass.
- [ ] Step 5: Commit: `feat(arena): OpenClaw gateway plugin scaffold`.

### Task A8: Plugin gateway client (HTTP)

**Files:**
- Create: `gateway_plugin/src/gateway-client.ts`
- Test: `gateway_plugin/tests/gateway-client.test.ts`

**Acceptance:** `GatewayClient.send()` POSTs JSON to the configured gateway URL and returns the `action_id`. Tests run against a fake HTTP server (vitest `msw` or a local `http.createServer`).

- [ ] Step 1: Write failing test for `GatewayClient.send` calling `/send`.
- [ ] Step 2: Implement the client using `fetch`.
- [ ] Step 3: Run, confirm pass.
- [ ] Step 4: Commit: `feat(arena): plugin gateway client`.

### Task A9: Plugin channel implementation

**Files:**
- Create: `gateway_plugin/src/channel.ts`
- Modify: `gateway_plugin/src/index.ts`
- Test: `gateway_plugin/tests/channel.test.ts`

**Acceptance:** The channel's `sendMessage` hook calls `GatewayClient.send`. The channel polls `/recv` every 250ms and surfaces inbound messages to OpenClaw's inbox. Every tool call reports through `GatewayClient.recordToolCall`.

- [ ] Step 1: Write failing tests for outbound routing and inbound delivery.
- [ ] Step 2: Implement the channel against the OpenClaw `channel-contract`.
- [ ] Step 3: Run, confirm pass.
- [ ] Step 4: Commit: `feat(arena): plugin channel implementation`.

### Task A10: OpenClaw-with-plugin Docker image

**Files:**
- Create: `docker/openclaw-with-plugin.Dockerfile`

**Acceptance:** `docker build` produces an image with OpenClaw CLI installed and the ClawSocialArena plugin preloaded at the expected path. A `--version` invocation succeeds.

- [ ] Step 1: Write a Dockerfile based on `node:24-alpine` that `npm install -g openclaw`, copies the built plugin tarball, and runs `openclaw plugin install ./clawsocial-plugin.tgz`.
- [ ] Step 2: Write a GitHub-style smoke: build the image locally in CI, run `docker run <image> openclaw --version`.
- [ ] Step 3: Commit: `feat(arena): OpenClaw-with-plugin Docker image`.

### Task A11: Gateway Dockerfile

**Files:**
- Create: `docker/gateway.Dockerfile`

**Acceptance:** `docker build` produces a Python 3.11 image with our gateway installed; `python -m gateway.server --port 8080` runs.

- [ ] Step 1: Write Dockerfile from `python:3.11-slim`.
- [ ] Step 2: Build locally; `curl :8080/healthz` succeeds.
- [ ] Step 3: Commit: `feat(arena): gateway Dockerfile`.

### Task A12: Minimal compose template

**Files:**
- Create: `docker/compose-templates/minimal.yml`

**Acceptance:** `docker compose -f minimal.yml up` brings up 1 gateway + 1 OpenClaw container; the OpenClaw container is configured to use the `clawsocial` channel and point to `gateway:8080`.

- [ ] Step 1: Author the compose file. Private bridge network, no external ports on the OpenClaw container.
- [ ] Step 2: Bring up, run a manual send/recv, teardown.
- [ ] Step 3: Commit: `feat(arena): minimal compose template`.

### Task A13: ComposeRunner

**Files:**
- Create: `gateway/compose_runner.py`
- Test: `tests/e2e/test_compose_up_down.py`

**Acceptance:** `ComposeRunner(template_path).run(env={...})` brings up the compose, waits for gateway health, yields a handle, tears down on exit. Python test uses `docker-compose` SDK.

- [ ] Step 1: Write failing test that asserts `ComposeRunner` yields a gateway URL and both containers are running.
- [ ] Step 2: Implement as a context manager using the `python-on-whales` library.
- [ ] Step 3: Run, confirm pass. Skip if Docker is unavailable.
- [ ] Step 4: Commit: `feat(arena): compose runner`.

### Task A14: E2E smoke test — one OpenClaw sends, gateway logs

**Files:**
- Create: `tests/e2e/test_minimal_compose.py`

**Acceptance:** Test brings up minimal compose, has the OpenClaw container run a one-shot message, asserts the gateway action log contains exactly one `outbound_message` with the expected content.

- [ ] Step 1: Write the E2E test.
- [ ] Step 2: Make it pass against a pinned OpenClaw version.
- [ ] Step 3: Commit: `feat(arena): minimal compose E2E smoke`.

### Task A15: Tag `phase-A-complete`

- [ ] Run `pytest -q` and confirm all phase-A tests green (including the E2E).
- [ ] Run `pnpm test` in `gateway_plugin/`.
- [ ] Tag: `git tag phase-A-complete`.
- [ ] Commit if any final doc tweaks: `chore(arena): phase A complete`.

---

## Phase B: Migrate surviving v1 modules and delete obsolete ones

Delivers: all surviving v1 modules live in their new gateway-internal paths, old in-process runtime and bus are deleted, `audit/sem.py` is replaced by `audit/mswm.py` stub, all existing tests that ran against the in-process runtime are deleted or rewritten.

### Task B1: Move `action_log.py` into its final location (no move needed, unchanged)

**Files:** confirm `action_log.py` is referenced by `gateway/session.py`.

- [ ] Step 1: Verify imports.
- [ ] Step 2: Commit if any fixups: `chore(arena): confirm action_log stays put`.

### Task B2: Delete `bus/` directory

**Files:**
- Delete: `clawsocialarena/bus/in_process.py`, `bus/raw.py`, `bus/audited.py`, `bus/__init__.py`

- [ ] Step 1: `git rm` the directory.
- [ ] Step 2: Run `pytest -q`; confirm only expected failures (tests that target the deleted bus).
- [ ] Step 3: Delete those tests in the same commit.
- [ ] Step 4: Commit: `refactor(arena): delete v1 in-process message bus`.

### Task B3: Delete `agents/` directory

**Files:**
- Delete: `clawsocialarena/agents/auditable_agent.py`, `agents/llm_client.py`, `agents/tools.py`, `agents/__init__.py`

- [ ] Step 1: `git rm` directory.
- [ ] Step 2: Run tests; delete the v1 agent tests.
- [ ] Step 3: Commit: `refactor(arena): delete v1 in-process agent classes`.

### Task B4: Delete `runtime/runner.py`

- [ ] Step 1: `git rm clawsocialarena/runtime/runner.py`.
- [ ] Step 2: Run tests; expect failures in `tests/runtime/*`; delete those.
- [ ] Step 3: Commit: `refactor(arena): delete v1 ScenarioRunner`.

### Task B5: Delete `audit/sem.py`

**Files:**
- Delete: `clawsocialarena/audit/sem.py`
- Test: `tests/audit/test_sem.py` -> delete

- [ ] Step 1: Delete both.
- [ ] Step 2: Commit: `refactor(arena): remove SEM stub (replaced by MSWM in phase C)`.

### Task B6: Rename symbols SEM -> MSWM in `types.py` and `docs/`

**Files:**
- Modify: `clawsocialarena/types.py`, `docs/plan.md`, any references
- Run: `grep -r "SEM" clawsocialarena docs/ | grep -v CHANGELOG`

- [ ] Step 1: Grep for "SEM", review results; rename each to MSWM (careful with "SEMantic" or similar false positives).
- [ ] Step 2: Run tests; fix import errors.
- [ ] Step 3: Commit: `refactor(arena): rename SEM -> MSWM across codebase`.

### Task B7: Update `scripts/run_mvp.py` to use ComposeRunner

**Files:**
- Modify: `scripts/run_mvp.py`

**Acceptance:** `python -m scripts.run_mvp` brings up minimal compose, runs a 3-turn scripted scenario, asserts terminal predicate passes.

- [ ] Step 1: Rewrite the script end-to-end.
- [ ] Step 2: Run manually; confirm success.
- [ ] Step 3: Commit: `refactor(arena): run_mvp uses ComposeRunner`.

### Task B8: Tag `phase-B-complete`

- [ ] Run full test suite; ensure green.
- [ ] Tag: `git tag phase-B-complete`.
- [ ] Commit: `chore(arena): phase B complete`.

---

## Phase C: MSWM online state machine and attribution walker

Delivers: `audit/mswm.py` with the per-peer mental model described in spec §2.6, plus `audit/attribution.py` rewritten to walk MSWM references. SAF dims 2 and 3 are now decidable.

### Task C1: MSWM data model

**Files:**
- Create: `clawsocialarena/audit/mswm.py`
- Test: `tests/audit/test_mswm_model.py`

**Acceptance:** `MSWM` class with `state[i][j]` returning a dict with the keys from spec §2.6.

- [ ] Step 1: Write failing test creating an `MSWM` and asserting `mswm.get("alice", "bob")` returns a default-initialized peer model.
- [ ] Step 2: Run, fail.
- [ ] Step 3: Implement the data model with typed dataclasses (`PeerModel`).
- [ ] Step 4: Run, pass.
- [ ] Step 5: Commit: `feat(arena): MSWM data model`.

### Task C2: MSWM update rule for `outbound_message`

**Files:**
- Modify: `clawsocialarena/audit/mswm.py`
- Test: `tests/audit/test_mswm_outbound.py`

**Acceptance:** When `outbound_message` action appended with payload mentioning a `mentioned_items` list, MSWM adds each item to `state[sender][recipient].items_told_to_j` and `state[recipient][sender].items_learned_from_j`.

- [ ] Step 1: Write failing test with a canned ActionRecord carrying `mentioned_items=["z"]`.
- [ ] Step 2: Fail.
- [ ] Step 3: Implement `MSWM.on_action(action)`.
- [ ] Step 4: Pass.
- [ ] Step 5: Commit: `feat(arena): MSWM outbound_message update rule`.

### Task C3: MSWM update rules for `memory_write`, `summary_write`, `retrieval_fetch`

**Files:**
- Modify: `clawsocialarena/audit/mswm.py`
- Test: `tests/audit/test_mswm_side_channels.py`

**Acceptance:** Side-channel actions propagate `mentioned_items` into MSWM per rules in spec §2.6; retrieval is modeled as "agent now knows item if it was in the retrieved content."

- [ ] Step 1: Write tests per action type.
- [ ] Step 2: Implement.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): MSWM side-channel update rules`.

### Task C4: Joint decidability predicate

**Files:**
- Modify: `clawsocialarena/audit/mswm.py`
- Test: `tests/audit/test_mswm_decidability.py`

**Acceptance:** `MSWM.joint_decidability(agent_id, predicate)` returns `decidable` iff every required field in the predicate's feature set is present in MSWM state and the predicate's guard does not refer to unknown peers.

- [ ] Step 1: Write failing test on a small 3-agent example from the inferential-leakage audit challenge.
- [ ] Step 2: Implement.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): MSWM joint decidability`.

### Task C5: Wire MSWM into `Session.record_*`

**Files:**
- Modify: `gateway/session.py`
- Test: `tests/gateway/test_session_with_mswm.py`

**Acceptance:** Each `session.record_*` call calls `mswm.on_action(action)` after `action_log.append` but before policy hooks evaluate.

- [ ] Step 1: Write failing test that sends a message and asserts MSWM state updated.
- [ ] Step 2: Implement.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): session wires MSWM online`.

### Task C6: MSWM-aware policy hook

**Files:**
- Create: `clawsocialarena/audit/policies/mswm_aware.py`
- Test: `tests/audit/test_mswm_hook.py`

**Acceptance:** `MswmAwareHook` evaluates "does sending item z to recipient j violate the joint-decidability invariant from the GT policies?". Under `enforce`, redacts `z` from the outbound content; under `passive`, logs a `policy_decision` with verdict `would_block`.

- [ ] Step 1: Write failing test with inferential-leakage audit challenge GT.
- [ ] Step 2: Implement hook.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): MSWM-aware policy hook`.

### Task C7: Attribution DAG builder — causal edges

**Files:**
- Create: `clawsocialarena/audit/attribution.py` (replaces v1)
- Test: `tests/audit/test_attribution_causal.py`

**Acceptance:** `AttributionGraphBuilder(action_log, mswm).build()` produces a DAG whose edges come from `source_action_ids` payload references plus MSWM `items_learned_from_j` back-references.

- [ ] Step 1: Write failing test using a two-hop causal chain A -> B summary -> C action.
- [ ] Step 2: Implement builder.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): attribution DAG causal edges`.

### Task C8: Attribution DAG builder — proximity fallback

**Files:**
- Modify: `clawsocialarena/audit/attribution.py`
- Test: `tests/audit/test_attribution_proximity.py`

**Acceptance:** When causal references are missing, fall back to proximity heuristic (same turn, recipient/sender match, item overlap with MSWM).

- [ ] Step 1: Write failing test with intentionally stripped `source_action_ids`.
- [ ] Step 2: Implement fallback.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): attribution proximity fallback`.

### Task C9: Node labelling (L0 / L1 / LX / LR / LF)

**Files:**
- Modify: `clawsocialarena/audit/attribution.py`
- Test: `tests/audit/test_attribution_labels.py`

**Acceptance:** Produced DAG nodes carry labels from the error-chain taxonomy per spec §3.2 dim 3.

- [ ] Step 1: Write failing tests for each label.
- [ ] Step 2: Implement.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): attribution DAG node labels`.

### Task C10: Tag `phase-C-complete`

- [ ] Full test suite green.
- [ ] Tag: `git tag phase-C-complete`.

---

## Phase D: Scenario generator v2

Delivers: generator emits v2 GT bundle + `docker-compose.yml` + `personas/` + `mcp/` alongside `scenario.json` and `scenario.gt.json`. CLI accepts `--category`, `--family`, `--n`, `--seed`, `--instantiation-mode {deterministic, llm}`, `--out`.

### Task D1: Scenario model v2

**Files:**
- Modify: `clawsocialarena/scenario/models.py`
- Test: `tests/scenario/test_models_v2.py`

**Acceptance:** `GTBundle` dataclass gains `mcp_tool_manifest: dict[str, McpToolSpec]`, `persona_manifest: dict[str, PersonaRef]`.

- [ ] Step 1: Add dataclasses.
- [ ] Step 2: Write failing deserialization test from canonical JSON.
- [ ] Step 3: Implement JSON (de)serialization.
- [ ] Step 4: Commit: `feat(arena): scenario model v2 adds MCP + persona manifests`.

### Task D2: Compose emitter

**Files:**
- Create: `clawsocialarena/generator/compose_emitter.py`
- Test: `tests/generator/test_compose_emitter.py`

**Acceptance:** Given a `Scenario`, emits a valid `docker-compose.yml` with N OpenClaw containers + 1 gateway on a private network.

- [ ] Step 1: Write failing test that asserts compose YAML parses and has `len(services) == N+1`.
- [ ] Step 2: Implement emitter using a Jinja2 template.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): compose emitter`.

### Task D3: Persona emitter

**Files:**
- Create: `clawsocialarena/generator/persona_emitter.py`
- Test: `tests/generator/test_persona_emitter.py`

**Acceptance:** Given a `Scenario`, emits `personas/<agent_id>.system.md` (persona prompt) and `personas/<agent_id>.tools.json` (allowed tool manifest) per agent.

- [ ] Step 1: Write failing test.
- [ ] Step 2: Implement.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): persona emitter`.

### Task D4: MCP emitter

**Files:**
- Create: `clawsocialarena/generator/mcp_emitter.py`
- Test: `tests/generator/test_mcp_emitter.py`

**Acceptance:** Given the MCP tool manifest, emits `mcp/<tool>.json` mcporter configs referencing the gateway as the MCP host.

- [ ] Step 1: Test.
- [ ] Step 2: Implement.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): MCP manifest emitter`.

### Task D5: GT assembly v2

**Files:**
- Modify: `clawsocialarena/generator/gt_assembly.py`
- Test: `tests/generator/test_gt_assembly_v2.py`

**Acceptance:** GT assembly produces the v2 bundle including `mcp_tool_manifest` and `persona_manifest`. Mechanically-composed.

- [ ] Step 1: Test.
- [ ] Step 2: Update assembly.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): GT bundle v2`.

### Task D6: Attack injection unchanged, re-wired

**Files:**
- Modify: `clawsocialarena/generator/attack_injection.py`

**Acceptance:** Existing attack injection still runs on the new pipeline; only types changed (payload now includes `mentioned_items` for MSWM updates).

- [ ] Step 1: Update types.
- [ ] Step 2: Run existing tests to confirm.
- [ ] Step 3: Commit: `refactor(arena): attack injection for v2`.

### Task D7: Generator CLI v2

**Files:**
- Modify: `clawsocialarena/generator/cli.py`

**Acceptance:** CLI supports the flags in §Phase-D intro and outputs a full v2 scenario bundle.

- [ ] Step 1: Add argparse flags.
- [ ] Step 2: Wire emitters in sequence.
- [ ] Step 3: Smoke: `python -m clawsocialarena.generator.cli --category CU --family scheduling --n 1 --seed 42 --out /tmp/gen_v2` produces a valid bundle.
- [ ] Step 4: Commit: `feat(arena): generator CLI v2`.

### Task D8: Scenario loader v2

**Files:**
- Modify: `clawsocialarena/scenario/loader.py`
- Test: `tests/scenario/test_loader_v2.py`

**Acceptance:** `ScenarioLoader.load(scenario_dir)` reads compose + personas + mcp and returns a `(Scenario, GTBundle, ComposeSpec)` triple.

- [ ] Step 1: Test.
- [ ] Step 2: Update loader.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): scenario loader v2`.

### Task D9: Scenario validator v2

**Files:**
- Modify: `clawsocialarena/scenario/validate.py`

**Acceptance:** `python -m clawsocialarena.scenario.validate <dir>` validates compose YAML, persona file presence, MCP manifest consistency, GT bundle schema.

- [ ] Step 1: Extend validator.
- [ ] Step 2: Add tests with both valid and invalid fixtures.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): scenario validator v2`.

### Task D10: Tag `phase-D-complete`

- [ ] Full suite green.
- [ ] Tag: `git tag phase-D-complete`.

---

## Phase I: Governance-aware audit revision

Delivers: SAF expands from five dimensions to six by adding Identity-Governance Auditability. The benchmark attack taxonomy expands from three axes to four: Collaboration, Security, Privacy, and Governance. Scenario bundles gain `governance/manifest.json`; action records gain a hashed governance object; scorecards and analysis gain governance metrics. This phase must land before Phase E benchmark content so every generated scenario uses the revised schema.

### Task I1: Governance schema in scenario and action models

**Files:**
- Modify: `clawsocialarena/types.py`
- Modify: `clawsocialarena/scenario/models.py`
- Modify: `clawsocialarena/generator/template.py`
- Test: `tests/test_types.py`, `tests/scenario/test_models.py`, `tests/generator/test_template.py`

**Acceptance:** `ActionRecord` can carry a `governance` object with `owner_id`, `active_identity_id`, `authorization_scope_id`, `approval_mandate_id`, and `escalation_state`. `ScenarioAgent` can declare default owner / identity metadata. `GTBundle` can carry a `governance_manifest` with owners, identities, authorization scopes, approval mandates, and escalation rules. Serialization round-trips and missing governance data fails validation for non-baseline v1.0.0 scenarios.

- [ ] Step 1: Add failing tests for governance object validation and round-trip serialization.
- [ ] Step 2: Add typed models for `GovernanceRecord`, `GovernanceManifest`, `AuthorizationScope`, `ApprovalMandate`, and `EscalationRule`.
- [ ] Step 3: Update `ActionRecord` hashing tests so the governance object is included in the hash input.
- [ ] Step 4: Run the focused tests and the full Python test suite.

### Task I2: Gateway governance enforcement hook

**Files:**
- Create: `clawsocialarena/audit/policies/governance.py`
- Modify: `clawsocialarena/gateway/session.py`
- Modify: `clawsocialarena/gateway/routes.py`
- Test: `tests/audit/test_governance_hook.py`, `tests/gateway/test_governance_logging.py`

**Acceptance:** Every audited message, tool call, memory write, and side-channel record can be checked against the governance manifest. Passive mode logs governance verdicts; enforce mode blocks or escalates owner-binding spoofing, wrong active identity, out-of-scope resource use, missing owner approval, and denied escalation states. Baseline still forwards without records.

- [ ] Step 1: Write failing tests for one permitted action and five blocked actions: owner spoof, identity confusion, scope creep, approval bypass, and denied escalation.
- [ ] Step 2: Implement `GovernancePolicyHook` with hook kind `governance` or a shared pre-action dispatch path.
- [ ] Step 3: Wire the hook into `Session.build(...)` when a governance manifest is present.
- [ ] Step 4: Confirm that enforce mode does not update MSWM or downstream queues for blocked governed actions.

### Task I3: Sixth SAF scorer and scorecard schema

**Files:**
- Create: `clawsocialarena/saf/scorers/identity_governance.py`
- Modify: `clawsocialarena/saf/saf_scorer.py`
- Modify: `clawsocialarena/eval/scorecard.py`
- Modify: `clawsocialarena/eval/runner.py`
- Test: `tests/saf/test_identity_governance.py`, `tests/eval/test_scorecard.py`, `tests/eval/test_runner.py`

**Acceptance:** `SAFScorer` emits six dimensions with equal default weights of `1/6`. `identity_governance` computes `γ = governed_actions_decidable_and_permitted / governed_actions_declared`. Scorecards include the sixth score, its binary pass flag, and governance diagnostics. Existing five-dimension fixtures are either migrated or explicitly marked as legacy.

- [ ] Step 1: Write a golden test with three governed actions: permitted, undecidable, and disallowed.
- [ ] Step 2: Implement the scorer against `ActionRecord.governance` plus `GTBundle.governance_manifest`.
- [ ] Step 3: Update geometric mean weights, threshold handling, and scorecard JSON schema.
- [ ] Step 4: Update golden scorecards and document any expected score drift.

### Task I4: Governance attack taxonomy in generator

**Files:**
- Modify: `clawsocialarena/generator/attack_injection.py`
- Modify: `clawsocialarena/generator/gt_assembly.py`
- Create: `clawsocialarena/generator/governance_emitter.py`
- Test: `tests/generator/test_governance_attacks.py`, `tests/generator/test_gt_assembly.py`

**Acceptance:** The generator supports governance attack types: `owner_binding_spoofing`, `identity_confusion`, `scope_creep`, `approval_bypass`, `mandate_laundering`, and `audit_evasion`. Each attack emits mechanical GT for expected governance violations and a manifest sufficient for the sixth SAF scorer.

- [ ] Step 1: Add failing tests for one deterministic scenario per governance attack type.
- [ ] Step 2: Emit `governance/manifest.json` with owner, identity, scope, approval, and escalation expectations.
- [ ] Step 3: Thread attack metadata into `canonical_action_stream`, `policies`, `invariants`, and `governance_manifest`.
- [ ] Step 4: Update `python -m clawsocialarena.generator.cli --list-templates` smoke expectations only if template IDs change.

### Task I5: Governance coverage in Phase E content

**Files:**
- Modify: `clawsocialarena/generator/registry.py`
- Modify: planned template files under `clawsocialarena/generator/templates/`
- Create or modify: `benchmark/scenarios/v1.0.0/audit_challenges/mandate_laundering_v1/`
- Create or modify: `benchmark/scenarios/v1.0.0/audit_challenges/approval_bypass_v1/`
- Test: `tests/audit_challenges/test_governance_cases.py`

**Acceptance:** At least 15 adversarial main scenarios exercise Governance attacks, distributed across CU, MG, HS, CM, and AM. The five audit challenge cases include the existing three (`inferential_leakage_v1`, `cross_delegation_attr_v1`, `partial_log_recovery_v1`) plus two governance cases (`mandate_laundering_v1`, `approval_bypass_v1`). Vanilla-AA either passes or abstains; SAF fails on the intended dimension.

- [ ] Step 1: Update the Phase E stratification table so governance attacks are not undercounted.
- [ ] Step 2: Author the two governance audit challenge cases by hand before batch generation.
- [ ] Step 3: Add audit challenge assertion tests comparing `VanillaAAEvalRunner` and `EvalRunner`.
- [ ] Step 4: Update annotator workbook fields so annotators reproduce the governance manifest.

### Task I6: Analysis, preregistration, and docs

**Files:**
- Modify: `clawsocialarena/analysis/aggregator.py`
- Modify: `clawsocialarena/analysis/tables.py`
- Modify: `clawsocialarena/analysis/figures.py`
- Modify: `clawsocialarena/analysis/prereg_check.py`
- Modify: `docs/preregistration.md`
- Modify: `README.md`

**Acceptance:** Aggregated results include governance metric columns and sixth SAF dimension columns. Tables and figures can break down attacks by four axes. The preregistration names six SAF dimensions, H2 covers privacy / security / governance, and H4 covers inference-chain plus identity-governance failures.

- [ ] Step 1: Add synthetic scorecard fixtures with governance columns.
- [ ] Step 2: Update analysis tests for headline, model, rewrite, and ablation tables.
- [ ] Step 3: Update preregistration before any live main run.
- [ ] Step 4: Run `pytest`, `mypy`, `ruff`, and TypeScript tests if gateway plugin types changed.

### Phase I acceptance checklist

- [ ] Governance schema exists in scenario bundles, action records, GT bundles, and scorecards.
- [ ] `SAFScorer` emits six dimensions and the geometric mean uses `1/6` weights by default.
- [ ] Governance attack types are first-class and can be generated deterministically.
- [ ] Two governance audit challenge cases pass their vanilla-AA-vs-SAF assertion tests.
- [ ] Analysis and preregistration mention collaboration, security, privacy, and governance consistently.
- [ ] Full Python test suite, `mypy`, `ruff`, and gateway plugin tests pass.

---

## Phase E0: Template worktree integration

Delivers: the existing Phase E template work from `worktree/phase-I-governance` is imported into main before resource fixtures are added. This avoids rewriting templates and lets Phase I.5 adapt the full template set to filesystem and personal-database resources.

### Task E0: Integrate existing Phase E template worktrees

**Files:**
- Copy / reconcile from: `worktree/phase-I-governance/clawsocialarena/generator/templates/`
- Copy / reconcile from: `worktree/phase-I-governance/clawsocialarena/generator/registry.py`
- Modify: `clawsocialarena/generator/template.py`
- Modify: `scripts/generate_benchmark_scaffold.py`
- Test: `tests/test_generator/test_phase_e_*`, `tests/test_scripts/test_generate_benchmark_scaffold.py`

**Acceptance:** Main registers the existing Phase E template set from the worktree instead of rewriting it. The task-family taxonomy is reconciled with the current spec (`scheduling`, `consensus`, `coalition`, `inference`, plus hard-stratum `code_review` / `doc_editing`). Every imported template builds under the current governance, MSWM, and validation contracts. Phase I.5 then adds resource fixtures and resource policies across this imported set.

- [ ] Step 1: Diff the worktree templates against main's current schema and identify incompatibilities.
- [ ] Step 2: Import templates in small batches, starting with registry and task-family enum reconciliation.
- [ ] Step 3: Adapt imported templates to emit governance manifests where needed.
- [ ] Step 4: Run template, generator, validator, mypy, and ruff checks after each batch.

---

## Phase I.5: Resource-aware scenario construction

Delivers: per-user filesystem and personal database fixtures as first-class scenario resources. Scenario bundles gain `resources/manifest.json`, seeded `resources/files/<agent_id>/...`, optional `resources/db/<agent_id>.sqlite`, gateway-hosted `fs.*` and `db.*` MCP tools, resource attack cases, and validator checks. This phase must finish before the final Phase E generation pass; adding resources after generation changes scenario IDs, GT bundles, compose mounts, MCP manifests, and expected final states.

### Task I.5-1: Resource schema and bundle layout

**Files:**
- Modify: `clawsocialarena/scenario/models.py`
- Modify: `clawsocialarena/generator/template.py`
- Modify: `clawsocialarena/generator/gt_assembly.py`
- Test: `tests/test_scenario/test_resource_models.py`, `tests/test_generator/test_resource_manifest.py`

**Acceptance:** `GTBundle` can carry a `resource_manifest` with file and database resource entries. Each entry declares `resource_id`, type, owner, sensitivity label, allowed operations by identity / scope, consent requirement, initial hash or row digest, and expected final state. Serialization round-trips and malformed references fail validation.

- [ ] Step 1: Add failing model tests for a file, directory, SQLite database, table, and row-set resource.
- [ ] Step 2: Add typed resource manifest models and lift them into `GTBundle`.
- [ ] Step 3: Extend `TemplateShape` so templates can declare resource fixtures and resource policies.
- [ ] Step 4: Update GT assembly so `scenario.gt.json` and `resources/manifest.json` agree exactly.

### Task I.5-2: Resource emitter, compose mounts, loader, and validator

**Files:**
- Create: `clawsocialarena/generator/resource_emitter.py`
- Modify: `clawsocialarena/generator/cli.py`
- Modify: `clawsocialarena/generator/compose_emitter.py`
- Modify: `clawsocialarena/scenario/loader.py`
- Modify: `clawsocialarena/scenario/validate.py`
- Test: `tests/test_generator/test_resource_emitter.py`, `tests/test_generator/test_compose_emitter.py`, `tests/test_scenario/test_validate_resources.py`

**Acceptance:** Generated bundles include deterministic resource files, database fixtures, and `resources/manifest.json`. Compose mounts resources into the gateway service for normal scenarios. Agent containers do not receive raw writable mounts for normal benchmark cases; access goes through MCP tools. The validator checks resource paths, hashes, ownership references, allowed operation references, and manifest consistency.

- [ ] Step 1: Write failing tests for generated file and SQLite fixtures.
- [ ] Step 2: Emit `resources/files/<agent_id>/...`, `resources/db/<agent_id>.sqlite`, and `resources/manifest.json`.
- [ ] Step 3: Add gateway resource mounts to compose output.
- [ ] Step 4: Extend loader and validator with resource checks.

### Task I.5-3: Gateway-hosted filesystem and personal database MCP tools

**Files:**
- Create: `clawsocialarena/mcp_tools/filesystem.py`
- Create: `clawsocialarena/mcp_tools/personal_db.py`
- Modify: `clawsocialarena/gateway/session.py`
- Modify: `clawsocialarena/gateway/routes.py`
- Test: `tests/test_mcp_tools/test_filesystem.py`, `tests/test_mcp_tools/test_personal_db.py`, `tests/gateway/test_resource_tools.py`

**Acceptance:** Gateway tools implement `fs.list`, `fs.read`, `fs.write`, `fs.delete`, `db.query`, `db.insert`, `db.update`, and `db.delete`. Every call is represented as `tool_call` plus `tool_observation_return`, carries `resource_id` and governance context, and applies side effects only after policy hooks allow the candidate. Denied writes and deletes leave resource state unchanged in `enforce`.

- [ ] Step 1: Write failing tests for allowed read, blocked cross-user read, allowed update, and blocked delete.
- [ ] Step 2: Implement handlers against a per-scenario resource root and SQLite fixtures.
- [ ] Step 3: Register resource tools when the resource manifest declares them.
- [ ] Step 4: Confirm blocked tool calls do not mutate files or databases.

### Task I.5-4: Resource policies, attacks, and scoring hooks

**Files:**
- Modify: `clawsocialarena/audit/policies/governance.py`
- Modify: `clawsocialarena/generator/attack_injection.py`
- Modify: `clawsocialarena/saf/scorers/policy_checkability.py`
- Modify: `clawsocialarena/eval/leak_detector.py`
- Test: `tests/audit/test_resource_governance.py`, `tests/test_generator/test_resource_attacks.py`, `tests/test_saf/test_resource_policy_checkability.py`

**Acceptance:** Resource operations are checked against both the resource manifest and governance manifest. Attack injection supports unauthorized delete, silent overwrite, cross-user file read, sensitive database query, database-to-message exfiltration, and consent-bypassed update. SAF can mark the relevant policies decidable and can identify final-state violations from resource hashes or row digests.

- [ ] Step 1: Add failing tests for each resource attack type.
- [ ] Step 2: Extend policy checks so allowed operations, consent, owner, identity, scope, and mandate are evaluated together.
- [ ] Step 3: Extend leak detection so protected file or database content in outbound messages counts as resource exfiltration.
- [ ] Step 4: Add final-state hash / row-digest checks to the evaluation path.

### Task I.5-5: Resource audit challenge fixtures

**Files:**
- Create or modify: `tests/fixtures/resource_audit_challenges/unauthorized_delete_v1/`
- Create or modify: `tests/fixtures/resource_audit_challenges/cross_user_file_read_v1/`
- Create or modify: `tests/fixtures/resource_audit_challenges/personal_db_exfiltration_v1/`
- Test: `tests/audit_challenges/test_resource_cases.py`

**Acceptance:** Resource audit challenge fixtures show that vanilla AA passes or abstains while SAF detects the target failure. At least one case tests a blocked `fs.delete`, one tests a sensitive file read followed by message exfiltration, and one tests an out-of-scope personal database query. If an audit-bypass challenge uses a raw writable mount, the expected result is a failed log-completeness or final-hash check, not a normal successful scenario. Phase E may promote one of these fixtures into the fixed five named audit challenge cases, but these fixtures do not by themselves change the benchmark target count.

- [x] Step 1: Author the three resource challenge fixture bundles by hand.
- [x] Step 2: Add vanilla-AA-vs-SAF assertion tests.
- [x] Step 3: Add resource fields to the annotator workbook.
- [x] Step 4: Run focused resource tests plus the full verification suite.

### Phase I.5 acceptance checklist

- [ ] Resource manifests exist in GT and as `resources/manifest.json`.
- [ ] Generated scenario bundles include deterministic file and database fixtures.
- [ ] Resource MCP tools are gateway-hosted and audited.
- [ ] Resource writes and deletes are blocked before mutation in `enforce`.
- [ ] Resource attack types can be generated deterministically.
- [x] Resource audit challenge fixtures pass their vanilla-AA-vs-SAF assertion tests.
- [ ] Final Phase E generation remains blocked until this checklist and Phase I are complete.

---

## Phase E: Benchmark content

Delivers: 14 category x family templates + 2 hard-stratum templates + 5 named audit challenge cases + 5 episode-graph definitions. Generation scripts first produce `benchmark/scenarios/v1.0.0/` as a 680-variant balanced difficulty pilot. Phase I, Phase E0, Phase I.5, and the task-success calibration plan must be complete before final generation so generated content includes imported templates, governance manifests, resource manifests, resource fixtures, task schema v0, designed difficulty tiers, source-pattern metadata, and the 4-axis attack taxonomy.

### Task E1-E14: Write category x family templates

**Files:** per the layout table in spec §4.3, create one template file per pair under `clawsocialarena/generator/templates/`.

**Acceptance:** Each template registered with the registry; `python -m clawsocialarena.generator.cli --list-templates` shows 14 pairs; each pair produces at least one valid scenario under the deterministic instantiation mode.

Template development pattern (same for each — repeat for all 14 pairs):

- [ ] Step 1: Write template module with `build(seed, scenario_id) -> TemplateShape`.
- [ ] Step 2: Write template test asserting the shape declares the correct agent count, tool manifest, phase schedule skeleton.
- [ ] Step 3: Implement template minimally (deterministic strings; LLM-assisted phase comes in Phase 4.2-equivalent of §Phase E tail).
- [ ] Step 4: Run tests; confirm scenario bundle is producible.
- [ ] Step 5: Commit per 2-3 templates: `feat(arena): templates for <pair1>, <pair2>, ...`.

Template pairs to write (one task each, labeled E1 through E14):

E1 CD × Consensus Allocation, E2 CD × Cross-User Inference Containment,
E3 MC × Group Scheduling, E4 MC × Cross-User Inference Containment,
E5 CU × Group Scheduling (replaces v1), E6 CU × Coalition Resistance,
E7 MG × Consensus Allocation, E8 MG × Coalition Resistance,
E9 HS × Consensus Allocation, E10 HS × Coalition Resistance,
E11 CM × Consensus Allocation, E12 CM × Coalition Resistance,
E13 AM × Group Scheduling, E14 AM × Cross-User Inference Containment.

### Task E15: Hard-stratum templates

**Files:**
- Create: `clawsocialarena/generator/templates/hard_code_review.py`, `hard_doc_editing.py`
- Test: per-template tests

**Acceptance:** Both registered; produce valid scenarios. Planted-bug lists and planted-field lists are declared in GT.

- [ ] Step 1-5: same pattern; commit: `feat(arena): hard-stratum code-review + doc-editing templates`.

### Task E16: Named audit challenge cases

**Files:**
- Create: `benchmark/scenarios/v1.0.0/audit_challenges/inferential_leakage_v1/`, `cross_delegation_attr_v1/`, `partial_log_recovery_v1/`, `mandate_laundering_v1/`, and `approval_bypass_v1/`
- Test: `tests/audit_challenges/test_cases_fail_vanilla_pass_saf.py`

**Acceptance:** Each audit challenge case is a hand-authored scenario bundle. The test asserts VanillaAA scores it compliant or abstains AND SAF catches the violation on the targeted dimension. The two governance cases target Identity-Governance Auditability (γ).

- [ ] Step 1-5: for each audit challenge case, author `scenario.json` + `scenario.gt.json` + compose + personas + MCP bundle, write the assertion test, commit.

### Task E17: Episode-graph definitions

**Files:**
- Create: `benchmark/scenarios/v1.0.0/episode_graphs/<category>_<name>/graph.json` for each of 5 graphs
- Create: `scripts/generate_episode_graphs.py`
- Test: `tests/generator/test_episode_graphs.py`

**Acceptance:** Each graph.json declares 4 linked scenarios sharing persona state and a cumulative invariant set. `generate_episode_graphs.py --seed 1 --out benchmark/scenarios/v1.0.0/episode_graphs/` produces all 5 graphs.

- [ ] Step 1: Author graph schema (JSON) and one example graph.
- [ ] Step 2: Write failing integration test.
- [ ] Step 3: Implement generator script.
- [ ] Step 4: Validate all 5 graphs load.
- [ ] Step 5: Commit: `feat(arena): episode-graph stratum`.

### Task E18: Balanced difficulty benchmark generation

**Files:**
- Create or modify: `scripts/generate_benchmark_scaffold.py`, `scripts/orchestrate_benchmark.py`
- Output: `benchmark/scenarios/v1.0.0/{630 main matched variants + 25 hard + 20 episode + 5 audit challenge cases}`

**Acceptance:** Running the orchestrated generation path with a pinned seed produces exactly 680 scenario-variant directories for the balanced difficulty pilot; `python -m clawsocialarena.scenario.validate benchmark/scenarios/v1.0.0` passes. Each main row has `task_schema_version`, `designed_difficulty_tier`, `source_pattern`, `benign_task_objective`, and `task_success_spec` in the construction manifest.

- [ ] Step 1: Write the script. Under deterministic instantiation (no LLM), produces placeholder scenarios with distinct content.
- [ ] Step 2: Check-in the output tarball-compressed if > 10 MB; otherwise plain.
- [ ] Step 3: Commit: `feat(arena): benchmark v1.0.0 content`.

### Task E19: Tag `phase-E-complete`

- [ ] Suite green.
- [ ] Tag: `git tag phase-E-complete`.

---

## Phase F: Evaluation pipeline v2

Delivers: updated SAFScorer consuming MSWM; cumulative metrics module for episode-graph stratum; cassette replay hooks; updated scorecard schema.

### Task F1: Policy Checkability scorer reads MSWM

**Files:**
- Modify: `clawsocialarena/saf/policy_checkability.py`
- Test: `tests/saf/test_policy_checkability_mswm.py`

**Acceptance:** Given `(action_log, mswm_snapshots, gt_policies)`, returns the fraction of policies decidable. Works from MSWM state at the right moment (snapshot at the policy's `evaluation_turn`).

- [ ] Steps 1-5: TDD, commit: `feat(arena): psi scorer consumes MSWM`.

### Task F2: Attribution F1 scorer consumes MSWM-built DAG

**Files:**
- Modify: `clawsocialarena/saf/attribution_f1.py`
- Test: `tests/saf/test_attribution_f1_mswm.py`

- [ ] Steps 1-5: TDD, commit: `feat(arena): tau scorer consumes MSWM DAG`.

### Task F3: Cumulative evaluation module

**Files:**
- Create: `clawsocialarena/eval/cumulative.py`
- Test: `tests/eval/test_cumulative.py`

**Acceptance:** Given an episode-graph run bundle (list of per-episode scorecards + persona-state checkpoints), compute Social Recall(t), Social Precision(t) against cumulative invariants, TLR(t), CPR(t). Trajectories returned as lists.

- [ ] Step 1: Write failing test with a canned 4-episode graph fixture.
- [ ] Step 2: Implement per spec §4.7.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): cumulative evaluation module`.

### Task F4: Scorecard v2 schema

**Files:**
- Modify: `clawsocialarena/eval/scorecard.py`
- Test: `tests/eval/test_scorecard_v2.py`

**Acceptance:** Scorecard JSON embeds `gateway_invariant_passed: bool`, `cassette_hash: str`, `live_or_replay: "live"|"replay"`, `episode_graph_id: str|null`.

- [ ] Steps 1-5: TDD, commit: `feat(arena): scorecard v2 schema`.

### Task F5: EvalRunner five-stage v2

**Files:**
- Modify: `clawsocialarena/eval/runner.py`
- Test: `tests/eval/test_eval_runner_v2.py`

**Acceptance:** Runs against a cassette + action log + shadow log + GT; emits a v2 scorecard. Stage 1 checks hash chain; Stage 2 replays MSWM; Stage 3 scores 5 dims; Stage 4 scores task/privacy/security; Stage 5 diagnostics.

- [ ] Step 1: Write E2E test with a recorded cassette fixture.
- [ ] Step 2: Update runner.
- [ ] Step 3: Pass.
- [ ] Step 4: Commit: `feat(arena): EvalRunner v2`.

### Task F6: Cassette replay mode

**Files:**
- Create: `gateway/replay.py`
- Test: `tests/gateway/test_replay.py`

**Acceptance:** `ReplayDriver(cassette_path, gt_bundle).run()` produces action log + MSWM trace identical to what a live run would have produced, without touching an LLM.

- [ ] Steps 1-5: TDD, commit: `feat(arena): cassette replay driver`.

### Task F7: `LeakDetector` reads from gateway log

**Files:**
- Modify: `clawsocialarena/eval/leak_detector.py`
- Test: `tests/eval/test_leak_detector_v2.py`

- [ ] Steps 1-5: TDD, commit: `feat(arena): leak detector reads gateway log`.

### Task F8: Update vanilla-AA baseline for v2 logs

**Files:**
- Modify: `clawsocialarena/baselines/vanilla_aa.py`

- [ ] Steps 1-5: TDD, commit: `refactor(arena): vanilla-AA baseline consumes v2 logs`.

### Task F9: Update prompt-ladder + DLP baselines

**Files:**
- Modify: `clawsocialarena/baselines/prompt_ladder.py`, `baselines/dlp_external.py`

- [ ] Steps 1-5: TDD, commit: `refactor(arena): update remaining baselines for v2`.

### Task F10: Tag `phase-F-complete`

- [ ] Full suite green (expect 200+ tests).
- [ ] Tag: `git tag phase-F-complete`.

---

## Phase G: Batch runner + cassette + cost tracking

Delivers: `scripts/run_grid.py` runs the compute-budget configurations from spec §5.4 (live cells + replay cells + ablations). Resumable. Cost and token counts aggregated into `results/v1.0.0/cost.csv`.

### Task G1: Grid config schema

**Files:**
- Create: `configs/main_table.yaml`, `configs/ablations.yaml`
- Test: `tests/scripts/test_grid_config.py`

**Acceptance:** YAML lists `(scenario_id, condition, model, privacy_level, seed, live_or_replay)` tuples.

- [ ] Step 1-5: TDD, commit: `feat(arena): grid config schema`.

### Task G2: `run_grid.py` — live mode

**Files:**
- Create: `scripts/run_grid.py`

**Acceptance:** Given a config, for each row: brings up compose; runs scenario; tears down; persists `run_scorecard.json` under `results/v1.0.0/<model>/<condition>/<scenario_id>/`. Tracks `cost.csv`. Resumable: skips rows whose scorecard already exists.

- [ ] Step 1: Smoke test with 5 rows × mock LLM, confirm pipeline works.
- [ ] Step 2: Implement.
- [ ] Step 3: Commit: `feat(arena): run_grid.py live mode`.

### Task G3: `run_grid.py` — replay mode

**Files:**
- Modify: `scripts/run_grid.py`

**Acceptance:** For rows marked `replay`, load a recorded cassette (recorded from the matching scenario under the reference-model live run), drive `ReplayDriver`, produce a scorecard.

- [ ] Step 1-3: Commit: `feat(arena): run_grid.py replay mode`.

### Task G4: Cost tracking

**Files:**
- Modify: `scripts/run_grid.py`, `clawsocialarena/eval/scorecard.py`

**Acceptance:** Each `llm_call` records `input_tokens`, `output_tokens`, `cached_tokens`. `run_grid.py` writes `cost.csv` with provider $ cost per run from a per-provider rate table.

- [ ] Steps 1-3: Commit: `feat(arena): cost tracking`.

### Task G5: Pilot smoke (30 real-LLM Bedrock runs)

**Files:**
- Create: `docs/pilot-report-2026-04.md` (write after running)

**Acceptance:** Before committing to full budget, run ~30 live Bedrock runs; compare $ to estimate. Report goes to docs/.

- [ ] Step 1: Configure Bedrock credentials.
- [ ] Step 2: Select 30 scenarios × 1 condition × 1 model.
- [ ] Step 3: Run.
- [ ] Step 4: Analyze actual cost and wall-clock per run; extrapolate.
- [ ] Step 5: Commit pilot report.

### Task G6: Full live main table

**Acceptance:** 600 live runs for the main table. Each persists a scorecard. `cost.csv` shows cumulative $ under budget.

- [ ] Step 1: Run `scripts/run_grid.py --config configs/main_table.yaml --out results/v1.0.0 --parallel 4`.
- [ ] Step 2: Monitor; resume on failures.
- [ ] Step 3: Commit the compressed results tarball.

### Task G7: Run remaining buckets (replay + ablations + seed + episode-graph)

- [ ] Step 1-N: Run each bucket, persist scorecards, commit.

### Task G8: Tag `phase-G-complete`

- [ ] Confirm all ~10,200 scorecards exist.
- [ ] Confirm no scorecard has `chain_integrity_primary == False`.
- [ ] Tag: `git tag phase-G-complete`.

---

## Phase H: Analysis, figures, pre-registration

Delivers: paper tables + figures + pre-registration reconciliation + reproducibility bundle.

### Task H1: Aggregator ingests v2 scorecards

**Files:**
- Modify: `clawsocialarena/analysis/aggregator.py`
- Test: `tests/analysis/test_aggregator_v2.py`

- [ ] Steps 1-5: TDD, commit: `feat(arena): aggregator ingests v2 scorecards`.

### Task H2: Tables — headline, model, rewrite

**Files:**
- Modify: `clawsocialarena/analysis/tables.py`

**Acceptance:** Produces markdown + LaTeX tables for headline (condition x category x metric), model comparison (model x SAF dim), rewrite quality (TSR delta). Live-vs-replay flag in every row.

- [ ] Steps 1-5: Commit: `feat(arena): v2 analysis tables`.

### Task H3: Figures

**Files:**
- Create: `clawsocialarena/analysis/figures.py`

**Acceptance:** Four matplotlib figures written as PDFs under `paper/figures/`: `ablation_figure.pdf`, `rewrite_quality_figure.pdf`, `audit_challenge_cases_figure.pdf`, `sensitivity_figure.pdf`. Plus episode-graph appendix figure.

- [ ] Steps 1-5: Commit: `feat(arena): paper figures`.

### Task H4: Statistical tests

**Files:**
- Modify: `clawsocialarena/analysis/stats.py`

**Acceptance:** Wilcoxon paired tests for condition deltas; Kruskal-Wallis across categories; Bonferroni correction where applicable.

- [ ] Steps 1-5: Commit: `feat(arena): v2 statistical tests`.

### Task H5: Pre-registration reconciliation

**Files:**
- Modify: `clawsocialarena/analysis/prereg_check.py`

**Acceptance:** Evaluates H1-H5 against real scorecards. Report written to `results/v1.0.0/prereg_reconciliation.md`.

- [ ] Steps 1-5: Commit: `feat(arena): prereg reconciliation v2`.

### Task H6: Sensitivity analysis

**Files:**
- Modify: `clawsocialarena/analysis/stats.py`

**Acceptance:** Sensitivity sweep of SAF thresholds +/- 0.05; binary pass-rate table.

- [ ] Steps 1-5: Commit: `feat(arena): SAF sensitivity analysis`.

### Task H7: Reproducibility bundle

**Files:**
- Create: `scripts/make_repro_bundle.py`

**Acceptance:** Produces a <= 2 GB tarball containing benchmark scenarios + results + lockfile + design + prereg + one-command `replay.sh`.

- [ ] Steps 1-5: Commit: `feat(arena): repro bundle`.

### Task H8: Tag `v1.0.0`

- [ ] Final suite green.
- [ ] Tag: `git tag v1.0.0`.
- [ ] Produce `CHANGELOG.md`.
- [ ] Commit: `chore(arena): v1.0.0 release`.

---

## Self-review summary

**Spec coverage.** Every spec section maps to a task:
- §2 runtime -> Phase A, Phase B module migration, Phase C MSWM.
- §3 SAF -> Phase C (MSWM) + Phase F (existing scorers) + Phase I (Identity-Governance scorer).
- §4 benchmark -> Phase D (generator) + Phase I (governance axis) + Phase E (content).
- §5 experiments -> Phase G (batch runner).
- §6 eval pipeline -> Phase F + Phase H (analysis).
- §7 threat model -> enforced across Phase A (compose egress invariant), Phase B (delete v1 surfaces), Phase F (Stage-1 integrity check).
- Appendix A migration -> Phase B.

**Placeholder scan.** No unresolved placeholder markers. The Phase E worktree import, Phase I.5 resource layer, and task-success calibration layer are explicit blocking phases before final generation. Phase E's LLM-assisted instantiation path now targets the 680-variant balanced difficulty pilot first; deterministic scaffold generation is only a schema/readiness path, not the final benchmark construction claim.

**Type consistency.** `Session`, `MSWM`, `GatewayState`, `ActionRecord`, `GTBundle`, `ComposeSpec`, `McpToolSpec`, `PersonaRef`, and the Phase I governance models are defined once (in `gateway/session.py`, `audit/mswm.py`, `types.py`, `scenario/models.py`) and referenced consistently. `LiveOrReplay = Literal["live", "replay"]` is defined in `types.py` and used in the scorecard and grid config.

Ready for execution.

---

## Execution choice

Plan complete and saved to `docs/superpowers/plans/2026-04-17-clawsocialarena-v2.md`. Two execution options:

1. **Subagent-Driven (recommended).** A fresh subagent per task; the orchestrator reviews between tasks; fast iteration; safe to pause between phases.
2. **Inline Execution.** Execute tasks in the current session using executing-plans; batch execution with checkpoints for review.

Which approach do you want?
