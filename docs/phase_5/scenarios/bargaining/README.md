# MARBLE Bargaining Scenario Reports

This folder keeps active reports for the owned-ecosystem MARBLE bargaining redesign. The current target is 24 distinct base scenarios, not paired clones: 12 `CU-A` tasks and 12 `CM-A` tasks.

| Cell | Task | Base ID | Report | Resource profile |
|---|---:|---|---|---|
| `CU-A` | `t0` | `CU-A-marble_bargaining__t0` | [cu_a/t0_smoke.md](cu_a/t0_smoke.md) | `owned_ecosystem_procurement` |
| `CU-A` | `t1` | `CU-A-marble_bargaining__t1` | [cu_a/t1_inventory_allocation.md](cu_a/t1_inventory_allocation.md) | `owned_ecosystem_inventory_allocation` |
| `CU-A` | `t2` | `CU-A-marble_bargaining__t2` | [cu_a/t2_shipping_terms.md](cu_a/t2_shipping_terms.md) | `owned_ecosystem_shipping_terms` |
| `CU-A` | `t3` | `CU-A-marble_bargaining__t3` | [cu_a/t3_renewal_addon.md](cu_a/t3_renewal_addon.md) | `owned_ecosystem_renewal_addon` |
| `CU-A` | `t4` | `CU-A-marble_bargaining__t4` | [cu_a/t4_vendor_onboarding.md](cu_a/t4_vendor_onboarding.md) | `owned_ecosystem_vendor_onboarding` |
| `CU-A` | `t5` | `CU-A-marble_bargaining__t5` | [cu_a/t5_delegated_close.md](cu_a/t5_delegated_close.md) | `owned_ecosystem_delegated_close` |
| `CU-A` | `t6` | `CU-A-marble_bargaining__t6` | [cu_a/t6_multisite_delivery.md](cu_a/t6_multisite_delivery.md) | `owned_ecosystem_multisite_delivery_split` |
| `CU-A` | `t7` | `CU-A-marble_bargaining__t7` | [cu_a/t7_service_level.md](cu_a/t7_service_level.md) | `owned_ecosystem_service_level_terms` |
| `CU-A` | `t8` | `CU-A-marble_bargaining__t8` | [cu_a/t8_substitution.md](cu_a/t8_substitution.md) | `owned_ecosystem_substitution_terms` |
| `CU-A` | `t9` | `CU-A-marble_bargaining__t9` | [cu_a/t9_broker_mediated.md](cu_a/t9_broker_mediated.md) | `owned_ecosystem_broker_mediated` |
| `CU-A` | `t10` | `CU-A-marble_bargaining__t10` | [cu_a/t10_license_trueup.md](cu_a/t10_license_trueup.md) | `owned_ecosystem_license_trueup` |
| `CU-A` | `t11` | `CU-A-marble_bargaining__t11` | [cu_a/t11_milestone_purchase.md](cu_a/t11_milestone_purchase.md) | `owned_ecosystem_milestone_purchase` |
| `CM-A` | `t0` | `CM-A-marble_bargaining__t0` | [cm_a/t0_competitive_priority_inventory.md](cm_a/t0_competitive_priority_inventory.md) | `owned_ecosystem_competitive_priority_inventory` |
| `CM-A` | `t1` | `CM-A-marble_bargaining__t1` | [cm_a/t1_competitive_dual_sourcing.md](cm_a/t1_competitive_dual_sourcing.md) | `owned_ecosystem_competitive_dual_sourcing` |
| `CM-A` | `t2` | `CM-A-marble_bargaining__t2` | [cm_a/t2_competitive_rebate_terms.md](cm_a/t2_competitive_rebate_terms.md) | `owned_ecosystem_competitive_rebate_terms` |
| `CM-A` | `t3` | `CM-A-marble_bargaining__t3` | [cm_a/t3_competitive_expiring_quote.md](cm_a/t3_competitive_expiring_quote.md) | `owned_ecosystem_competitive_expiring_quote` |
| `CM-A` | `t4` | `CM-A-marble_bargaining__t4` | [cm_a/t4_competitive_substitute_close.md](cm_a/t4_competitive_substitute_close.md) | `owned_ecosystem_competitive_substitute_close` |
| `CM-A` | `t5` | `CM-A-marble_bargaining__t5` | [cm_a/t5_competitive_escrow.md](cm_a/t5_competitive_escrow.md) | `owned_ecosystem_competitive_escrow_purchase` |
| `CM-A` | `t6` | `CM-A-marble_bargaining__t6` | [cm_a/t6_competitive_production_slot.md](cm_a/t6_competitive_production_slot.md) | `owned_ecosystem_competitive_production_slot` |
| `CM-A` | `t7` | `CM-A-marble_bargaining__t7` | [cm_a/t7_competitive_brokered_shortage.md](cm_a/t7_competitive_brokered_shortage.md) | `owned_ecosystem_competitive_brokered_shortage` |
| `CM-A` | `t8` | `CM-A-marble_bargaining__t8` | [cm_a/t8_competitive_warranty_tradeoff.md](cm_a/t8_competitive_warranty_tradeoff.md) | `owned_ecosystem_competitive_warranty_tradeoff` |
| `CM-A` | `t9` | `CM-A-marble_bargaining__t9` | [cm_a/t9_competitive_compliance_hold.md](cm_a/t9_competitive_compliance_hold.md) | `owned_ecosystem_competitive_compliance_hold` |
| `CM-A` | `t10` | `CM-A-marble_bargaining__t10` | [cm_a/t10_competitive_renewal_uplift.md](cm_a/t10_competitive_renewal_uplift.md) | `owned_ecosystem_competitive_renewal_uplift` |
| `CM-A` | `t11` | `CM-A-marble_bargaining__t11` | [cm_a/t11_competitive_staged_milestone.md](cm_a/t11_competitive_staged_milestone.md) | `owned_ecosystem_competitive_staged_milestone` |

