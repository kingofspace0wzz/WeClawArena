# Bargaining And Bidding Design Specs

This folder is the active design entry point for `marble_bargaining` and the owned-ecosystem redesign of `marble_bidding`. The current bargaining slice is an owned-ecosystem grid with 24 base scenarios and 120 matched attack-mode rows. The bidding companion slice is designed as a seller-centered owned-ecosystem grid with 6 base scenarios and 30 matched attack-mode rows.

## Active Specs

| Spec | Use |
|---|---|
| `2026-05-16-marble-bargaining-task-construction.md` | Task grid, owned resources, tool surface, runtime, and cap-36 construction rules. |
| `2026-05-16-marble-bargaining-attack-vectors.md` | Five-mode bargaining attack contract and active runtime playbooks. |
| `2026-05-16-marble-bargaining-evaluation-metrics.md` | Raw TSR, deprecated deterministic-ASR diagnostics, SAF metrics, and LLM-as-a-judge ASR reporting. |
| `2026-05-16-marble-bidding-owned-ecosystem-design.md` | Owned-ecosystem bidding construction, scoring contract, and attack-vector design. |

## Current Grid

| Cell | Base tasks | Rows |
|---|---:|---:|
| `CU-A-marble_bargaining` | 12 | 60 |
| `CM-A-marble_bargaining` | 12 | 60 |
| `CM-C-marble_bidding` | 6 | 30 |
| **Total** | **30** | **150** |

Use `max_turns = 36` for bargaining simulations. Use the same cap for the first owned-ecosystem bidding calibration unless baseline runs show bidding needs a separate cap.

## Archive

Older bargaining drafts are retained in `archive/` for audit history only. They include the shallow MARBLE expansion, early owned-ecosystem checkpoints, delegated-close calibration, stress-attack calibration, and the first ASR judge draft.
