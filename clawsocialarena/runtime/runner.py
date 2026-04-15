"""ScenarioRunner: orchestrates agents and the AuditedMessageBus for one scenario."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from clawsocialarena.action_log import ActionLog
from clawsocialarena.agents.auditable_agent import AuditableAIAgent
from clawsocialarena.agents.llm_client import LLMClient
from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.bus.audited import AuditedMessageBus
from clawsocialarena.bus.in_process import InProcessMessageBus
from clawsocialarena.scenario.models import Scenario, GTBundle
from clawsocialarena.tasks.scheduling import scheduling_pinned_slot
from clawsocialarena.types import AuditCondition


_PIN_RE = re.compile(r"\[READY_TO_PIN\s+(\S+)\]")


@dataclass
class RunResult:
    scenario_id: str
    turns_used: int
    log_rows: int
    terminal_predicate_passed: bool
    final_state: dict


class ScenarioRunner:
    def __init__(
        self,
        *,
        scenario: Scenario,
        gt: GTBundle,
        llm_factory: Callable[[str], LLMClient],
        db_path: str | Path,
        condition: AuditCondition = AuditCondition.BASELINE,
    ) -> None:
        self.scenario = scenario
        self.gt = gt
        self.log = ActionLog(db_path=db_path)
        shadow_db_path = Path(db_path).parent / f"{Path(db_path).stem}.shadow.db"
        self.shadow = ShadowLog(db_path=shadow_db_path)
        self.phase_tracker = (
            PhaseTracker.from_schedule(gt.phase_schedule)
            if gt.phase_schedule
            else PhaseTracker()
        )
        self.bus = AuditedMessageBus(
            inner=InProcessMessageBus(),
            action_log=self.log,
            condition=condition,
            phase_tracker=self.phase_tracker,
            shadow_log=self.shadow,
        )
        self.agents = {
            spec.agent_id: AuditableAIAgent(
                agent_id=spec.agent_id,
                llm=llm_factory(spec.agent_id),
                bus=self.bus,
                system_prompt=spec.system_prompt_template,
            )
            for spec in scenario.agents
        }
        self.state = dict(scenario.initial_state)

    async def run(self) -> RunResult:
        # Log the opening message as a first-class outbound action from the opener.
        # This preserves the "MessageBus is sole egress" invariant required by SAF
        # Action Recoverability.
        opening = self.scenario.opening_message
        await self.bus.send(
            sender_id=opening["from"], recipient_id=opening["to"], content=opening["content"]
        )
        turns = 0
        for turn_index in range(self.scenario.max_turns):
            self.phase_tracker.advance_to_turn(turn_index)
            progressed = False
            for agent in self.agents.values():
                if await agent.step():
                    progressed = True
            turns += 1
            if self._check_terminal():
                break
            if not progressed:
                break
        return RunResult(
            scenario_id=self.scenario.scenario_id,
            turns_used=turns,
            log_rows=len(self.log.read_all()),
            terminal_predicate_passed=self._check_terminal(),
            final_state=dict(self.state),
        )

    def _check_terminal(self) -> bool:
        spec = self.gt.terminal_predicate
        if spec["type"] == "scheduling_pinned_slot":
            self._maybe_pin_slot()
            return scheduling_pinned_slot(state=self.state, spec=spec)
        return False

    def _maybe_pin_slot(self) -> None:
        """Scan recent log rows for a [READY_TO_PIN <iso>] tag from every agent."""
        rows = self.log.read_all()
        seen: dict[str, str] = {}
        for r in rows:
            if r.action_type.value != "outbound_message":
                continue
            m = _PIN_RE.search(r.payload.get("content", ""))
            if m:
                seen[r.agent_id] = m.group(1)
        agent_ids = [a.agent_id for a in self.scenario.agents]
        if all(a in seen for a in agent_ids):
            if len(set(seen.values())) == 1:
                self.state["pinned_slot"] = next(iter(seen.values()))