## Current Grid Status

- Base scenarios: `24`
- `CU-A` scenarios: `12`
- `CM-A` scenarios: `12`
- Main rows after five attack modes: `120`
- Published store: `benchmark/scenarios/v2.0.0/bargaining/` contains all 24 base bundles
- Published manifest bargaining rows: `120`
- Current no-attacker simulation status: cap-36 rerun completed on `2026-05-16` for the full 24-task grid
- No-attacker run directory: `benchmark/phase5/pilot/bargaining_owned_ecosystem_24_no_attacker_cap36_20260516`
- No-attacker rows run: `24`
- Raw no-attacker TSR: `0.6250` (`15/24`)
- Turn-cap hits: `9/24`
- Mean turn count: `25.9167`
- Simulation tokens: `3073374`
- Residual failures: `9/24`, all cap-hit rows; no `predicate_not_registered` errors remained after the `required_terms_consistent` registry fix
- Current five-mode simulation status: cap-36 LLM-ASR run completed on `2026-05-16` for all 120 bargaining rows
- Five-mode report: [five_mode_cap36_report.md](five_mode_cap36_report.md)
- Five-mode run directory: `benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_llm_asr_20260516`
- Five-mode raw TSR: `0.4250` (`51/120`)
- Five-mode baseline TSR: `0.4167` (`10/24`)
- Five-mode attacked-row TSR: `0.4271` (`41/96`)
- Five-mode ASR reporting policy: LLM-ASR only; deterministic ASR is deprecated and excluded from headline metrics
- Five-mode LLM judge status: `gpt-5.2` ASR pass completed for all `120` rows with `0` judge errors
- Five-mode primary-axis LLM-ASR: collaboration `1/24`, security `24/24`, privacy `3/24`, governance `0/24`
- Five-mode LLM judge artifact: `benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_llm_asr_20260516/BARGAINING_LLM_ASR_GPT52.jsonl`
- Five-mode LLM-ASR summary: `benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_llm_asr_20260516/BARGAINING_LLM_ASR_REPORT.json`
- Five-mode turn-cap hits: `65/120`
- Five-mode scorecard-prep failures: `4/120`, two malformed tool-call rows and two invalid authorized-closer recipients
- Current governance rerun status: v5 approval-policy-bypass run completed on `2026-05-16` for all `24` governance rows
- Governance v5 report: [governance_v5_cap36_llm_asr_report.md](governance_v5_cap36_llm_asr_report.md)
- Governance v5 run directory: `benchmark/phase5/pilot/bargaining_governance_v5_cap36_llm_asr_20260516`
- Governance v5 primary-axis LLM-ASR: governance `24/24`
- Governance v5 raw TSR: `0/24`
- Governance v5 turn-cap hits: `24/24`
- Governance v5 note: the old five-mode governance `0/24` is retained as the historical v4 delegated-identity result; the active governance playbook is now v5 approval-policy bypass

## Archives

- `archive/cell_agnostic_20260515/`: pre-24-grid owned-ecosystem reports and simulation logs for the earlier cell-agnostic `t0-t3` runs.
- `archive/shallow_marble/`: older shallow MARBLE bargaining scenario reviews.
- `archive/calibration/`: stress-calibration, turn-cap, and attack-mode reports from the shallow task era.

Use `cu_a/` and `cm_a/` for new simulation logs. Keep archived reports for audit history only.
