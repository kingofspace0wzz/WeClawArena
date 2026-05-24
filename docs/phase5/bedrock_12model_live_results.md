# Bedrock Sweep Live Results

Last updated: `2026-05-24 13:35:08 UTC`

Notes:

- Progress counts use main rows plus `_patch_results`, keyed by `variant_id`.
- Non-SWE TSR is `task_success is True / completed rows`.
- SWE-bench TSR uses true harness results when available. Pending strict harness rows are not counted as true TSR yet.
- `oss_20b` is intentionally stopped and excluded from future resume runs.
- Paused models for new runs: `deepseek_r1, minimax_m2, minimax_m25, oss_120b, oss_20b`.

## Overall Progress

| model | bargaining | swebench_workspace | travel | total | left |
|---|---:|---:|---:|---:|---:|
| opus_41_id | 120/120 | 111/250 | 0/100 | 231/470 | 239 |
| opus_47_id | 120/120 | 250/250 | 100/100 | 470/470 | 0 |
| deepseek_r1 | 120/120 | 250/250 | 100/100 | 470/470 | 0 |
| deepseek_v32 | 120/120 | 250/250 | 100/100 | 470/470 | 0 |
| kimi_k25 | 120/120 | 250/250 | 100/100 | 470/470 | 0 |
| kimi_k2_think | 120/120 | 250/250 | 100/100 | 470/470 | 0 |
| minimax_m2 | 120/120 | 250/250 | 100/100 | 470/470 | 0 |
| minimax_m25 | 120/120 | 250/250 | 100/100 | 470/470 | 0 |
| oss_120b | 120/120 | 250/250 | 100/100 | 470/470 | 0 |
| oss_20b | 94/120 | 0/250 | 0/100 | 94/470 | 376 |
| qwen3_235b | 120/120 | 250/250 | 0/100 | 370/470 | 100 |
| qwen3_32b | 120/120 | 250/250 | 100/100 | 470/470 | 0 |

Total: `4925/5640`, left `715`.

## TSR By Model And Domain

| model | bargaining TSR | swebench_workspace true TSR | travel TSR |
|---|---:|---:|---:|
| opus_41_id | 27/120 (22.5%) | 0/0 (n/a) | 0/0 (n/a) |
| opus_47_id | 76/120 (63.3%) | 68/150 (45.3%) | 83/100 (83.0%) |
| deepseek_r1 | 3/120 (2.5%) | 0/250 (0.0%) | 11/100 (11.0%) |
| deepseek_v32 | 24/120 (20.0%) | 26/150 (17.3%) | 26/100 (26.0%) |
| kimi_k25 | 57/120 (47.5%) | 30/200 (15.0%) | 58/100 (58.0%) |
| kimi_k2_think | 23/120 (19.2%) | 15/250 (6.0%) | 11/100 (11.0%) |
| minimax_m2 | 4/120 (3.3%) | 0/50 (0.0%) | 2/100 (2.0%) |
| minimax_m25 | 5/120 (4.2%) | 0/50 (0.0%) | 1/100 (1.0%) |
| oss_120b | 29/120 (24.2%) | 0/50 (0.0%) | 22/100 (22.0%) |
| oss_20b | 9/94 (9.6%) | 0/0 (n/a) | 0/0 (n/a) |
| qwen3_235b | 31/120 (25.8%) | 1/50 (2.0%) | 0/0 (n/a) |
| qwen3_32b | 14/120 (11.7%) | 4/250 (1.6%) | 20/100 (20.0%) |

## TSR By Model, Domain, And Attack Mode

### opus_41_id

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 6/24 (25.0%) | 4/24 (16.7%) | 4/24 (16.7%) | 5/24 (20.8%) | 8/24 (33.3%) |
| swebench_workspace | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) |
| travel | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) |

### opus_47_id

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 11/24 (45.8%) | 17/24 (70.8%) | 16/24 (66.7%) | 16/24 (66.7%) | 16/24 (66.7%) |
| swebench_workspace | 26/50 (52.0%) | 29/50 (58.0%) | 13/50 (26.0%) | 0/0 (n/a) | 0/0 (n/a) |
| travel | 16/20 (80.0%) | 17/20 (85.0%) | 18/20 (90.0%) | 17/20 (85.0%) | 15/20 (75.0%) |

### deepseek_r1

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 1/24 (4.2%) | 1/24 (4.2%) | 0/24 (0.0%) | 1/24 (4.2%) | 0/24 (0.0%) |
| swebench_workspace | 0/50 (0.0%) | 0/50 (0.0%) | 0/50 (0.0%) | 0/50 (0.0%) | 0/50 (0.0%) |
| travel | 1/20 (5.0%) | 3/20 (15.0%) | 2/20 (10.0%) | 4/20 (20.0%) | 1/20 (5.0%) |

### deepseek_v32

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 6/24 (25.0%) | 2/24 (8.3%) | 6/24 (25.0%) | 5/24 (20.8%) | 5/24 (20.8%) |
| swebench_workspace | 13/50 (26.0%) | 9/50 (18.0%) | 4/50 (8.0%) | 0/0 (n/a) | 0/0 (n/a) |
| travel | 8/20 (40.0%) | 2/20 (10.0%) | 4/20 (20.0%) | 4/20 (20.0%) | 8/20 (40.0%) |

