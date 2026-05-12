"""Phase 5 orchestration entry points.

The orchestrator slices the 680-row Phase-5 manifest into five run
batches and dispatches each scenario through a pluggable
:class:`ScenarioExecutor`. The mock executor returns deterministic
results so the orchestration logic stays testable without LLM
calls; the live executor wraps gpt-5.2 naturalization + gpt-4.1-mini
agent simulation to drive Run-Batches 1..5.
"""
