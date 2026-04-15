1. **PARTIALLY RESOLVED** — Recoverability now keys on full-content hash, so same-ID tampering is caught: [recoverability.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/saf/scorers/recoverability.py:17), lines 17-44. Test coverage added for tampered payloads: [test_scorers.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/tests/test_saf/test_scorers.py:57), lines 57-62. But primary-only extras are still explicitly ignored: [test_scorers.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/tests/test_saf/test_scorers.py:65), lines 65-70.

2. **PARTIALLY RESOLVED** — `gt.policies` is now loaded into a fresh per-run registry via `PolicyCatalog`: [runner.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/eval/runner.py:39), lines 39-45 and 64-70; covered by [test_runner.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/tests/test_eval/test_runner.py:106), lines 106-143. But flat-policy decidability still checks field presence “somewhere in the log,” not per-record: [policy_checkability.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/saf/scorers/policy_checkability.py:12), lines 12-24 and 33-36.

3. **NOT RESOLVED** — `EvalRunner` still hardcodes `produced_dag={"nodes": [], "edges": []}`: [runner.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/eval/runner.py:74), lines 71-75.

4. **RESOLVED** — Evidence Integrity behavior is now acknowledged correctly instead of papered over. Weighting remains explicit: [evidence_integrity.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/saf/scorers/evidence_integrity.py:9), lines 9-33. MVP baseline now asserts `0.75` and expects the threshold failure: [test_runner.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/tests/test_eval/test_runner.py:54), lines 54-66.

5. **RESOLVED** — Phase-scoped scorer now separates `decidable` / `satisfied` / `vacuous`: [phase_scoped_policy.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/saf/scorers/phase_scoped_policy.py:53), lines 53-90. Zero-in-phase and missing-field cases are tested: [test_scorers.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/tests/test_saf/test_scorers.py:201), lines 201-239.

6. **RESOLVED** — Geometric mean remains correct/stable: [saf_scorer.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/saf/saf_scorer.py:86), lines 86-96.

7. **RESOLVED** — Runner purity is fixed: constructor holds only `PolicyCatalog`; registry is rebuilt inside `evaluate()`: [runner.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/eval/runner.py:35), lines 35-45 and 64-70.

8. **RESOLVED** — MVP fixture restored `integrity_requirements`: [scenario.gt.json](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/fixtures/scenarios/cu_scheduling_mvp/scenario.gt.json:10), line 10. MVP test now expects `evidence_integrity == 0.75`: [test_runner.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/tests/test_eval/test_runner.py:61), lines 54-66.

**Final verdict:** **STILL NEEDS FIXES**.