### kimi_k25

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 14/24 (58.3%) | 10/24 (41.7%) | 9/24 (37.5%) | 13/24 (54.2%) | 11/24 (45.8%) |
| swebench_workspace | 15/50 (30.0%) | 6/50 (12.0%) | 4/50 (8.0%) | 5/50 (10.0%) | 0/0 (n/a) |
| travel | 12/20 (60.0%) | 10/20 (50.0%) | 9/20 (45.0%) | 13/20 (65.0%) | 14/20 (70.0%) |

### kimi_k2_think

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 4/24 (16.7%) | 6/24 (25.0%) | 6/24 (25.0%) | 4/24 (16.7%) | 3/24 (12.5%) |
| swebench_workspace | 6/50 (12.0%) | 4/50 (8.0%) | 2/50 (4.0%) | 1/50 (2.0%) | 2/50 (4.0%) |
| travel | 3/20 (15.0%) | 1/20 (5.0%) | 0/20 (0.0%) | 3/20 (15.0%) | 4/20 (20.0%) |

### minimax_m2

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 0/24 (0.0%) | 0/24 (0.0%) | 0/24 (0.0%) | 2/24 (8.3%) | 2/24 (8.3%) |
| swebench_workspace | 0/50 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) |
| travel | 1/20 (5.0%) | 0/20 (0.0%) | 1/20 (5.0%) | 0/20 (0.0%) | 0/20 (0.0%) |

### minimax_m25

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 1/24 (4.2%) | 1/24 (4.2%) | 0/24 (0.0%) | 1/24 (4.2%) | 2/24 (8.3%) |
| swebench_workspace | 0/50 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) |
| travel | 0/20 (0.0%) | 0/20 (0.0%) | 1/20 (5.0%) | 0/20 (0.0%) | 0/20 (0.0%) |

### oss_120b

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 6/24 (25.0%) | 4/24 (16.7%) | 7/24 (29.2%) | 7/24 (29.2%) | 5/24 (20.8%) |
| swebench_workspace | 0/50 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) |
| travel | 3/20 (15.0%) | 5/20 (25.0%) | 6/20 (30.0%) | 3/20 (15.0%) | 5/20 (25.0%) |

### oss_20b

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 3/19 (15.8%) | 1/19 (5.3%) | 2/18 (11.1%) | 3/19 (15.8%) | 0/19 (0.0%) |
| swebench_workspace | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) |
| travel | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) |

### qwen3_235b

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 9/24 (37.5%) | 4/24 (16.7%) | 7/24 (29.2%) | 9/24 (37.5%) | 2/24 (8.3%) |
| swebench_workspace | 1/50 (2.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) |
| travel | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) |

### qwen3_32b

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| bargaining | 6/24 (25.0%) | 2/24 (8.3%) | 1/24 (4.2%) | 5/24 (20.8%) | 0/24 (0.0%) |
| swebench_workspace | 2/50 (4.0%) | 0/50 (0.0%) | 0/50 (0.0%) | 1/50 (2.0%) | 1/50 (2.0%) |
| travel | 4/20 (20.0%) | 5/20 (25.0%) | 2/20 (10.0%) | 6/20 (30.0%) | 3/20 (15.0%) |

## SWE-bench True Harness Progress

| model | completed modes | running/started modes | predictions completed/known | true TSR so far |
|---|---:|---|---:|---:|
| opus_41_id | 0/5 (-) | - | 0/0 | 0/0 (n/a) |
| opus_47_id | 3/5 (no_attacker, collaboration, security) | privacy | 149/198 | 68/150 (45.3%) |
| deepseek_r1 | 5/5 (no_attacker, collaboration, security, privacy, governance) | - | 16/16 | 0/250 (0.0%) |
| deepseek_v32 | 3/5 (no_attacker, collaboration, security) | privacy | 122/165 | 26/150 (17.3%) |
| kimi_k25 | 4/5 (no_attacker, collaboration, security, privacy) | governance | 142/180 | 30/200 (15.0%) |
| kimi_k2_think | 5/5 (no_attacker, collaboration, security, privacy, governance) | - | 62/62 | 15/250 (6.0%) |
| minimax_m2 | 1/5 (no_attacker) | - | 0/0 | 0/50 (0.0%) |
| minimax_m25 | 1/5 (no_attacker) | - | 0/0 | 0/50 (0.0%) |
| oss_120b | 1/5 (no_attacker) | - | 6/6 | 0/50 (0.0%) |
| oss_20b | 0/5 (-) | - | 0/0 | 0/0 (n/a) |
| qwen3_235b | 1/5 (no_attacker) | collaboration | 32/36 | 1/50 (2.0%) |
| qwen3_32b | 5/5 (no_attacker, collaboration, security, privacy, governance) | - | 109/109 | 4/250 (1.6%) |

## Supplemental gpt-4.1-mini Results

These prior rows are not part of the Bedrock 12-model totals. They are no-attacker CLAW clinical/trading runs found under `benchmark/phase5/pilot`.

| source | families | rows | definite | TSR | errors |
|---|---|---:|---:|---:|---:|
| claw_no_attacker_gpt41mini_fix_20260524_103703 | claw_clinical, claw_trading | 18 | 18 | 3/18 (16.7%) | 15 |
| claw_trading_no_attacker_gpt41mini_fix_20260524_121543 | claw_trading | 8 | 8 | 0/8 (0.0%) | 8 |
| claw_no_attacker_gpt41mini_rerun_20260523_1215 | claw_clinical, claw_trading | 18 | 18 | 0/18 (0.0%) | 18 |
| claw_no_attacker_gpt41mini_20260522 | claw_clinical, claw_trading | 18 | 18 | 0/18 (0.0%) | 18 |
