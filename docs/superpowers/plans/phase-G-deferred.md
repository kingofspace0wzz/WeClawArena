# Phase G deferred tasks (G5-G8)

> **Status note as of 2026-05-06:** This is a historical Phase G resume note.
> It still describes the run-grid infrastructure, but branch, Docker, and
> batch status must be checked against `docs/project_status.md` before use.

> **Update as of 2026-05-05:** The earlier 150-scenario / 4,440-run budget
> and the later 550-variant scaffold target are obsolete for release
> planning. The 550-variant tree is a pre-calibration scaffold. The active
> next target is the 680-variant balanced difficulty pilot: 630 main matched
> variants, 25 hard-verification variants, 20 episode-graph variants, and 5
> audit challenge cases. If the pilot validates the tier rubric, the
> recommended release grid is 1100 total variants with 1050 main matched
> variants. Full-grid run counts and budget should be recomputed from the
> selected target and observed smoke-run costs; see
> `docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md` §5.5.

Phase G lands the infrastructure needed to run the ClawSocialArena v2
compute budget: grid config schema, batch runner with live and replay
modes, cassette enrichment, and cost tracking. The actual LLM-API runs
and the final phase-G tag are deferred pending budget approval and
Docker availability in the target runtime.

This note enumerates the remaining Tasks G5, G6, G7, and G8 and sets
out step-by-step instructions so Prince can resume them without
re-reading the plan.

## Status at the time this note was written

- Branch: ``v2-refactor``
- Last tag: ``phase-G-infrastructure-complete``
- Test counts: 420 passed + 2 skipped (Python); 29 passed (TypeScript)
- Docker: not installed on the current workstation
- LLM credentials: not configured on the current workstation

## What is already in place

- ``configs/main_table.yaml`` and ``configs/ablations.yaml`` carry
  smoke-sized samples with the budget numbers from spec §5.4 in the
  header comments.
- ``clawsocialarena/experiments/grid_config.py`` loads and validates
  grid YAMLs into typed ``GridRow`` instances.
- ``scripts/run_grid.py`` walks a grid, dispatches replay rows against
  :class:`ReplayDriver` + :class:`EvalRunner`, stubs live rows with a
  ``status: "pending"`` scorecard, and aggregates per-row dollar cost
  into ``<out>/cost.csv``.
- ``clawsocialarena/experiments/rates.yaml`` holds the USD-per-million
  rate schedule for the spec §5.2 model panel.
- The gateway's :class:`CassetteRecorder` writes an enriched JSON line
  per action so live-recorded cassettes can be replayed without an
  external ``agent_resolver``.

## What is deferred and how to resume

### G5 — Pilot smoke (30 real-LLM Bedrock runs)

Goal: sanity-check the live path against real Bedrock pricing before
committing to the full budget.

1. Configure Bedrock credentials:
   - Set ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` /
     ``AWS_REGION`` (or use an IAM role).
   - Run ``aws sts get-caller-identity`` to confirm.
   - Ensure the IAM principal has ``bedrock:InvokeModel`` on the
     target model ARN.
2. Install and start Docker Desktop (or a native ``dockerd``). Verify
   with ``docker info``.
3. Materialize a 30-row pilot grid:
   - ``python scripts/materialize_grid.py --strata pilot`` (script to
     be written; see §5.4 pilot selection). For now, a hand-edited
     ``configs/pilot.yaml`` with 30 rows (30 scenarios × 1 condition ×
     1 model) is acceptable.
4. Run: ``python scripts/run_grid.py --config configs/pilot.yaml --out
   results/v1.0.0 --no-dry-run``.
5. After completion, open ``results/v1.0.0/cost.csv`` and compute the
   mean cost per row. Multiply by the selected pilot or release run count
   to extrapolate.
6. Write ``docs/pilot-report-2026-04.md`` with: number of runs,
   total tokens, total spend, extrapolated full-budget spend, wall-clock
   per run, noteworthy failures, and go/no-go on the full budget.
7. Commit: ``feat(arena): phase-G5 pilot report``.

### G6 — Full live main table

Goal: live runs for the headline main table, using the current benchmark
target rather than the obsolete 500-main-variant scaffold.

1. Confirm the G5 pilot is within budget and no blocking failures.
2. Materialize the full main-table grid for the selected target. The next
   pilot has 630 matched variants; the release grid has 1050 matched
   variants if the pilot passes calibration.
3. Run: ``python scripts/run_grid.py --config configs/main_table.yaml
   --out results/v1.0.0 --parallel 4 --no-dry-run``. The ``--parallel``
   knob is currently a placeholder; wire it to a ``concurrent.futures``
   pool before running or run serially.
4. Monitor ``results/v1.0.0/cost.csv`` tail for anomaly detection
   (sudden jump in ``input_tokens`` per row indicates a prompt-cache
   regression).
5. On failure: the runner is resumable. Rerun the same command; rows
   whose scorecards already hold ``status != "pending"`` are skipped.
6. On full completion: ``tar czf results/v1.0.0-main-table.tgz
   results/v1.0.0`` and ``git add`` + commit the tarball.

### G7 — Remaining buckets

Goal: replay + ablations + seed-variance + episode-graph + hard / audit
challenge buckets according to the selected calibrated run budget.

1. Materialize each bucket's config against the appropriate cassettes:
   ``configs/ablations.yaml`` already carries the template.
2. Run each bucket with ``scripts/run_grid.py``, committing each output
   tarball separately so review is incremental.
3. Spot-check the seed-variance bucket: the CV of SAF overall across
   seeds for the same ``(scenario, condition, model)`` should be
   <0.1; anything above flags a non-determinism bug before Phase H.

### G8 — Tag ``phase-G-complete``

1. Confirm all configured scorecards exist under ``results/v1.0.0/``.
2. Confirm no scorecard has ``chain_integrity_primary == False``:
   ``python scripts/audit_scorecards.py --out results/v1.0.0`` (script
   to write as part of G8).
3. Confirm ``cost.csv`` total spend is within the $4K-$10K envelope
   from spec §5.4.
4. ``git tag phase-G-complete`` and push.

## Why we paused here

Three reasons:

1. Docker is not available on the current workstation; live-mode
   dispatch would crash at ``docker compose up`` without first running
   the G5 pilot anywhere. The batch runner's ``--no-dry-run`` path
   already handles the ``DockerUnavailable`` case gracefully, but the
   pilot itself needs Docker.
2. LLM API credentials are not configured. Running even a 30-row pilot
   against Bedrock without IAM credentials is a no-op.
3. The Phase H analysis scripts (aggregator, tables, figures, stats,
   prereg reconciler) are the natural next milestone and can proceed
   against synthetic scorecards while G5-G8 wait for the budget.

Resuming G5-G8 is a matter of completing the steps above; no code
redesign is required. The infrastructure produced under
``phase-G-infrastructure-complete`` is the final shape.
