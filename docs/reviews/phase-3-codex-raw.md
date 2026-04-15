**Findings**

1. `baseline` is still audit-instrumented, so the §5.1 ablation is not implemented as specified. In baseline, the runner still constructs `ActionLog`, `ShadowLog`, and `PhaseTracker`, and the bus still appends hash-chained `OUTBOUND_MESSAGE` records with `integrity_level=HASH_CHAINED` regardless of condition. That means this is “hooks off,” not “no audit infra / raw transport logging.” See [runner.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/runtime/runner.py:46) and [audited.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/bus/audited.py:45).

2. Tool dispatch bypasses the audited runtime boundary, so the spec’s pre-tool enforcement claim does not hold. `TOOL_CALL` and `TOOL_OBSERVATION_RETURN` are written straight to the primary log; they do not go through condition gating, `PolicyHook`, `ShadowLog`, or `PhaseTracker`, and they hardcode `SocialPhase.DISCOVERY`. That is not just an implementation shortcut; it creates a second egress path outside the audit wrapper. See [auditable_agent.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/agents/auditable_agent.py:69).

3. Tool call/return linkage is incomplete in the log. The logged `TOOL_CALL` record does not store the model’s tool-call id, while `TOOL_OBSERVATION_RETURN` stores only that external id, not the logged `TOOL_CALL.action_id`. So an auditor cannot reliably pair request and response from the action log alone. See [auditable_agent.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/agents/auditable_agent.py:98).

4. The attribution implementation is neither online nor causal. It is built offline during evaluation, and L1 edges are assigned by “within N later records,” which conflates proximity with responsibility and will both over-attribute nearby unrelated outbounds and miss delayed real cascades. See [attribution.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/audit/attribution.py:20) and [eval/runner.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/eval/runner.py:72).

5. Enforce semantics are only sound for the simple single-hook case. All hooks evaluate the original provisional message even after an earlier hook rewrites `content_to_send`, and `policy_decision` records contain no `target_action_id` or blocked/rewritten content. So multi-hook behavior is order-sensitive and blocked messages lose the very evidence you would want to audit. See [audited.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/bus/audited.py:50).

**Answers**

Q1: simple passive/enforce rewrite flow is mostly correct; refreshing `prev_hash` before appending the rewritten outbound avoids the immediate hash-chain bug. The real problems are baseline contamination, non-compositional multi-hook semantics, and block swallowing the underlying content.

Q2: the cascade window is acceptable as a temporary smoke-test heuristic only. For Phase 4, switch to explicit provenance: add `policy_decision.target_action_id`, carry planted disclosure ids / source action ids through outbound/tool/memory actions, and build L0/L1/LX/LR/LF from those links. Keep positional proximity only as a fallback diagnostic.

Q3: direct `action_log.append` is only safe under today’s effectively sequential scheduler. Under the claimed async/Hermes model, the old head-hash race is still there in [action_log.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/action_log.py:87). `SocialPhase.DISCOVERY` hardcoded on tool records is a bug, not acceptable.

Q4: Phase 2 finding #2 is closed by [policy_checkability.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/saf/scorers/policy_checkability.py:25). Finding #3 is only narrowly closed: `produced_dag` is no longer hardcoded empty, but the replacement is an offline L0/L1 heuristic, not the promised online attribution DAG. So strict status is still “not all 8 cleanly resolved.”

Q5: reviewer-2’s “runtime incomplete” objection still has force. Phase 3 meaningfully improves the message path, but the runtime still lacks true pre-tool enforcement, true online attribution, and a spec-faithful baseline. I would pitch this as an audit-aware prototype, not yet a complete audit-first runtime.

I could not independently rerun the tests in this shell because the local interpreter is Python 3.10 while the project requires `>=3.11`; collection fails on `StrEnum`.
