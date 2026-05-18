"""Per-scenario Session object for the gateway.

A :class:`Session` holds the audit substrate (``ActionLog``, ``ShadowLog``,
``PhaseTracker``), the optional cassette recorder, and any registered
``PolicyHook`` instances for a single scenario run. It is the gateway-layer
counterpart to the v1 ``ScenarioRunner``'s construction block (see
``clawsocialarena/runtime/runner.py`` lines 41-85) stripped of the agent
registry: the gateway wires agents out-of-process, so ``Session`` is a pure
data-plus-construction object.

Under :data:`~clawsocialarena.types.AuditCondition.BASELINE` all substrate
fields are ``None``, mirroring the "deployment without audit infrastructure"
condition in spec §5.1. Under ``PASSIVE`` or ``ENFORCE`` the full set of
audit primitives is instantiated.

Phase A.5 lands the real enforce/passive semantics on this object so the
v1 ``AuditedMessageBus`` becomes redundant: every ``record_*`` helper
double-writes to the shadow log, dispatches any matching ``PolicyHook``,
emits a ``POLICY_DECISION`` record per verdict, and under ``ENFORCE``
returns the rewritten content (or a blocked sentinel) so the caller can
propagate it to the inbox queue and, for tool calls, short-circuit the
MCP dispatch.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.mswm import MSWM, MswmTransaction
from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.policies.governance import GovernancePolicyHook
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.gateway.cassette import CassetteRecorder
from clawsocialarena.gateway.mcp_host import McpHost, ToolHandler
from clawsocialarena.mcp_tools.filesystem import FilesystemResourceTool
from clawsocialarena.mcp_tools.personal_db import PersonalDatabaseTool
from clawsocialarena.protocols.policy_hook import (
    PolicyDecision,
    PolicyHook,
    PolicyVerdict,
)
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    AuditCondition,
    ExecutionPhase,
    GovernanceRecord,
    IntegrityLevel,
    SocialPhase,
)
from clawsocialarena.scenario.models import GovernanceManifest, ResourceManifest


# Map action types to the ``hook_kind`` buckets v1 used to scope hook
# dispatch. ``message`` fires on outbound messages, ``tool`` fires on the
# tool_call / tool_observation_return pair, ``memory`` fires on memory
# writes / compressions / summaries. Anything not in this table (e.g.
# ``llm_call``) bypasses hook evaluation entirely.
_HOOK_KIND_FOR_ACTION: dict[ActionType, str] = {
    ActionType.OUTBOUND_MESSAGE: "message",
    ActionType.TOOL_CALL: "tool",
    ActionType.TOOL_OBSERVATION_RETURN: "tool",
    ActionType.MEMORY_WRITE: "memory",
    ActionType.MEMORY_COMPRESSION: "memory",
    ActionType.SUMMARY_WRITE: "memory",
}


@dataclass
class RecordOutcome:
    """Result of a :meth:`Session._record_action` call.

    ``action_id`` is ``None`` under BASELINE (no log, no id) or when the
    final action was blocked by a hook under ENFORCE (no record written).
    ``rewritten_content`` is the content the caller should propagate
    downstream (e.g. onto the recipient inbox queue) under ENFORCE after
    a ``rewrite`` verdict; for ``message`` hooks it is a string, for
    ``memory`` hooks it is the replacement memory text. ``blocked`` is
    True when any ENFORCE hook returned ``block``; the caller must treat
    the action as never having occurred (no inbox put, no MCP dispatch).
    """

    action_id: str | None = None
    rewritten_content: str | None = None
    blocked: bool = False


@dataclass
class Session:
    """Container for one scenario's audit substrate and policy hooks.

    Attributes:
        scenario_id: Stable identifier for the scenario this session serves.
        condition: Audit condition governing which substrate fields are wired.
        action_log: Primary hash-chained action log, or ``None`` under BASELINE.
        shadow_log: Privileged independent copy, or ``None`` under BASELINE.
        phase_tracker: Social-phase tracker, or ``None`` under BASELINE.
        cassette: Optional cassette recorder (Task A5 will populate this).
        hooks: Ordered list of ``PolicyHook`` instances to consult at egress.
        inboxes: Lazily-created per-recipient message queues. Each entry is a
            FIFO of ``(sender_id, content)`` tuples waiting for a ``/recv``.
        mcp_host: In-process MCP tool registry. Present under every audit
            condition (BASELINE too) so scenario setup code has a uniform
            registration surface; BASELINE dispatches still run but are not
            logged.
    """

    scenario_id: str
    condition: AuditCondition
    action_log: ActionLog | None = None
    shadow_log: ShadowLog | None = None
    phase_tracker: PhaseTracker | None = None
    cassette: CassetteRecorder | None = None
    hooks: list[PolicyHook] = field(default_factory=list)
    inboxes: dict[str, asyncio.Queue[tuple[str, str]]] = field(default_factory=dict)
    mcp_host: McpHost = field(default_factory=McpHost)
    audit_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # MSWM is cheap in-memory state and is always present, even under
    # BASELINE. Under BASELINE the gateway never calls ``_record_action``
    # (early-return on the baseline gate), so MSWM naturally stays empty;
    # keeping the field always-present makes it safe for the gateway HTTP
    # handlers and the MSWM-aware hook to reference unconditionally.
    mswm: MSWM = field(default_factory=MSWM)

    @classmethod
    def build(
        cls,
        scenario_id: str,
        condition: AuditCondition,
        *,
        db_path: str | Path,
        phase_schedule: list[dict] | None = None,
        work_dir: Path | str | None = None,
        hooks: list[PolicyHook] | None = None,
        governance_manifest: GovernanceManifest | dict[str, Any] | None = None,
        resource_root: Path | str | None = None,
        resource_manifest: ResourceManifest | dict[str, Any] | None = None,
        family_id: str | None = None,
        family_pack_context: dict[str, Any] | None = None,
    ) -> "Session":
        """Construct a Session with substrate wired per ``condition``.

        Under BASELINE every substrate field stays ``None`` and ``db_path``
        is ignored; any supplied ``hooks`` are also dropped because baseline
        is defined as "deployment without audit infrastructure" and hook
        dispatch would contradict that semantics. Under PASSIVE or ENFORCE
        the full audit stack is created, with the shadow log persisted
        alongside the primary log as ``{db_path.stem}.shadow.db`` in the
        same directory. When ``work_dir`` is supplied under a non-baseline
        condition, a :class:`CassetteRecorder` is attached that writes a
        ``cassette.jsonl`` file inside that directory.

        Args:
            scenario_id: Stable identifier for the scenario.
            condition: Audit condition governing substrate wiring.
            db_path: Filesystem path for the primary ``ActionLog`` DB.
                Ignored under BASELINE.
            phase_schedule: Optional phase schedule (as used by
                ``PhaseTracker.from_schedule``). When absent a plain
                :class:`PhaseTracker` is created.
            work_dir: Optional filesystem directory for session artifacts
                such as the cassette. When omitted, no cassette is attached.
                Under BASELINE this argument is ignored.
            hooks: Ordered list of ``PolicyHook`` instances. Ignored under
                BASELINE.
            governance_manifest: Optional manifest used to wire a
                governance hook outside BASELINE.
        """

        if condition == AuditCondition.BASELINE:
            session = cls(scenario_id=scenario_id, condition=condition)
            if resource_root is not None and resource_manifest is not None:
                session.register_resource_tools(resource_root, resource_manifest)
            if family_id and resource_root is not None:
                session.register_family_pack_tools(
                    family_id=family_id,
                    resource_root=resource_root,
                    context=family_pack_context,
                )
            return session

        primary_path = Path(db_path)
        action_log = ActionLog(db_path=primary_path)
        shadow_path = primary_path.parent / f"{primary_path.stem}.shadow.db"
        shadow_log = ShadowLog(db_path=shadow_path)
        phase_tracker = (
            PhaseTracker.from_schedule(phase_schedule)
            if phase_schedule
            else PhaseTracker()
        )
        cassette: CassetteRecorder | None = None
        if work_dir is not None:
            cassette = CassetteRecorder(Path(work_dir) / "cassette.jsonl")
        wired_hooks = list(hooks) if hooks else []
        if governance_manifest is not None:
            wired_hooks.insert(
                0,
                GovernancePolicyHook(
                    governance_manifest,
                    resource_manifest=resource_manifest,
                ),
            )
        session = cls(
            scenario_id=scenario_id,
            condition=condition,
            action_log=action_log,
            shadow_log=shadow_log,
            phase_tracker=phase_tracker,
            cassette=cassette,
            hooks=wired_hooks,
        )
        if resource_root is not None and resource_manifest is not None:
            session.register_resource_tools(resource_root, resource_manifest)
        if family_id and resource_root is not None:
            session.register_family_pack_tools(
                family_id=family_id,
                resource_root=resource_root,
                context=family_pack_context,
            )
        return session

    def register_family_pack_tools(
        self,
        *,
        family_id: str,
        resource_root: Path | str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Register family-pack-specific MCP handlers against this session.

        Supports all v2 family packs: ``tau2_retail``, ``tau2_airline``,
        ``tau2_telecom``, ``marble_research``, ``marble_bargaining``,
        ``marble_bidding``, ``swebench_workspace``, ``wildclaw_social``.
        The ``context`` dict carries family-specific parameters; the
        per-family keys are enumerated by
        :data:`clawsocialarena.generator.family_pack_registry.FAMILY_LOADERS`
        under each entry's ``session_context_keys`` field. When ``context``
        is omitted or partial, each branch falls back to its pack's default
        configuration (e.g., tau2_retail defaults to household HH-7 with
        primary owner alice and secondary owner bob).

        Unknown ``family_id`` values are skipped silently so a forward-
        compatible bundle (declaring a family pack the runtime does not
        know about yet) does not crash construction. A future strict
        mode could promote this to an error.
        """
        ctx = dict(context or {})
        if family_id == "tau2_retail":
            from clawsocialarena.mcp_tools.tau2_retail import (
                RetailSessionContext,
                register_tau2_retail_handlers,
            )

            # The four archetypes carry different owner-id fields in their
            # family_pack_context. Thread them all through so the per-
            # archetype handlers (and authenticatable_owners) see the right
            # set without each archetype needing its own branch here. The
            # shared_account defaults preserve legacy behavior for bundles
            # that pre-date the 4-archetype redesign.
            archetype = str(ctx.get("archetype") or "shared_account")
            household = RetailSessionContext(
                resources_root=Path(resource_root),
                archetype=archetype,
                household_id=str(ctx.get("household_id", "HH-7") or ""),
                primary_owner_id=str(ctx.get("primary_owner_id", "alice") or ""),
                secondary_owner_ids=tuple(ctx.get("secondary_owner_ids") or ("bob",)),
                sender_owner_id=str(ctx.get("sender_owner_id") or ""),
                recipient_owner_id=str(ctx.get("recipient_owner_id") or ""),
                customer_owner_id=str(ctx.get("customer_owner_id") or ""),
                store_rep_owner_id=str(ctx.get("store_rep_owner_id") or ""),
                hub_owner_id=str(ctx.get("hub_owner_id") or ""),
                spoke_owner_ids=tuple(ctx.get("spoke_owner_ids") or ()),
                shared_account_id=str(ctx.get("shared_account_id") or ""),
            )
            # store_rep_dyad / cross_account have no household; clear the
            # shared_account defaults so authenticatable_owners only includes
            # the archetype's actual owners.
            if archetype in ("store_rep_dyad", "cross_account", "hub_aggregator"):
                household = RetailSessionContext(
                    resources_root=Path(resource_root),
                    archetype=archetype,
                    household_id="",
                    primary_owner_id="",
                    secondary_owner_ids=(),
                    sender_owner_id=str(ctx.get("sender_owner_id") or ""),
                    recipient_owner_id=str(ctx.get("recipient_owner_id") or ""),
                    customer_owner_id=str(ctx.get("customer_owner_id") or ""),
                    store_rep_owner_id=str(ctx.get("store_rep_owner_id") or ""),
                    hub_owner_id=str(ctx.get("hub_owner_id") or ""),
                    spoke_owner_ids=tuple(ctx.get("spoke_owner_ids") or ()),
                    shared_account_id=str(ctx.get("shared_account_id") or ""),
                )
            register_tau2_retail_handlers(self.mcp_host, context=household)
            return
        if family_id == "tau2_airline":
            from clawsocialarena.mcp_tools.tau2_airline import (
                GroupBookingContext,
                register_tau2_airline_handlers,
            )

            group = GroupBookingContext(
                resources_root=Path(resource_root),
                group_id=str(ctx.get("group_id", "GRP-7")),
                organizer_owner_id=str(ctx.get("organizer_owner_id", "alice")),
                traveler_owner_ids=tuple(ctx.get("traveler_owner_ids") or ("bob",)),
            )
            register_tau2_airline_handlers(self.mcp_host, context=group)
            return
        if family_id == "tau2_telecom":
            from clawsocialarena.mcp_tools.tau2_telecom import (
                FamilyPlanContext,
                register_tau2_telecom_handlers,
            )

            plan = FamilyPlanContext(
                resources_root=Path(resource_root),
                account_id=str(ctx.get("account_id", "ACC-7")),
                primary_owner_id=str(ctx.get("primary_owner_id", "alice")),
                secondary_owner_ids=tuple(ctx.get("secondary_owner_ids") or ("bob",)),
            )
            register_tau2_telecom_handlers(self.mcp_host, context=plan)
            return
        if family_id == "marble_research":
            from clawsocialarena.mcp_tools.marble_research import (
                ResearchCollaborationContext,
                register_marble_research_handlers,
            )

            collaboration = ResearchCollaborationContext(
                resources_root=Path(resource_root),
                proposal_id=str(ctx.get("proposal_id", "PROP-7")),
                convener_owner_id=str(ctx.get("convener_owner_id", "alice")),
                peer_owner_ids=tuple(ctx.get("peer_owner_ids") or ("bob", "carol")),
            )
            register_marble_research_handlers(self.mcp_host, context=collaboration)
            return
        if family_id == "marble_bargaining":
            from clawsocialarena.mcp_tools.marble_bargaining import (
                BargainingContext,
                register_marble_bargaining_handlers,
            )

            bargain = BargainingContext(
                resources_root=Path(resource_root),
                transaction_id=str(ctx.get("transaction_id", "TXN-OE-001")),
                resource_profile=str(
                    ctx.get("resource_profile", "owned_ecosystem_procurement")
                ),
                item_id=str(ctx.get("item_id", "PRINTER-BUNDLE-12")),
                quantity=int(ctx.get("quantity", 12)),
                target_price=float(ctx.get("target_price", 795.0)),
                buyer_owner_id=str(ctx.get("buyer_owner_id", "acme_procurement")),
                seller_owner_id=str(ctx.get("seller_owner_id", "northstar_sales")),
                approver_owner_id=str(ctx.get("approver_owner_id", "acme_finance")),
            )
            register_marble_bargaining_handlers(self.mcp_host, context=bargain)
            return
        if family_id == "marble_bidding":
            from clawsocialarena.mcp_tools.marble_bidding import (
                BiddingContext,
                register_marble_bidding_handlers,
            )

            buyer_owner_ids = tuple(
                str(owner)
                for owner in (
                    ctx.get("buyer_owner_ids")
                    or ("anchor_procurement", "beacon_procurement")
                )
            )
            buyer_agent_ids = tuple(
                str(agent_id)
                for agent_id in (
                    ctx.get("buyer_agent_ids") or ("anchor_buyer", "beacon_buyer")
                )
            )
            default_budgets = {
                "anchor_procurement": 430.0,
                "beacon_procurement": 420.0,
            }
            raw_budgets = ctx.get("buyer_budget_ceiling_by_owner")
            if raw_budgets is None:
                raw_budgets = default_budgets
            budgets = {}
            if isinstance(raw_budgets, dict):
                for owner in buyer_owner_ids:
                    raw_value = raw_budgets.get(owner)
                    try:
                        budget = float(raw_value)
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(budget):
                        budgets[owner] = budget
            bidding = BiddingContext(
                resources_root=Path(resource_root),
                auction_id=str(ctx.get("auction_id", "AUC-BID-000")),
                item_id=str(ctx.get("item_id", "BID-LOT-000")),
                quantity=int(ctx.get("quantity", 8)),
                seller_owner_id=str(ctx.get("seller_owner_id", "sable_supply_sales")),
                buyer_owner_ids=buyer_owner_ids,
                seller_minimum_unit_price=float(
                    ctx.get("seller_minimum_unit_price", 360.0)
                ),
                buyer_budget_ceiling_by_owner=budgets,
                required_terms=tuple(
                    str(term)
                    for term in (
                        ctx.get("required_terms")
                        or ("delivery_by_2026-06-30", "warranty_12_months")
                    )
                ),
                agent_owner_by_id={
                    str(ctx.get("seller_agent_id", "sable_seller")): str(
                        ctx.get("seller_owner_id", "sable_supply_sales")
                    ),
                    **{
                        agent_id: owner_id
                        for agent_id, owner_id in zip(
                            buyer_agent_ids,
                            buyer_owner_ids,
                        )
                    },
                },
            )
            register_marble_bidding_handlers(self.mcp_host, context=bidding)
            return
        if family_id == "swebench_workspace":
            from clawsocialarena.mcp_tools.swebench_workspace import (
                WorkspaceCodingContext,
                register_swebench_workspace_handlers,
            )

            owner_ids = tuple(
                str(owner)
                for owner in (
                    ctx.get("owner_ids")
                    or (
                        ctx.get("implementer_owner_id", "maya"),
                        ctx.get("reviewer_owner_id", "nolan"),
                        ctx.get("code_owner_id", "opal"),
                        ctx.get("ci_owner_id", "priya"),
                    )
                )
            )
            workspace = WorkspaceCodingContext(
                resources_root=Path(resource_root),
                instance_id=str(ctx.get("instance_id", "django__django-0001")),
                repo_name=str(ctx.get("repo_name", "django/django")),
                base_commit=str(ctx.get("base_commit", "")),
                owner_ids=owner_ids,
                code_owner_id=str(ctx.get("code_owner_id", "opal")),
                workspace_substrate_version=str(
                    ctx.get("workspace_substrate_version", "v1")
                ),
            )
            register_swebench_workspace_handlers(self.mcp_host, context=workspace)
            return
        if family_id == "wildclaw_social":
            from clawsocialarena.mcp_tools.wildclaw_social import (
                MeetingNegotiationContext,
                register_wildclaw_social_handlers,
            )

            meeting = MeetingNegotiationContext(
                resources_root=Path(resource_root),
                meeting_id=str(ctx.get("meeting_id", "MTG-7")),
                organizer_owner_id=str(ctx.get("organizer_owner_id", "alice")),
                participant_owner_ids=tuple(
                    ctx.get("participant_owner_ids") or ("bob", "carol", "dave")
                ),
            )
            register_wildclaw_social_handlers(self.mcp_host, context=meeting)
            return
        if family_id == "travel":
            from clawsocialarena.mcp_tools.travel import (
                TravelContext,
                register_travel_handlers,
            )

            owner_to_agent: dict[str, str] = {}
            traveler_owner_id = str(ctx.get("traveler_owner_id", ""))
            partner_owner_id = str(ctx.get("partner_hotel_owner_id", ""))
            approver_owner_id = str(ctx.get("approver_owner_id", ""))
            organizer_owner_id = str(ctx.get("organizer_owner_id", ""))
            co_owner_ids = tuple(
                str(o) for o in (ctx.get("co_traveler_owner_ids") or ())
            )
            traveler_agent_id = str(ctx.get("traveler_agent_id", ""))
            partner_agent_id = str(ctx.get("partner_hotel_agent_id", ""))
            approver_agent_id = str(ctx.get("approver_agent_id", ""))
            organizer_agent_id = str(ctx.get("organizer_agent_id", ""))
            co_agent_ids = tuple(
                str(a) for a in (ctx.get("co_traveler_agent_ids") or ())
            )
            for oid, aid in (
                (traveler_owner_id, traveler_agent_id),
                (partner_owner_id, partner_agent_id),
                (approver_owner_id, approver_agent_id),
                (organizer_owner_id, organizer_agent_id),
            ):
                if oid and aid:
                    owner_to_agent[oid] = aid
            for oid, aid in zip(co_owner_ids, co_agent_ids):
                if oid and aid:
                    owner_to_agent[oid] = aid

            travel = TravelContext(
                resources_root=Path(resource_root),
                trip_id=str(ctx.get("trip_id", "TRIP-CU-OE-001")),
                resource_profile=str(
                    ctx.get("resource_profile", "owned_ecosystem_solo_business_yunnan")
                ),
                destination=str(ctx.get("destination", "Huaning County, Yunnan")),
                target_unit_rate=float(ctx.get("target_unit_rate", 420.0)),
                partner_floor_rate=float(ctx.get("partner_floor_rate", 395.0)),
                room_type_target=str(ctx.get("room_type_target", "deluxe_king")),
                quantity=int(ctx.get("quantity", 3)),
                traveler_owner_id=traveler_owner_id,
                partner_hotel_owner_id=partner_owner_id,
                approver_owner_id=approver_owner_id,
                organizer_owner_id=organizer_owner_id,
                co_traveler_owner_ids=co_owner_ids,
                delegate_authorization_code=str(
                    ctx.get("delegate_authorization_code", "")
                ),
                owner_to_agent=owner_to_agent,
            )
            register_travel_handlers(self.mcp_host, context=travel)
            return
        # Unknown family_id: skip silently rather than block scenario
        # construction. A future strict mode could raise here.

    def register_resource_tools(
        self,
        resource_root: Path | str,
        resource_manifest: ResourceManifest | dict[str, Any],
    ) -> None:
        """Register gateway-hosted ``fs.*`` and ``db.*`` resource tools."""

        manifest = ResourceManifest.model_validate(resource_manifest)
        operations = {
            operation
            for resource in manifest.resources.values()
            for rule in resource.allowed_operations
            for operation in rule.operations
        }
        fs_tool = FilesystemResourceTool(resource_root, manifest)
        db_tool = PersonalDatabaseTool(resource_root, manifest)

        def fs_handler(operation: str) -> ToolHandler:
            def _handler(arguments: dict) -> dict:
                return fs_tool.dispatch(operation, arguments)

            return _handler

        def db_handler(operation: str) -> ToolHandler:
            def _handler(arguments: dict) -> dict:
                return db_tool.dispatch(operation, arguments)

            return _handler

        for operation in sorted(operations):
            if operation.startswith("fs."):
                self.mcp_host.register(operation, fs_handler(operation))
            elif operation.startswith("db."):
                self.mcp_host.register(operation, db_handler(operation))

    def close(self) -> None:
        """Release per-session resources. Idempotent.

        Currently closes the cassette recorder if one is attached. Future
        resources (open DB handles, MCP hosts) should hook in here too.
        """

        if self.cassette is not None:
            self.cassette.close()

    def ensure_inbox(self, recipient_id: str) -> asyncio.Queue[tuple[str, str]]:
        """Return the inbox queue for ``recipient_id``, creating it on first use.

        Queues are created lazily so the gateway can serve arbitrary recipient
        ids without preconfiguration. The first ``/send`` or ``/recv`` for a
        recipient materializes the queue.
        """

        queue = self.inboxes.get(recipient_id)
        if queue is None:
            queue = asyncio.Queue()
            self.inboxes[recipient_id] = queue
        return queue

    async def send_outbound(
        self,
        *,
        sender_id: str,
        recipient_id: str,
        content: str,
        source_action_ids: list[str] | None = None,
        mentioned_items: list[str] | None = None,
        declared_action_id: str | None = None,
        governance: GovernanceRecord | None = None,
        turn_index: int | None = None,
    ) -> RecordOutcome:
        """Record and enqueue an outbound message as one audited operation.

        ``record_outbound`` remains a record-only primitive. This helper
        owns the delivery side effect so record/rewrite/block decisions and
        recipient inbox mutation are serialized by the per-session audit
        lock.
        """

        async with self.audit_lock:
            if self.condition == AuditCondition.BASELINE or self.action_log is None:
                inbox = self.ensure_inbox(recipient_id)
                await inbox.put((sender_id, content))
                return RecordOutcome()

            payload: dict = {"recipient_id": recipient_id, "content": content}
            if mentioned_items is not None:
                payload["mentioned_items"] = list(mentioned_items)
            if declared_action_id is not None:
                payload["declared_action_id"] = declared_action_id
            outcome = await self._record_action_unlocked(
                agent_id=sender_id,
                action_type=ActionType.OUTBOUND_MESSAGE,
                payload=payload,
                id_prefix="act",
                hook_target_content=content,
                source_action_ids=source_action_ids,
                governance=governance,
                turn_index=turn_index,
            )
            if outcome.blocked:
                return outcome

            delivered = (
                outcome.rewritten_content
                if outcome.rewritten_content is not None
                else content
            )
            inbox = self.ensure_inbox(recipient_id)
            await inbox.put((sender_id, delivered))
            return outcome

    async def record_outbound(
        self,
        *,
        sender_id: str,
        recipient_id: str,
        content: str,
        source_action_ids: list[str] | None = None,
        mentioned_items: list[str] | None = None,
        declared_action_id: str | None = None,
        governance: GovernanceRecord | None = None,
        turn_index: int | None = None,
    ) -> RecordOutcome:
        """Append an ``OUTBOUND_MESSAGE`` ActionRecord for a send, if audited.

        Under BASELINE this is a no-op and returns an empty outcome: the
        baseline condition simulates "deployment without audit
        infrastructure" so no log exists to append to and no hooks run.
        Under PASSIVE or ENFORCE the record is appended to the primary
        ``ActionLog`` AND the shadow log, any registered ``message``-kind
        hooks are evaluated, and their verdicts land as ``POLICY_DECISION``
        rows. ENFORCE additionally reflects ``rewrite`` / ``block`` verdicts
        back on the returned :class:`RecordOutcome`:

        - ``rewrite``: ``rewritten_content`` holds the final content; the
          persisted OUTBOUND_MESSAGE row carries this content.
        - ``block``: ``blocked`` is True, ``action_id`` is ``None``, no
          OUTBOUND_MESSAGE row is written (the caller must skip the
          inbox enqueue).

        ``mentioned_items`` is the MSWM payload convention introduced in
        Phase C. When supplied, the items are attached to ``payload`` under
        the ``mentioned_items`` key so ``MSWM.on_action`` can update the
        sender / recipient peer models. When absent the payload omits the
        key and MSWM is left unchanged for this action.
        """

        payload: dict = {"recipient_id": recipient_id, "content": content}
        if mentioned_items is not None:
            payload["mentioned_items"] = list(mentioned_items)
        if declared_action_id is not None:
            payload["declared_action_id"] = declared_action_id
        return await self._record_action(
            agent_id=sender_id,
            action_type=ActionType.OUTBOUND_MESSAGE,
            payload=payload,
            id_prefix="act",
            hook_target_content=content,
            source_action_ids=source_action_ids,
            governance=governance,
            turn_index=turn_index,
        )

    async def record_tool_call(
        self,
        *,
        agent_id: str,
        tool_name: str,
        arguments: dict,
        source_action_ids: list[str] | None = None,
        governance: GovernanceRecord | None = None,
        turn_index: int | None = None,
    ) -> RecordOutcome:
        """Append a ``TOOL_CALL`` ActionRecord if the session is audited.

        Under BASELINE returns an empty outcome with no log append. Under
        PASSIVE or ENFORCE the record is appended and any ``tool``-kind
        hooks run. Under ENFORCE a ``block`` verdict sets ``blocked=True``
        on the outcome and suppresses the TOOL_CALL row so the caller can
        short-circuit the MCP dispatch; ``rewrite`` verdicts are logged as
        POLICY_DECISION rows but do not currently rewrite the persisted
        arguments (no tool-rewrite semantics defined).
        """

        hook_target = f"{tool_name}({arguments!r})"
        return await self._record_action(
            agent_id=agent_id,
            action_type=ActionType.TOOL_CALL,
            payload={"tool_name": tool_name, "arguments": arguments},
            id_prefix="tc",
            hook_target_content=hook_target,
            source_action_ids=source_action_ids,
            governance=governance,
            turn_index=turn_index,
        )

    async def record_tool_observation(
        self,
        *,
        agent_id: str,
        tool_call_action_id: str | None,
        tool_name: str,
        observation: str,
        source_action_ids: list[str] | None = None,
        governance: GovernanceRecord | None = None,
        turn_index: int | None = None,
    ) -> RecordOutcome:
        """Append a ``TOOL_OBSERVATION_RETURN`` ActionRecord, if audited.

        Payload mirrors v1's ``AuditedMessageBus.record_tool_observation``:
        ``{tool_call_action_id, tool_name, observation}``. Baseline returns
        an empty outcome; passive/enforce append and return the new
        ``action_id``. Hooks are not evaluated on returns: the call itself
        was the decision point.

        TODO(F-pair): ``tool_call_action_id`` is recorded verbatim and
        not yet validated against existing ``TOOL_CALL`` records in the
        action log. Call/return pairing verification belongs in the
        MSWM-aware attribution phase (see Phase F in the plan), where
        the attribution graph walker already rebuilds tool call/return
        edges.
        """

        return await self._record_action(
            agent_id=agent_id,
            action_type=ActionType.TOOL_OBSERVATION_RETURN,
            payload={
                "tool_call_action_id": tool_call_action_id,
                "tool_name": tool_name,
                "observation": observation,
            },
            id_prefix="tr",
            hook_target_content=observation,
            source_action_ids=source_action_ids,
            governance=governance,
            turn_index=turn_index,
        )

    async def record_memory_write(
        self,
        *,
        agent_id: str,
        content: str,
        tags: list[str] | None = None,
        source_action_ids: list[str] | None = None,
        governance: GovernanceRecord | None = None,
        turn_index: int | None = None,
    ) -> RecordOutcome:
        """Append a ``MEMORY_WRITE`` ActionRecord, if audited.

        ``tags`` is normalized to an empty list when absent so downstream
        consumers always see a list. Baseline returns an empty outcome.
        Memory-kind hooks may rewrite the content or block the write under
        ENFORCE; PASSIVE logs the verdict but always persists the original.
        """

        return await self._record_action(
            agent_id=agent_id,
            action_type=ActionType.MEMORY_WRITE,
            payload={"content": content, "tags": list(tags) if tags else []},
            id_prefix="mem",
            hook_target_content=content,
            source_action_ids=source_action_ids,
            governance=governance,
            turn_index=turn_index,
        )

    async def record_llm_call(
        self,
        *,
        agent_id: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        model: str,
        cached_tokens: int = 0,
        source_action_ids: list[str] | None = None,
        governance: GovernanceRecord | None = None,
        turn_index: int | None = None,
    ) -> RecordOutcome:
        """Append an ``LLM_CALL`` ActionRecord with token accounting, if audited.

        The payload carries five accounting fields (``input_tokens``,
        ``output_tokens``, ``cached_tokens``, ``latency_ms``, ``model``).
        ``cached_tokens`` defaults to 0 when the caller omits it. Baseline
        returns an empty outcome. LLM calls are not hook-scoped.
        """

        return await self._record_action(
            agent_id=agent_id,
            action_type=ActionType.LLM_CALL,
            payload={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "latency_ms": latency_ms,
                "model": model,
            },
            id_prefix="llm",
            hook_target_content=None,
            source_action_ids=source_action_ids,
            governance=governance,
            turn_index=turn_index,
        )

    async def _record_action(
        self,
        *,
        agent_id: str,
        action_type: ActionType,
        payload: dict,
        id_prefix: str,
        hook_target_content: str | None,
        source_action_ids: list[str] | None = None,
        governance: GovernanceRecord | None = None,
        turn_index: int | None = None,
    ) -> RecordOutcome:
        """Serialize audit mutation and delegate to the unlocked recorder."""

        async with self.audit_lock:
            return await self._record_action_unlocked(
                agent_id=agent_id,
                action_type=action_type,
                payload=payload,
                id_prefix=id_prefix,
                hook_target_content=hook_target_content,
                source_action_ids=source_action_ids,
                governance=governance,
                turn_index=turn_index,
            )

    async def _record_action_unlocked(
        self,
        *,
        agent_id: str,
        action_type: ActionType,
        payload: dict,
        id_prefix: str,
        hook_target_content: str | None,
        source_action_ids: list[str] | None = None,
        governance: GovernanceRecord | None = None,
        turn_index: int | None = None,
    ) -> RecordOutcome:
        """Shared helper: append an ActionRecord under PASSIVE or ENFORCE.

        Steps, mirroring the v1 ``AuditedMessageBus``:

        1. Baseline short-circuit (no log, empty outcome).
        2. Mint a stable ``action_id`` up front so every POLICY_DECISION
           emitted here can reference the target action even when that
           target is ultimately blocked (no row written).
        3. Apply the candidate action to a tentative MSWM in transaction-local
           state so hooks see fresh state without mutating committed MSWM.
        4. For each hook matching ``_HOOK_KIND_FOR_ACTION[action_type]``,
           evaluate against a candidate ActionRecord and emit a
           POLICY_DECISION row per verdict.
        5. If blocked under ENFORCE, discard the tentative MSWM update and
           return early — no primary record is appended.
        6. Under ENFORCE, rewrites rebuild the tentative MSWM candidate so
           later hooks and the eventual commit see the rewritten payload.
        7. Append the final record to primary log, shadow log, and cassette,
           then commit the tentative MSWM view.

        Under BASELINE this always returns an empty :class:`RecordOutcome`.
        """

        if self.condition == AuditCondition.BASELINE or self.action_log is None:
            return RecordOutcome()

        if turn_index is not None and self.phase_tracker is not None:
            self.phase_tracker.advance_to_turn(turn_index)

        # Phase tracker is always present under passive/enforce because
        # Session.build wires one; but be defensive and fall back so a
        # hand-constructed Session (unit tests) does not crash.
        social_phase = (
            self.phase_tracker.current_phase()
            if self.phase_tracker is not None
            else SocialPhase.DISCOVERY
        )

        action_id = f"{id_prefix}-{uuid.uuid4().hex[:12]}"
        hook_kind = _HOOK_KIND_FOR_ACTION.get(action_type)
        sources = list(source_action_ids or [])

        original_content = hook_target_content
        current_content = hook_target_content
        # Track the mentioned_items list separately so rewrites that drop
        # items get reflected in the final payload AND in MSWM.
        original_mentioned = list(payload.get("mentioned_items") or [])
        current_mentioned: list[str] | None = (
            list(original_mentioned) if "mentioned_items" in payload else None
        )
        blocked = False
        block_decision: PolicyDecision | None = None

        # Build a candidate action so MSWM can update transaction-local
        # tentative state immediately and pre-commit policy hooks can see
        # the action's effects. Committed MSWM is not mutated until the
        # action has been accepted and appended.
        initial_candidate = ActionRecord(
            action_id=action_id,
            prev_hash=self.action_log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=action_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload=dict(payload),
            integrity_level=IntegrityLevel.HASH_CHAINED,
            source_action_ids=sources,
            governance=governance,
        )
        tx = MswmTransaction(self.mswm)
        tx.apply_candidate(initial_candidate)

        if self.hooks:
            for hook in self.hooks:
                hook_scope = getattr(hook, "hook_kind", "message")
                if hook_scope != "governance" and (
                    hook_kind is None or hook_scope != hook_kind
                ):
                    continue
                # Build the candidate action the hook sees. Under PASSIVE it
                # carries the ORIGINAL content (rewrites do not compose
                # because they do not propagate); under ENFORCE it carries
                # the CURRENT (post-previous-rewrite) content so a rewrite
                # chain composes.
                candidate_payload = dict(payload)
                if hook_target_content is not None:
                    content_key = _content_key_for_action(action_type)
                    if content_key is not None:
                        candidate_payload[content_key] = current_content
                if (
                    self.condition == AuditCondition.ENFORCE
                    and current_mentioned is not None
                ):
                    candidate_payload["mentioned_items"] = list(current_mentioned)

                candidate = ActionRecord(
                    action_id=action_id,
                    prev_hash=self.action_log.head_hash(agent_id),
                    agent_id=agent_id,
                    action_type=action_type,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    execution_phase=ExecutionPhase.NOMINAL,
                    social_phase=social_phase,
                    payload=candidate_payload,
                    integrity_level=IntegrityLevel.HASH_CHAINED,
                    source_action_ids=sources,
                    governance=governance,
                )
                decision: PolicyDecision = hook.evaluate(
                    action=candidate,
                    context={
                        "mswm": tx.tentative,
                        "mswm_tentative": tx.tentative,
                        "mswm_committed": tx.committed,
                        "candidate_action_id": action_id,
                    },
                )

                post_content = (
                    decision.rewritten_content
                    if decision.verdict == PolicyVerdict.REWRITE
                    else None
                )
                self._append_policy_decision(
                    agent_id=agent_id,
                    decision=decision,
                    target_action_id=action_id,
                    action_type=action_type,
                    original_payload=payload,
                    social_phase=social_phase,
                    original_content=original_content,
                    post_content=post_content,
                    source_action_ids=sources,
                )

                if self.condition == AuditCondition.ENFORCE:
                    if decision.verdict == PolicyVerdict.BLOCK:
                        blocked = True
                        block_decision = decision
                        break
                    if decision.verdict == PolicyVerdict.REWRITE:
                        previous_content = current_content
                        previous_mentioned = (
                            list(current_mentioned)
                            if current_mentioned is not None
                            else None
                        )
                        if decision.rewritten_content is not None:
                            current_content = decision.rewritten_content
                        if decision.rewritten_mentioned_items is not None:
                            current_mentioned = list(decision.rewritten_mentioned_items)
                        rewrite_changed = (
                            current_content != previous_content
                            or current_mentioned != previous_mentioned
                        )
                        if rewrite_changed:
                            rewritten_payload = dict(payload)
                            if hook_target_content is not None:
                                content_key = _content_key_for_action(action_type)
                                if content_key is not None:
                                    rewritten_payload[content_key] = current_content
                            if current_mentioned is not None:
                                rewritten_payload["mentioned_items"] = list(
                                    current_mentioned
                                )
                            rewritten_candidate = ActionRecord(
                                action_id=action_id,
                                prev_hash=self.action_log.head_hash(agent_id),
                                agent_id=agent_id,
                                action_type=action_type,
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                execution_phase=ExecutionPhase.NOMINAL,
                                social_phase=social_phase,
                                payload=rewritten_payload,
                                integrity_level=IntegrityLevel.HASH_CHAINED,
                                source_action_ids=sources,
                                governance=governance,
                            )
                            tx.rebuild(rewritten_candidate)

        if blocked:
            # No primary record, no cassette line for the action itself;
            # the POLICY_DECISION rows above preserve the evidence. Discard
            # tentative MSWM so committed state still reflects "action never
            # happened" from the peer's perspective.
            tx.discard()
            _ = block_decision  # retained for future attribution passes
            return RecordOutcome(action_id=None, blocked=True)

        # Build the final payload. Under ENFORCE a rewrite may have changed
        # ``content`` and/or ``mentioned_items``; apply those to the payload
        # before constructing the final record.
        final_payload = dict(payload)
        content_changed = (
            self.condition == AuditCondition.ENFORCE
            and hook_target_content is not None
            and current_content != original_content
        )
        if content_changed:
            content_key = _content_key_for_action(action_type)
            if content_key is not None:
                final_payload[content_key] = current_content

        mentioned_changed = (
            self.condition == AuditCondition.ENFORCE
            and current_mentioned is not None
            and current_mentioned != original_mentioned
        )
        if mentioned_changed and current_mentioned is not None:
            final_payload["mentioned_items"] = list(current_mentioned)

        record = ActionRecord(
            action_id=action_id,
            prev_hash=self.action_log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=action_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload=final_payload,
            integrity_level=IntegrityLevel.HASH_CHAINED,
            source_action_ids=sources,
            governance=governance,
        )

        self.action_log.append(record)

        if self.shadow_log is not None:
            shadow_rec = record.model_copy(
                update={"prev_hash": self.shadow_log.head_hash(agent_id)}
            )
            self.shadow_log.append(shadow_rec)

        if self.cassette is not None:
            self.cassette.record(record)

        self.mswm = tx.commit()

        rewritten = current_content if content_changed else None
        return RecordOutcome(
            action_id=action_id,
            rewritten_content=rewritten,
            blocked=False,
        )

    def _append_policy_decision(
        self,
        *,
        agent_id: str,
        decision: PolicyDecision,
        target_action_id: str,
        action_type: ActionType,
        original_payload: dict,
        social_phase: SocialPhase,
        original_content: str | None,
        post_content: str | None,
        source_action_ids: list[str] | None = None,
    ) -> None:
        """Append a POLICY_DECISION row to primary + shadow logs + cassette.

        Payload shape extends the v1 ``AuditedMessageBus`` schema with
        block/rewrite context for replay-time attribution: ``verdict``,
        ``policy_id``, ``reason``, ``target_action_id``, ``original_content``,
        ``post_content``, plus ``recipient_id`` (for outbound messages),
        ``mentioned_items`` (original pre-rewrite list) and
        ``rewritten_mentioned_items`` (post-rewrite list; ``None`` on block),
        and ``source_action_ids`` (the target action's provenance chain).

        The enrichment does not change the gateway HTTP API; it only lets
        downstream consumers reconstruct blocked or rewritten actions
        without reading another row (blocked actions have no ActionRecord
        at all, so the policy_decision is the only surviving evidence).
        """

        if self.action_log is None:
            return
        pd_payload: dict = {
            "verdict": decision.verdict.value,
            "policy_id": decision.policy_id,
            "reason": decision.reason,
            "audit_condition": self.condition.value,
            "enforcement_effect": self._policy_enforcement_effect(decision.verdict),
            "enforced": self.condition == AuditCondition.ENFORCE
            and decision.verdict in {PolicyVerdict.BLOCK, PolicyVerdict.REWRITE},
            "target_action_id": target_action_id,
            "original_content": original_content,
            "post_content": post_content,
            "source_action_ids": list(source_action_ids or []),
        }
        # Enrichment by action type: outbound messages carry a recipient_id
        # and (optionally) mentioned_items; tool/memory actions carry
        # neither, so we only populate fields that make sense.
        if action_type == ActionType.OUTBOUND_MESSAGE:
            recipient = original_payload.get("recipient_id")
            if recipient is not None:
                pd_payload["recipient_id"] = recipient
        original_mentioned = original_payload.get("mentioned_items")
        if original_mentioned is not None:
            pd_payload["mentioned_items"] = list(original_mentioned)
        # rewritten_mentioned_items: populated on rewrite verdicts that
        # carry the field; explicitly None on block so downstream consumers
        # can distinguish "block dropped all items" from "rewrite dropped
        # a subset".
        if decision.verdict == PolicyVerdict.REWRITE:
            rewritten_items = decision.rewritten_mentioned_items
            if rewritten_items is not None:
                pd_payload["rewritten_mentioned_items"] = list(rewritten_items)
            else:
                pd_payload["rewritten_mentioned_items"] = None
        else:
            pd_payload["rewritten_mentioned_items"] = None
        governance_verdict = getattr(decision, "governance_verdict", None)
        if governance_verdict is not None:
            pd_payload["governance_verdict"] = governance_verdict
        rec = ActionRecord(
            action_id=f"pol-{uuid.uuid4().hex[:12]}",
            prev_hash=self.action_log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=ActionType.POLICY_DECISION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload=pd_payload,
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )
        self.action_log.append(rec)
        if self.shadow_log is not None:
            shadow_rec = rec.model_copy(
                update={"prev_hash": self.shadow_log.head_hash(agent_id)}
            )
            self.shadow_log.append(shadow_rec)
        if self.cassette is not None:
            self.cassette.record(rec)

    def _policy_enforcement_effect(self, verdict: PolicyVerdict) -> str:
        if self.condition == AuditCondition.PASSIVE:
            if verdict == PolicyVerdict.BLOCK:
                return "would_block_audit_only"
            if verdict == PolicyVerdict.REWRITE:
                return "would_rewrite_audit_only"
            return "allow_audit_only"
        if self.condition == AuditCondition.ENFORCE:
            if verdict == PolicyVerdict.BLOCK:
                return "blocked"
            if verdict == PolicyVerdict.REWRITE:
                return "rewritten"
            return "allowed"
        return "not_applicable"


def _content_key_for_action(action_type: ActionType) -> str | None:
    """Return the payload key the hook rewrite should replace, or ``None``.

    Outbound messages carry the evidence in ``payload["content"]``; memory
    writes do the same. Tool calls and tool observations do not have a
    single content field that rewrite semantics can mutate, so we return
    ``None`` and let POLICY_DECISION capture the evidence only.
    """

    if action_type in (
        ActionType.OUTBOUND_MESSAGE,
        ActionType.MEMORY_WRITE,
        ActionType.MEMORY_COMPRESSION,
        ActionType.SUMMARY_WRITE,
    ):
        return "content"
    return None
