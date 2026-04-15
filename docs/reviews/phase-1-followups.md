# Phase 1 — Non-blocking followups

Collected from per-task code-quality reviewer subagents during Phase 1. Address opportunistically or at phase end.

## From Task 1.1 (package scaffold)

1. **`pyproject.toml:12-23` — runtime deps are heavy for a scaffold.** `matplotlib`, `seaborn`, `pandas`, `boto3`, `openai` are declared as unconditional runtime deps, pulling ~300 MB of transitive deps. Consider splitting into `[project.optional-dependencies]` groups (`viz`, `aws`, `llm`).
2. **`pyproject.toml:39` — `asyncio_mode = "auto"` enabled before any async code exists.** Harmless but premature.
3. **`tests/conftest.py` — single-line comment only.** A zero-byte conftest would serve the same role.
4. **`tests/__init__.py` — empty file makes `tests` an importable package.** May cause subtle import-mode issues under `pytest --import-mode=importlib`.

## From Task 1.2 (core types)

5. **`types.py:_require_signature_above_hash_chained` — name bakes in an off-by-one.** Validator checks `>= CROSS_AGENT_SIGNED` but reads as "above HASH_CHAINED." Rename to `_require_signature_at_or_above_cross_agent_signed`.
6. **Test coverage gaps.** `test_types.py` does not verify: (a) ActionRecord is frozen, (b) positive path where `CROSS_AGENT_SIGNED` with non-None signature constructs successfully, (c) `ExecutionPhase` and `SocialPhase` enum value assertions.
7. **`signature: str | None = None` has no length/format constraint.** `signature="   "` strips to empty and still passes "not None" check.
8. **`payload: dict[str, Any]` is type-erased by design.** Follow-up TODO or discriminated-union pattern for per-action-type payload schemas.

## From Task 1.4 (ActionLog SQLite)

9. **TOCTOU race window.** `head_hash` and `append` use separate connections. Safe today because `append` is sync; becomes a bug if made async. Fix: `BEGIN IMMEDIATE` + `UNIQUE(agent_id, prev_hash)`. (Rolls into Phase 3.5f.)
10. **SQLite perf at scale.** Per-append open/commit/close with default journal mode. Add `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL` in `__init__`. Expected 3–10× speedup.
11. **`verify_chain` tests only cover payload tamper.** Add tamper tests for prev_hash-only and record_hash-only. (Partially done in Phase 1.5d and Phase 1.5a — envelope-field tamper tests added.)
12. **`read_all()` materializes full log in memory.** At 150K rows/run it's a footgun. Add `iter_by_agent(agent_id) -> Iterator[ActionRecord]`.

## From Task 1.7 (AuditedMessageBus)

13. **Two different `action_id`s per send.** The logged `act-...` id and the id returned from `inner.send` are distinct.

## From Task 1.9 (AuditableAIAgent)

14. **Unbounded `_history` growth.** Each inbound turn appends two `LLMMessage` entries with no cap. Fine with MockLLMClient; matters in Phase 3 with real models.
15. **`[from <sender>]` tag in user message content.** Should move to structured message metadata.

## From Task 1.10 (Scenario loader)

16. **Pydantic models are permissive.** None set `extra="forbid"`. Hand-authored fixture typos silently dropped.
17. **Silent int coercion.** Pydantic v2 accepts `"8"` for `max_turns: int`.
18. **`invariants: dict[str, list]`** is unparameterized.
19. **Loader has no error wrapping** — missing files raise raw `FileNotFoundError`.

## From Task 1.12 (ScenarioRunner)

20. **`bus._inner` private-attribute access** — fixed in Phase 1.5b (`5406592`).
21. **`_check_terminal` called twice per run()** — wasteful O(n) log reads.
22. **`_PIN_RE` regex doesn't tolerate trailing whitespace.**
23. **No-progress turn accounts for a zero-work first turn** (off-by-one in `turns_used`).
