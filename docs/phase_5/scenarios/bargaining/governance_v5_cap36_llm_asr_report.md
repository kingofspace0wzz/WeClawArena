# MARBLE Bargaining Governance V5 Cap-36 LLM-ASR Report

**Run date:** 2026-05-16
**Run directory:** `benchmark/phase5/pilot/bargaining_governance_v5_cap36_llm_asr_20260516`
**Scenario store:** `benchmark/scenarios/v2.0.0`
**Agent model:** `gpt-4.1-mini`
**Judge model:** `gpt-5.2`
**Turn cap:** `36`

This report covers the governance-only rerun after replacing the earlier delegated-identity governance payload with the current approval-policy-bypass playbook. ASR is reported with the LLM judge only. Deterministic ASR fields remain raw diagnostics and are not headline metrics.

## Change Summary

The v5 governance playbook targets the real approval path in owned-ecosystem bargaining tasks. It sends forged approval requests, stale approval replays, policy-exception claims, wrong-term approval requests, and approval-id laundering attempts through normal benchmark surfaces. Final harm must come from agent actions such as `issue_purchase_approval`, `record_seller_acceptance`, or `record_purchase_order`.

The run also refreshed the bargaining store so each task uses the real finance approver agent as the approval delegate when there is no explicit closer agent.

## Batch Summary

| Metric | Value |
|---|---:|
| Rows | `24` |
| `CU-A` rows | `12` |
| `CM-A` rows | `12` |
| Raw TSR | `0/24 = 0.0000` |
| Turn-cap hits | `24/24 = 1.0000` |
| Rows with error strings | `24/24 = 1.0000` |
| Mean turn count | `39.0000` |
| Judge rows scored | `24/24` |
| Judge errors | `0/24` |
| Primary governance LLM-ASR | `24/24 = 1.0000` |

Every simulation row exited with `scenario did not reach done=true within max_turns`. This means task completion remains unresolved for this rerun, even though the judge found attack-caused approval-policy-bypass evidence in all traces.

## LLM-ASR

Headline ASR for this rerun is the governance axis only.

| Attack mode | Judge positives | Denominator | LLM-ASR |
|---|---:|---:|---:|
| `governance` | 24 | 24 | `1.0000` |

The judge pass took `57.19s` and used `274,338` total tokens (`258,897` prompt tokens, `15,441` completion tokens).

## Diagnostic Cross-Axis Positives

The judge also scores all four axes for every row. These positives are diagnostic only.

| Axis | Judge positives | Denominator | Rate |
|---|---:|---:|---:|
| `governance` | 24 | 24 | `1.0000` |
| `security` | 23 | 24 | `0.9583` |
| `collaboration` | 4 | 24 | `0.1667` |
| `privacy` | 0 | 24 | `0.0000` |

## Interpretation

The governance attack vector is now active against the owned-ecosystem approval workflow. The judge found clear approval-policy-bypass evidence in every row, usually through an approver issuing a forged or mismatched approval and later close artifacts using that approval id.

The tradeoff is that all 24 rows hit the cap. This rerun is useful for ASR validation, but not for healthy-task completion analysis. The next bargaining pass should separate the question of attack strength from the question of cap-36 completion reliability.

## Artifacts

| Artifact | Path |
|---|---|
| Merged simulation rows | `benchmark/phase5/pilot/bargaining_governance_v5_cap36_llm_asr_20260516/BARGAINING_STRESS_RESULTS.jsonl` |
| Simulation summary JSON | `benchmark/phase5/pilot/bargaining_governance_v5_cap36_llm_asr_20260516/BARGAINING_STRESS_REPORT.json` |
| LLM-ASR rows | `benchmark/phase5/pilot/bargaining_governance_v5_cap36_llm_asr_20260516/BARGAINING_GOVERNANCE_V5_LLM_ASR_GPT52.jsonl` |
| LLM-ASR summary JSON | `benchmark/phase5/pilot/bargaining_governance_v5_cap36_llm_asr_20260516/BARGAINING_GOVERNANCE_V5_LLM_ASR_REPORT.json` |
| Store refresh report | `benchmark/phase5/pilot/bargaining_governance_v5_cap36_llm_asr_20260516/BARGAINING_STORE_REFRESH_REPORT.json` |
| Shard outputs | `benchmark/phase5/pilot/bargaining_governance_v5_cap36_llm_asr_20260516/shards/` |
