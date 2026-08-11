// WeClawArena OpenClaw channel: arena-owned bridge between the
// OpenClaw plugin SDK and the Python audit gateway.
//
// OpenClaw's channel contract exposes a rich set of adapters (see
// `openclaw/plugin-sdk/channel-core`). For WeClawArena we only need
// a small subset; the mapping is:
//
//   * outbound.sendText  ->  GatewayClient.send({sender_id, recipient_id, content})
//                            keyed off ChannelOutboundContext { to, text, accountId }.
//                            We treat `accountId` (falling back to the
//                            factory's `agentId`) as `sender_id`.
//   * gateway.startAccount -> begin /recv polling every `pollMs` (default 250).
//   * gateway.stopAccount  -> clear the polling timer.
//   * inbound delivery    -> we hand messages to the factory's `onInbound`
//                            callback; a14 Docker E2E will replace this
//                            with a real SDK inbox push once the full
//                            runtime is attached. OpenClaw's SDK does not
//                            publish a standalone inbound-push type for
//                            external plugins at compile time.
//   * tool-call reporting -> the factory exposes `reportToolCall(...)`
//                            which A10/A14 wiring (agent loop + plugin
//                            hooks) invokes around each tool invocation;
//                            there is no top-level `ChannelPlugin` hook
//                            that fires on every agent tool call.
//
// Anything the SDK expects that is not listed above is left unset; the
// existing `ChannelConfigAdapter` stub in `./index.ts` keeps the plugin
// type-conformant without claiming behavior we do not implement.

import {
  GatewayClient,
  type GatewayClientOptions,
  type Inbound,
  type ToolCallBody,
} from './gateway-client.js';

export interface ChannelOptions {
  baseUrl: string;
  agentId: string;
  pollMs?: number;
  fetchImpl?: typeof fetch;
  onInbound?: (msg: Inbound) => void | Promise<void>;
  // Hook for pluggable error reporting during the poll loop. Defaults to
  // a silent no-op so a transient /recv failure (e.g. gateway restart)
  // does not crash the agent process. A14 can swap in structured logging.
  onPollError?: (err: unknown) => void;
}

export interface OutboundMessage {
  from: string;
  to: string;
  body: string;
}

export interface ReportToolCallInput {
  tool_name: string;
  arguments: Record<string, unknown>;
}

export interface Channel {
  readonly client: GatewayClient;
  readonly agentId: string;
  sendMessage(message: OutboundMessage): Promise<string | null>;
  reportToolCall(input: ReportToolCallInput): Promise<string | null>;
  start(): void;
  stop(): Promise<void>;
  // Exposed so `src/index.ts` can wire the factory into OpenClaw's
  // `outbound.sendText` hook without re-implementing the mapping.
  handleOutboundSend(params: {
    to: string;
    text: string;
    accountId?: string | null;
  }): Promise<string | null>;
}

const DEFAULT_POLL_MS = 250;

export function createChannel(opts: ChannelOptions): Channel {
  const clientOpts: GatewayClientOptions = {
    baseUrl: opts.baseUrl,
    fetchImpl: opts.fetchImpl,
  };
  const client = new GatewayClient(clientOpts);
  const pollMs = opts.pollMs ?? DEFAULT_POLL_MS;
  const agentId = opts.agentId;

  // We use a self-scheduling `setTimeout` loop rather than `setInterval`
  // so overlapping ticks cannot pile up while a slow /recv is in flight.
  // `running` guards the scheduler; `currentTimer` lets `stop()` clear
  // any pending wakeup, and `activePoll` lets `stop()` wait for an
  // in-flight request to settle before returning.
  let running = false;
  let currentTimer: ReturnType<typeof setTimeout> | null = null;
  let activePoll: Promise<void> | null = null;

  async function pollOnce(): Promise<void> {
    try {
      const inbound = await client.recv(agentId);
      if (inbound && opts.onInbound) {
        await opts.onInbound(inbound);
      }
    } catch (err) {
      if (opts.onPollError) {
        opts.onPollError(err);
      }
    }
  }

  function scheduleNext(): void {
    if (!running) return;
    currentTimer = setTimeout(() => {
      currentTimer = null;
      if (!running) return;
      activePoll = pollOnce().finally(() => {
        activePoll = null;
        scheduleNext();
      });
    }, pollMs);
  }

  function start(): void {
    if (running) return;
    running = true;
    // First tick is scheduled the same way subsequent ticks are so the
    // initial burst does not race ahead of a freshly started server.
    scheduleNext();
  }

  async function stop(): Promise<void> {
    running = false;
    if (currentTimer) {
      clearTimeout(currentTimer);
      currentTimer = null;
    }
    // If a fetch is in flight, let it resolve so callers do not see
    // hanging promises after `stop()` returns.
    if (activePoll) {
      await activePoll.catch(() => {
        /* poll errors already routed through onPollError */
      });
    }
  }

  async function sendMessage(message: OutboundMessage): Promise<string | null> {
    return client.send({
      sender_id: message.from,
      recipient_id: message.to,
      content: message.body,
    });
  }

  async function reportToolCall(
    input: ReportToolCallInput,
  ): Promise<string | null> {
    const body: ToolCallBody = {
      agent_id: agentId,
      tool_name: input.tool_name,
      arguments: input.arguments,
    };
    return client.recordToolCall(body);
  }

  async function handleOutboundSend(params: {
    to: string;
    text: string;
    accountId?: string | null;
  }): Promise<string | null> {
    // OpenClaw's `ChannelOutboundContext` separates the routing target
    // (`to`) from the sending account (`accountId`). The arena runtime
    // identifies the sending agent by `accountId`; when absent (e.g.
    // single-account default config) we fall back to the factory's
    // `agentId` so the audit record never has an empty sender.
    const from = params.accountId ?? agentId;
    return sendMessage({ from, to: params.to, body: params.text });
  }

  return {
    client,
    agentId,
    sendMessage,
    reportToolCall,
    start,
    stop,
    handleOutboundSend,
  };
}
