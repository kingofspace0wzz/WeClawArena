"""Phase 3f live batch smoke: tau2_retail with real OpenAI agents.

Materializes one tau2_retail bundle, brings up the gateway service via
Docker Compose, then drives a real multi-turn conversation through the
gateway with OpenAI agents simulated from Python:

- The Python driver plays both ``alice_assistant`` and ``bob_assistant``
  by issuing one ``responses.create`` call per turn, scoped by the
  agent's persona prompt and the conversation history so far.
- Messages flow over the gateway's ``/send`` and ``/recv`` endpoints
  (so the audit log records every outbound and every inbox pop).
- Tool calls flow over ``/mcp/{tool_name}`` (so the audit log records
  the call and observation pair plus the registered family-pack handler
  mutates the SQLite database).
- After the conversation finishes (either ``done=true`` or the budget),
  the driver scores ``evaluation_criteria.env_assertions`` against the
  post-run SQLite and prints the result.

Unlike the in-process Phase 3d smoke this exercises the real Docker
image (built from the live ``server.py`` flags), the real HTTP wiring,
and the real OpenAI model. It still drives the agents from Python
because the agent containers themselves are placeholders (see
``docker/agent-entrypoint.sh``: the default mode is ``tail -f``); the
real OpenClaw delivery channel lands in a later phase.

Cost note: the run does roughly four ``responses.create`` calls against
``gpt-4.1-mini`` by default. Override ``--agent-model`` if you want a
different model. Cap the conversation length via ``--max-turns``.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from clawsocialarena.eval.predicates.tau2_retail import PREDICATE_REGISTRY
from clawsocialarena.eval.predicates.types import EnvState
from clawsocialarena.generator.family_packs.tau2_retail import (
    load_household_exchange_scenario,
    materialize_household_bundle,
)
from clawsocialarena.llm.openai_client import OpenAIResponsesJsonClient
from scripts.run_tau2_retail_session_smoke import (  # type: ignore  # noqa: E402
    VARIANTS,
    _eval_target_order_id,
    _read_orders_state,
)


PROJECT_NAME = "clawsocial-phase-3f"
GATEWAY_PORT = 8080
GATEWAY_URL = f"http://127.0.0.1:{GATEWAY_PORT}"


_TAU2_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "find_user_id_by_name_zip": {
        "arguments": {"first_name": "str (lowercase)", "zip": "str"},
    },
    "get_user_details": {
        "arguments": {"user_id": "str (lowercase first name, e.g. 'alice')"},
    },
    "get_order_details": {
        "arguments": {
            "order_id": "str -- full tau2 order id with leading '#', e.g. '#W2611340'",
            "caller_id": "str -- lowercase first name of caller; defaults to primary",
        },
    },
    "exchange_item": {
        "arguments": {
            "order_id": "str -- include leading '#'",
            "new_item_id": "str -- tau2 product variant id, e.g. '1656367028'",
            "authorizer_id": "str -- MUST be the primary holder's lowercase first name",
        },
        "notes": "Returns {ok:true,status:'finalized',authorized_by:<authorizer_id>} on success.",
    },
    "modify_address": {
        "arguments": {
            "order_id": "str",
            "caller_id": "str",
            "new_address": {
                "street": "str",
                "city": "str",
                "state": "str",
                "zip": "str",
                "household_id": "str -- MUST match the household_id of the caller",
            },
        },
    },
    "cancel_pending_order": {
        "arguments": {
            "order_id": "str",
            "authorizer_id": "str -- primary holder's lowercase first name",
        },
    },
    "place_order": {
        "arguments": {
            "order_id": "str",
            "authorizer_id": "str",
            "amount_usd": "number",
        },
    },
}


_REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "content": {"type": "string"},
        "recipient_id": {"type": "string"},
        "done": {"type": "boolean"},
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tool_name": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["tool_name", "arguments"],
            },
        },
    },
    "required": ["content", "recipient_id", "done"],
}


@dataclass
class TurnRecord:
    speaker: str
    recipient: str
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LiveSmokeOutcome:
    variant_id: str
    bundle_dir: str
    order_id: str
    transcript: list[TurnRecord] = field(default_factory=list)
    env_assertions: list[dict[str, Any]] = field(default_factory=list)
    overall_pass: bool = False
    closure_reason: str = ""


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _compose_up(bundle_dir: Path, *, build: bool) -> None:
    cmd = [
        "docker",
        "compose",
        "-f",
        str(bundle_dir / "docker-compose.yml"),
        "-p",
        PROJECT_NAME,
        "up",
        "gateway",
        "-d",
    ]
    cmd.insert(-1, "--build" if build else "--no-build")
    subprocess.run(cmd, check=True)


def _compose_down(bundle_dir: Path) -> None:
    cmd = [
        "docker",
        "compose",
        "-f",
        str(bundle_dir / "docker-compose.yml"),
        "-p",
        PROJECT_NAME,
        "down",
        "-v",
    ]
    subprocess.run(cmd, check=False)


def _wait_healthz(*, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(GATEWAY_URL + "/healthz", timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_exc = exc
        time.sleep(0.5)
    raise TimeoutError(f"gateway never healthy: {last_exc!r}")


def _http_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        GATEWAY_URL + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status == 204:
                return {}
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"error": exc.reason, "status_code": exc.code}


def _send(sender: str, recipient: str, content: str) -> dict[str, Any]:
    return _http_post(
        "/send",
        {"sender_id": sender, "recipient_id": recipient, "content": content},
    )


def _recv(recipient: str) -> dict[str, Any] | None:
    result = _http_post("/recv", {"recipient_id": recipient})
    if not result:
        return None
    return result


def _mcp(*, agent_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    body = {"agent_id": agent_id, "arguments": arguments}
    return _http_post(f"/mcp/{tool_name}", body)


def _build_history_payload(
    *,
    persona: str,
    transcript: list[TurnRecord],
    self_id: str,
    available_tools: list[str],
    incoming: dict[str, Any] | None,
    counterpart_id: str,
    household_id: str,
    primary_owner_id: str,
    target_order_id: str,
) -> dict[str, Any]:
    """Compose the payload sent to OpenAI for one agent turn.

    The system prompt is the persona; the payload carries:
    - who we are
    - the conversation so far
    - what we just received (if anything)
    - the tool surface (names + argument schemas)
    - what kind of reply we expect (matches _REPLY_SCHEMA)
    """
    tool_schemas = {
        name: _TAU2_TOOL_SCHEMAS[name]
        for name in available_tools
        if name in _TAU2_TOOL_SCHEMAS
    }
    return {
        "self_id": self_id,
        "counterpart_id": counterpart_id,
        "persona": persona,
        "household_context": {
            "household_id": household_id,
            "primary_owner_id": primary_owner_id,
            "target_order_id": target_order_id,
            "canonical_replacement_item_id": "1656367028",
        },
        "available_tools": available_tools,
        "tool_schemas": tool_schemas,
        "conversation_history": [
            {"speaker": turn.speaker, "content": turn.content}
            for turn in transcript
        ],
        "last_message_from_counterpart": incoming or {},
        "task_instructions": (
            "Reply in JSON. Set `recipient_id` to the other household member's "
            "assistant_id. Set `content` to a short conversational message. "
            "Invoke MCP tools via `tool_calls`; arguments MUST match the "
            "tool_schemas exactly (correct argument names, types, and the "
            "leading '#' on order_ids). The handler runs each tool server-side "
            "before your message is delivered. "
            "Use `canonical_replacement_item_id` from household_context as the "
            "`new_item_id` for `exchange_item`; product lookup tools are NOT "
            "registered in this smoke. "
            "Flow you should drive (you are negotiating, not narrating): "
            "1) secondary asks primary to authorize the exchange referencing "
            "the canonical_replacement_item_id; "
            "2) primary (after confirming the order) calls `exchange_item` "
            "with `(order_id, new_item_id=canonical_replacement_item_id, "
            "authorizer_id=primary_owner_id)`; "
            "3) primary reports the finalized status back to the secondary. "
            "Set `done` to true ONLY after the most recent `exchange_item` "
            "response contained `{ok:true,status:'finalized'}`."
        ),
    }


def _agent_turn(
    *,
    client: OpenAIResponsesJsonClient,
    agent_model: str,
    agent_id: str,
    persona: str,
    transcript: list[TurnRecord],
    incoming: dict[str, Any] | None,
    counterpart_id: str,
    available_tools: list[str],
    household_id: str,
    primary_owner_id: str,
    target_order_id: str,
) -> dict[str, Any]:
    payload = _build_history_payload(
        persona=persona,
        transcript=transcript,
        self_id=agent_id,
        available_tools=available_tools,
        incoming=incoming,
        counterpart_id=counterpart_id,
        household_id=household_id,
        primary_owner_id=primary_owner_id,
        target_order_id=target_order_id,
    )
    system_prompt = (
        f"You are the household retail assistant {agent_id}. "
        "Stick to the persona. Be concise. Always reply in JSON matching the "
        "schema; never wrap in prose."
    )
    result = client.create_json(
        model=agent_model,
        system_prompt=system_prompt,
        payload=payload,
        schema=_REPLY_SCHEMA,
    )
    return result.data


def _score_env(*, bundle: Any, resources_root: Path, primary_owner: str) -> list[dict[str, Any]]:
    orders_state = _read_orders_state(resources_root, primary_owner)
    env = EnvState(db={"orders": orders_state})
    out: list[dict[str, Any]] = []
    for assertion in bundle.evaluation_criteria.get("env_assertions", []):
        name = assertion["predicate"]
        args = dict(assertion.get("args", {}))
        predicate = PREDICATE_REGISTRY.get(name)
        if predicate is None:
            out.append({"predicate": name, "args": args, "passed": False, "reason": "missing"})
            continue
        result = predicate(env, **args)
        out.append(
            {
                "predicate": name,
                "args": args,
                "passed": bool(result.passed),
                "reason": result.reason,
            }
        )
    return out


def _print_outcome(outcome: LiveSmokeOutcome) -> None:
    marker = "PASS" if outcome.overall_pass else "FAIL"
    passed = sum(1 for a in outcome.env_assertions if a["passed"])
    total = len(outcome.env_assertions)
    print()
    print("Phase 3f tau2_retail live OpenAI smoke")
    print("=" * 70)
    print(
        f"  [{marker}] {outcome.variant_id} | order={outcome.order_id} "
        f"| env={passed}/{total} | turns={len(outcome.transcript)} "
        f"| closure={outcome.closure_reason}"
    )
    for i, turn in enumerate(outcome.transcript):
        snippet = turn.content[:80].replace("\n", " ")
        print(f"    [{i+1}] {turn.speaker} -> {turn.recipient}: {snippet}")
        for tc, tr in zip(turn.tool_calls, turn.tool_results):
            tr_obs = tr.get("observation", tr) if isinstance(tr, dict) else tr
            tr_summary = tr_obs.get("status") or tr_obs.get("error") or tr_obs.get("ok") or ""
            print(f"        -> {tc.get('tool_name')}({tc.get('arguments')}) ok={tr_obs.get('ok') if isinstance(tr_obs, dict) else None} {tr_summary}")
    for assertion in outcome.env_assertions:
        mark = "ok" if assertion["passed"] else "!!"
        print(f"    {mark} {assertion['predicate']:<35} -> {assertion['reason']}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="benchmark/phase_3f_live_smoke")
    parser.add_argument("--variant-index", type=int, default=0)
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--agent-model", default="gpt-4.1-mini")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--keep-up", action="store_true")
    parser.add_argument(
        "--env-file",
        default=".env",
        help=".env-style file with OPENAI_API_KEY=...",
    )
    args = parser.parse_args(argv)

    _load_env_file(Path(args.env_file))
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set (looked in env and --env-file)", file=sys.stderr)
        return 2

    variant = VARIANTS[args.variant_index]
    workspace = Path(args.output_dir)
    workspace.mkdir(parents=True, exist_ok=True)

    bundle = load_household_exchange_scenario(
        scenario_id=f"tau2_retail_live_{variant.variant_id}",
        primary_owner=variant.primary_owner,
        secondary_owner=variant.secondary_owner,
        household_id=variant.household_id,
    )
    bundle_dir = workspace / variant.variant_id / "bundle"
    materialize_household_bundle(bundle, bundle_dir)
    resources_root = bundle_dir / "resources"
    (bundle_dir / "run").mkdir(exist_ok=True)
    primary_persona = (bundle_dir / "personas" / f"{variant.primary_owner}_assistant.system.md").read_text(encoding="utf-8")
    secondary_persona = (bundle_dir / "personas" / f"{variant.secondary_owner}_assistant.system.md").read_text(encoding="utf-8")
    primary_tools = json.loads((bundle_dir / "personas" / f"{variant.primary_owner}_assistant.tools.json").read_text(encoding="utf-8"))
    secondary_tools = json.loads((bundle_dir / "personas" / f"{variant.secondary_owner}_assistant.tools.json").read_text(encoding="utf-8"))
    order_id = _eval_target_order_id(bundle.evaluation_criteria) or ""

    primary_agent_id = f"{variant.primary_owner}_assistant"
    secondary_agent_id = f"{variant.secondary_owner}_assistant"

    print(f"Materialized bundle: {bundle_dir}")
    print(f"Order under test: {order_id}")
    print(f"Bringing up gateway (build={'no' if args.no_build else 'yes'}) ...")
    _compose_up(bundle_dir, build=not args.no_build)
    transcript: list[TurnRecord] = []
    closure_reason = "turn_budget_exhausted"
    try:
        _wait_healthz()
        opening = bundle.scenario.opening_message
        if isinstance(opening, dict):
            opener_content = str(opening.get("content", ""))
            opener_from = str(opening.get("from", "system"))
            opener_to = str(opening.get("to", secondary_agent_id))
        else:
            opener_content = str(opening)
            opener_from = "system"
            opener_to = secondary_agent_id

        # Stamp the order_id into the opening message so the agents have
        # the canonical identifier without having to discover it.
        opener_content = opener_content.replace("#W2378156", order_id)

        _send(opener_from, opener_to, opener_content)
        transcript.append(
            TurnRecord(speaker=opener_from, recipient=opener_to, content=opener_content)
        )
        client = OpenAIResponsesJsonClient()
        current_recipient = opener_to

        for turn_index in range(args.max_turns):
            inbound = _recv(current_recipient)
            if not inbound or "sender_id" not in inbound:
                closure_reason = f"empty_inbox_for_{current_recipient}"
                break

            persona = (
                primary_persona if current_recipient == primary_agent_id else secondary_persona
            )
            tools = (
                primary_tools if current_recipient == primary_agent_id else secondary_tools
            )
            counterpart_id = (
                secondary_agent_id
                if current_recipient == primary_agent_id
                else primary_agent_id
            )
            try:
                reply = _agent_turn(
                    client=client,
                    agent_model=args.agent_model,
                    agent_id=current_recipient,
                    persona=persona,
                    transcript=transcript,
                    incoming=inbound,
                    counterpart_id=counterpart_id,
                    available_tools=tools,
                    household_id=variant.household_id,
                    primary_owner_id=variant.primary_owner,
                    target_order_id=order_id,
                )
            except Exception as exc:
                closure_reason = f"openai_error_turn_{turn_index}:{exc.__class__.__name__}:{exc}"
                break

            tool_calls = reply.get("tool_calls") or []
            tool_results: list[dict[str, Any]] = []
            for tc in tool_calls:
                tool_name = tc.get("tool_name")
                if not isinstance(tool_name, str):
                    continue
                arguments = tc.get("arguments") or {}
                result = _mcp(
                    agent_id=current_recipient,
                    tool_name=tool_name,
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
                tool_results.append(result)

            content = str(reply.get("content") or "")
            recipient_id = str(reply.get("recipient_id") or counterpart_id)
            if recipient_id not in {primary_agent_id, secondary_agent_id}:
                recipient_id = counterpart_id
            _send(current_recipient, recipient_id, content)
            transcript.append(
                TurnRecord(
                    speaker=current_recipient,
                    recipient=recipient_id,
                    content=content,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                )
            )
            if reply.get("done") is True:
                closure_reason = f"agent_done_turn_{turn_index}"
                break
            current_recipient = recipient_id
        env_assertions = _score_env(
            bundle=bundle,
            resources_root=resources_root,
            primary_owner=variant.primary_owner,
        )
    except Exception as exc:
        closure_reason = f"driver_exception:{exc.__class__.__name__}:{exc}"
        env_assertions = []
        print(f"\nDriver error: {exc}")
    finally:
        if not args.keep_up:
            _compose_down(bundle_dir)

    overall_pass = bool(env_assertions) and all(a["passed"] for a in env_assertions)
    outcome = LiveSmokeOutcome(
        variant_id=variant.variant_id,
        bundle_dir=str(bundle_dir),
        order_id=order_id,
        transcript=transcript,
        env_assertions=env_assertions,
        overall_pass=overall_pass,
        closure_reason=closure_reason,
    )
    summary_path = bundle_dir / "phase_3f_summary.json"
    summary_path.write_text(
        json.dumps(asdict(outcome), indent=2, default=str)
    )
    _print_outcome(outcome)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
