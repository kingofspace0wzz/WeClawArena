<!-- CLAW_BEDROCK_SWEEP_START -->
## CLaw Clinical/Trading Bedrock Sweep

Last updated: `2026-05-25 02:05:59 UTC`

Root: `benchmark/phase5/pilot/claw_bedrock_8model_20260524_140017`

Scope: active, uncommented Bedrock models from `.env`; domains `claw_clinical` and `claw_trading`; modes `no_attacker`, `collaboration`, `security`, `privacy`, and `governance`.

Commented `.env` model entries are treated as deprecated and are not launched.

### CLaw Progress

| model | clinical | trading | total | left | errors | turn caps |
|---|---:|---:|---:|---:|---:|---:|
| deepseek_v32 | 50/50 | 40/40 | 90/90 | 0 | 62 | 6 |
| kimi_k25 | 50/50 | 40/40 | 90/90 | 0 | 59 | 4 |
| kimi_k2_think | 50/50 | 40/40 | 90/90 | 0 | 65 | 2 |
| opus_41_id | 50/50 | 40/40 | 90/90 | 0 | 61 | 0 |
| opus_47_id | 50/50 | 40/40 | 90/90 | 0 | 60 | 6 |
| qwen3_235b | 50/50 | 40/40 | 90/90 | 0 | 61 | 7 |
| qwen3_32b | 50/50 | 40/40 | 90/90 | 0 | 62 | 6 |
| sonnet_45_id | 50/50 | 40/40 | 90/90 | 0 | 56 | 2 |

CLaw total: `720/720`, left `0`.

### CLaw TSR By Model And Domain

| model | clinical TSR | trading TSR | combined TSR |
|---|---:|---:|---:|
| deepseek_v32 | 20/50 (40.0%) | 8/40 (20.0%) | 28/90 (31.1%) |
| kimi_k25 | 20/50 (40.0%) | 11/40 (27.5%) | 31/90 (34.4%) |
| kimi_k2_think | 13/50 (26.0%) | 12/40 (30.0%) | 25/90 (27.8%) |
| opus_41_id | 19/50 (38.0%) | 10/40 (25.0%) | 29/90 (32.2%) |
| opus_47_id | 18/50 (36.0%) | 12/40 (30.0%) | 30/90 (33.3%) |
| qwen3_235b | 17/50 (34.0%) | 12/40 (30.0%) | 29/90 (32.2%) |
| qwen3_32b | 14/50 (28.0%) | 14/40 (35.0%) | 28/90 (31.1%) |
| sonnet_45_id | 20/50 (40.0%) | 14/40 (35.0%) | 34/90 (37.8%) |

### CLaw TSR By Model, Domain, And Attack Mode

#### deepseek_v32

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 10/10 (100.0%) | 10/10 (100.0%) | 0/10 (0.0%) | 0/10 (0.0%) | 0/10 (0.0%) |
| claw_trading | 5/8 (62.5%) | 3/8 (37.5%) | 0/8 (0.0%) | 0/8 (0.0%) | 0/8 (0.0%) |

#### kimi_k25

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 10/10 (100.0%) | 10/10 (100.0%) | 0/10 (0.0%) | 0/10 (0.0%) | 0/10 (0.0%) |
| claw_trading | 6/8 (75.0%) | 5/8 (62.5%) | 0/8 (0.0%) | 0/8 (0.0%) | 0/8 (0.0%) |

#### kimi_k2_think

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 5/10 (50.0%) | 8/10 (80.0%) | 0/10 (0.0%) | 0/10 (0.0%) | 0/10 (0.0%) |
| claw_trading | 6/8 (75.0%) | 6/8 (75.0%) | 0/8 (0.0%) | 0/8 (0.0%) | 0/8 (0.0%) |

#### opus_41_id

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 9/10 (90.0%) | 10/10 (100.0%) | 0/10 (0.0%) | 0/10 (0.0%) | 0/10 (0.0%) |
| claw_trading | 6/8 (75.0%) | 4/8 (50.0%) | 0/8 (0.0%) | 0/8 (0.0%) | 0/8 (0.0%) |

#### opus_47_id

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 9/10 (90.0%) | 9/10 (90.0%) | 0/10 (0.0%) | 0/10 (0.0%) | 0/10 (0.0%) |
| claw_trading | 7/8 (87.5%) | 5/8 (62.5%) | 0/8 (0.0%) | 0/8 (0.0%) | 0/8 (0.0%) |

#### qwen3_235b

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 7/10 (70.0%) | 10/10 (100.0%) | 0/10 (0.0%) | 0/10 (0.0%) | 0/10 (0.0%) |
| claw_trading | 7/8 (87.5%) | 5/8 (62.5%) | 0/8 (0.0%) | 0/8 (0.0%) | 0/8 (0.0%) |

#### qwen3_32b

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 7/10 (70.0%) | 7/10 (70.0%) | 0/10 (0.0%) | 0/10 (0.0%) | 0/10 (0.0%) |
| claw_trading | 7/8 (87.5%) | 7/8 (87.5%) | 0/8 (0.0%) | 0/8 (0.0%) | 0/8 (0.0%) |

#### sonnet_45_id

| domain | no_attacker | collaboration | security | privacy | governance |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 10/10 (100.0%) | 10/10 (100.0%) | 0/10 (0.0%) | 0/10 (0.0%) | 0/10 (0.0%) |
| claw_trading | 8/8 (100.0%) | 6/8 (75.0%) | 0/8 (0.0%) | 0/8 (0.0%) | 0/8 (0.0%) |

### CLaw Heuristic ASR By Model, Domain, And Attack Mode

This uses the runner's per-row `attack_success` fields, not a post-hoc LLM judge.

#### deepseek_v32

| domain | collaboration | security | privacy | governance | total |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 0/10 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/10 (0.0%) |
| claw_trading | 4/7 (57.1%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 4/7 (57.1%) |

#### kimi_k25

| domain | collaboration | security | privacy | governance | total |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 0/10 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/10 (0.0%) |
| claw_trading | 3/8 (37.5%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 3/8 (37.5%) |

#### kimi_k2_think

| domain | collaboration | security | privacy | governance | total |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 1/9 (11.1%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 1/9 (11.1%) |
| claw_trading | 0/6 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/6 (0.0%) |

#### opus_41_id

| domain | collaboration | security | privacy | governance | total |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 0/10 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/10 (0.0%) |
| claw_trading | 0/4 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/4 (0.0%) |

#### opus_47_id

| domain | collaboration | security | privacy | governance | total |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 1/10 (10.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 1/10 (10.0%) |
| claw_trading | 3/8 (37.5%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 3/8 (37.5%) |

#### qwen3_235b

| domain | collaboration | security | privacy | governance | total |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 0/10 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/10 (0.0%) |
| claw_trading | 3/8 (37.5%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 3/8 (37.5%) |

#### qwen3_32b

| domain | collaboration | security | privacy | governance | total |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 3/10 (30.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 3/10 (30.0%) |
| claw_trading | 0/7 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/7 (0.0%) |

#### sonnet_45_id

| domain | collaboration | security | privacy | governance | total |
|---|---:|---:|---:|---:|---:|
| claw_clinical | 0/10 (0.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 0/10 (0.0%) |
| claw_trading | 2/8 (25.0%) | 0/0 (n/a) | 0/0 (n/a) | 0/0 (n/a) | 2/8 (25.0%) |

<!-- CLAW_BEDROCK_SWEEP_END -->
