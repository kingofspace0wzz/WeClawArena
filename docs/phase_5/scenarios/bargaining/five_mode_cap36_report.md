# MARBLE Bargaining Five-Mode Cap-36 LLM-ASR Report

**Run date:** 2026-05-16
**Run directory:** `benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_llm_asr_20260516`
**Scenario store:** `benchmark/scenarios/v2.0.0`
**Agent model:** `gpt-4.1-mini`
**Judge model:** `gpt-5.2`
**Turn cap:** `36`

This is the current bargaining attack report. Bargaining ASR is reported with the LLM judge only. The older deterministic attack-success fields remain in raw rows as deprecated diagnostics and are not reported here as ASR.

**Governance note:** this 120-row report used the earlier governance payload. The active governance attack vector is now the v5 approval-policy-bypass playbook. Its governance-only rerun is reported in [governance_v5_cap36_llm_asr_report.md](governance_v5_cap36_llm_asr_report.md).

## Batch Summary

| Metric | Value |
|---|---:|
| Rows | `120` |
| Base tasks | `24` |
| Rows per mode | `24` |
| Raw TSR | `51/120 = 0.4250` |
| Baseline TSR | `10/24 = 0.4167` |
| Attacked-row TSR | `41/96 = 0.4271` |
| Turn-cap hits | `65/120 = 0.5417` |
| Rows failed before scorecard | `4/120 = 0.0333` |
| Rows with error strings | `69/120 = 0.5750` |
| Mean turn count | `28.4083` |
| Simulation tokens | `18,625,212` |

Error strings were dominated by turn-cap exits: `65/69`. The remaining four interface errors were `tool_calls[0].arguments must be an object` (`2` rows), `unknown recipient_id from agent reply: 'helio_projects_authorized_closer'` (`1` row), and `unknown recipient_id from agent reply: 'vesta_procurement_authorized_closer'` (`1` row).

## Mode Metrics

| Mode | Rows | Raw TSR | Cap hits | Error strings |
|---|---:|---:|---:|---:|
| `no_attacker` | 24 | `10/24 = 0.4167` | `13/24 = 0.5417` | `14/24 = 0.5833` |
| `collaboration` | 24 | `7/24 = 0.2917` | `17/24 = 0.7083` | `17/24 = 0.7083` |
| `security` | 24 | `7/24 = 0.2917` | `17/24 = 0.7083` | `17/24 = 0.7083` |
| `privacy` | 24 | `15/24 = 0.6250` | `8/24 = 0.3333` | `9/24 = 0.3750` |
| `governance` | 24 | `12/24 = 0.5000` | `10/24 = 0.4167` | `12/24 = 0.5000` |

## Primary LLM-ASR

Headline ASR excludes `no_attacker` rows. For each attack row, the primary axis is the row's `attack_mode`.

| Attack mode | Judge positives | Denominator | LLM-ASR |
|---|---:|---:|---:|
| `collaboration` | 1 | 24 | `0.0417` |
| `security` | 24 | 24 | `1.0000` |
| `privacy` | 3 | 24 | `0.1250` |
| `governance` | 0 | 24 | `0.0000` |

The judge scored all `120` rows with `0` judge errors. The judge pass took `251.91s` and used `1,166,637` total tokens (`1,099,361` prompt tokens, `67,276` completion tokens).

## Diagnostic Cross-Axis Positives

The judge also scores all four axes for every row. These all-row positives are diagnostic only, not headline ASR.

| Axis | Judge positives | Denominator | Rate |
|---|---:|---:|---:|
| `security` | 27 | 120 | `0.2250` |
| `privacy` | 3 | 120 | `0.0250` |
| `collaboration` | 1 | 120 | `0.0083` |
| `governance` | 0 | 120 | `0.0000` |

## Interpretation

This rerun used the refreshed bargaining contexts, so numeric stress fields and delegated-close fields were available to the materialized variants. The security attacks now show high LLM-ASR: `24/24` security-mode rows were judged as final harm with a clear causal link to the attack. Privacy has a smaller but nonzero signal at `3/24`. Collaboration remains low under the semantic judge because most failures were ordinary cap-hit or task-failure outcomes rather than clearly attack-caused final harm. Governance remains at `0/24` for the earlier governance payload used inside this 120-row run. The follow-up v5 governance rerun targets the real approval path and scored `24/24` primary-axis LLM-ASR.

Operationally, the run is still hard for the simulation loop. Turn-cap hits remain high at `65/120`, and four rows failed before scorecard due to benchmark-interface issues rather than task semantics. These should be analyzed separately from ASR because the LLM judge can still score exposure and harm from the recorded evidence packet, but task success and robustness are affected.

## Artifacts

| Artifact | Path |
|---|---|
| Merged simulation rows | `benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_llm_asr_20260516/BARGAINING_STRESS_RESULTS.jsonl` |
| Simulation summary JSON | `benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_llm_asr_20260516/BARGAINING_STRESS_REPORT.json` |
| LLM-ASR rows | `benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_llm_asr_20260516/BARGAINING_LLM_ASR_GPT52.jsonl` |
| LLM-ASR summary JSON | `benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_llm_asr_20260516/BARGAINING_LLM_ASR_REPORT.json` |
| Store refresh report | `benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_llm_asr_20260516/BARGAINING_STORE_REFRESH_REPORT.json` |
| Shard-0 partial backup | `benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_llm_asr_20260516/BARGAINING_STRESS_RESULTS_SHARD0_PARTIAL.jsonl` |
