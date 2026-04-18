// ClawSocialArena OpenClaw channel plugin.
//
// The `plugin` export satisfies OpenClaw's `ChannelPlugin` contract
// (`openclaw/plugin-sdk/channel-core`). A9 wires the minimum surface
// needed for agent-initiated sends to reach the Python audit gateway:
// the SDK's `outbound.sendText` adapter is routed through a lazily
// constructed per-agent `Channel` (see `./channel.ts`). Inbound polling
// and tool-call reporting live on the channel instance itself, which
// A10/A14 will start via the plugin's `start(...)` helper because
// OpenClaw's external-plugin surface does not guarantee a single
// account-lifecycle hook that fires before outbound sends for every
// runtime shape.
//
// The `config.resolveAccount` returns a minimal arena account record
// so SDK code that expects `accountId` on the resolved account gets a
// stable value; richer typing (e.g. per-account gateway URLs) will come
// with the arena config schema in later phases.

import type { ChannelPlugin } from 'openclaw/plugin-sdk/channel-core';
// Side-effect-free type-only import from the contract subpath to make sure
// the SDK surface is reachable.
import type {} from 'openclaw/plugin-sdk/channel-contract';

import { createChannel, type Channel, type ChannelOptions } from './channel';

// The SDK publishes `OutboundDeliveryResult` only through its internal
// path `openclaw/dist/plugin-sdk/src/infra/outbound/deliver-types.d.ts`,
// and not as a re-export from `openclaw/plugin-sdk/channel-core`. We
// derive the type from the outbound adapter contract so this plugin
// does not need to import from an internal subpath.
type OutboundSendTextReturn = NonNullable<
  NonNullable<ChannelPlugin['outbound']>['sendText']
>;
type OutboundDeliveryResult = Awaited<ReturnType<OutboundSendTextReturn>>;

// Re-export the HTTP gateway client so downstream tasks can import it
// from the plugin package root.
export {
  GatewayClient,
  GatewayClientError,
  UnknownToolError,
} from './gateway-client';
export type {
  GatewayClientOptions,
  SendBody,
  Inbound,
  ToolCallBody,
  ToolObservationBody,
  MemoryWriteBody,
  LlmCallBody,
  McpCallBody,
  McpCallResponse,
} from './gateway-client';
export { createChannel } from './channel';
export type { Channel, ChannelOptions } from './channel';

// Shape returned by `config.resolveAccount`. We keep it minimal — the
// arena only needs the account id today — and widen it in later phases
// when per-account gateway credentials are introduced.
interface ArenaAccount {
  accountId: string;
}

// Process-lifetime registry of per-agent `Channel` instances. We key on
// `accountId` because OpenClaw identifies the sender of an outbound
// message via the resolved account; A10/A14 register each arena agent
// here by calling `plugin.start({accountId, agentId, baseUrl, ...})`.
const channels = new Map<string, Channel>();

// Non-enumerable helper so `plugin.start(...)` can be invoked without
// accidentally appearing as a `ChannelPlugin` field the SDK would try
// to consume.
function attachNonEnumerable<T extends object>(target: T, key: string, value: unknown): T {
  Object.defineProperty(target, key, {
    value,
    enumerable: false,
    configurable: true,
    writable: true,
  });
  return target;
}

// Outbound stub used by the SDK's `outbound.sendText` hook. The actual
// HTTP send happens through the per-agent `Channel`. If no channel is
// registered for the resolved account we synthesize a deterministic
// fallback so the SDK does not crash (A14 E2E will tighten this to a
// hard failure once Docker wiring is in place).
async function routeOutbound(params: {
  accountId?: string | null;
  to: string;
  text: string;
}): Promise<OutboundDeliveryResult> {
  const key = params.accountId ?? '';
  const channel = channels.get(key);
  const messageId = channel
    ? (await channel.handleOutboundSend({
        to: params.to,
        text: params.text,
        accountId: params.accountId ?? null,
      })) ?? 'clawsocial-no-action-id'
    : 'clawsocial-no-channel';
  return {
    channel: 'clawsocial',
    messageId,
    meta: {
      // `registered` lets tests and A14 E2E confirm the channel was
      // resolved rather than the fallback path being taken.
      registered: Boolean(channel),
    },
  };
}

const pluginObject: ChannelPlugin<ArenaAccount> = {
  id: 'clawsocial',
  meta: {
    id: 'clawsocial',
    label: 'ClawSocialArena',
    selectionLabel: 'ClawSocialArena',
    docsPath: 'docs/channels/clawsocial.md',
    blurb:
      'ClawSocialArena research channel: routes OpenClaw outbound/inbound traffic through the Python audit gateway.',
  },
  capabilities: {
    chatTypes: ['direct'],
  },
  config: {
    // Arena config surfaces one account per run; A10 lifts this into a
    // real lookup driven by `OpenClawConfig`.
    listAccountIds: () => Array.from(channels.keys()),
    resolveAccount: (_cfg, accountId) => ({
      accountId: accountId ?? '',
    }),
  },
  outbound: {
    deliveryMode: 'direct',
    sendText: async (ctx) => {
      return routeOutbound({
        accountId: ctx.accountId ?? null,
        to: ctx.to,
        text: ctx.text,
      });
    },
  },
};

export const plugin = pluginObject;
export default plugin;

// Imperative helpers so A10/A14 orchestration code can register/teardown
// per-agent channels without needing to touch SDK internals.
export interface StartOptions extends ChannelOptions {
  // The OpenClaw `accountId` used to look the channel back up when the
  // SDK calls `outbound.sendText`. Defaults to `agentId` so
  // single-agent runs can omit it.
  accountId?: string;
  // If true, also calls `channel.start()` to begin inbound polling.
  // Defaults to true; A14 Docker tests can opt out when they want to
  // drive `/recv` manually.
  autoStartPolling?: boolean;
}

export async function startChannel(opts: StartOptions): Promise<Channel> {
  const key = opts.accountId ?? opts.agentId;
  const channel = createChannel(opts);
  channels.set(key, channel);
  if (opts.autoStartPolling !== false) {
    channel.start();
  }
  return channel;
}

export async function stopChannel(accountId: string): Promise<void> {
  const channel = channels.get(accountId);
  if (!channel) return;
  await channel.stop();
  channels.delete(accountId);
}

export function getChannel(accountId: string): Channel | undefined {
  return channels.get(accountId);
}

// `plugin.start(...)` / `plugin.stop(...)` mirror the exported helpers
// so callers that only hold the `plugin` object can still drive the
// lifecycle. They live as non-enumerable properties to avoid leaking
// into the `ChannelPlugin` keyspace.
attachNonEnumerable(plugin, 'start', startChannel);
attachNonEnumerable(plugin, 'stop', stopChannel);
attachNonEnumerable(plugin, 'getChannel', getChannel);
