// ClawSocialArena OpenClaw channel plugin.
//
// The `plugin` export satisfies OpenClaw's `ChannelPlugin` contract
// (`openclaw/plugin-sdk/channel-core`). The default export is the
// OpenClaw extension entry that registers that channel at runtime.
//
// The `config.resolveAccount` returns a minimal arena account record
// so SDK code that expects `accountId` on the resolved account gets a
// stable value; richer typing (e.g. per-account gateway URLs) will come
// with the arena config schema in later phases.

import type { ChannelPlugin } from 'openclaw/plugin-sdk/channel-core';
import type { OpenClawPluginApi } from 'openclaw/plugin-sdk/core';
// Side-effect-free type-only import from the contract subpath to make sure
// the SDK surface is reachable.
import type {} from 'openclaw/plugin-sdk/channel-contract';

import { createChannel, type Channel, type ChannelOptions } from './channel.js';

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
} from './gateway-client.js';
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
} from './gateway-client.js';
export { createChannel } from './channel.js';
export type { Channel, ChannelOptions } from './channel.js';

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
// registered for the resolved account we fail closed: the plugin is
// the sole egress path for the arena, so a missing channel means we
// have no way to audit the send, and silently inventing a fake message
// id would let the outbound leak past the audit layer. Callers (the
// OpenClaw SDK, A14 E2E, arena runtime) must register a channel via
// ``plugin.start({accountId, ...})`` before the SDK invokes
// ``outbound.sendText``.
async function routeOutbound(params: {
  accountId?: string | null;
  to: string;
  text: string;
}): Promise<OutboundDeliveryResult> {
  const key = params.accountId ?? '';
  const channel = channels.get(key);
  if (!channel) {
    throw new Error(
      `ClawSocialArena gateway plugin: no channel registered for account ${
        key || '<empty>'
      }; refusing to pretend the outbound succeeded`,
    );
  }
  const actionId = await channel.handleOutboundSend({
    to: params.to,
    text: params.text,
    accountId: params.accountId ?? null,
  });
  // ``handleOutboundSend`` returns the gateway's action_id on success.
  // It is ``null`` only under BASELINE (gateway has no audit substrate);
  // we surface a deterministic sentinel so the SDK has a stable
  // ``messageId`` but never a fake one. BASELINE is an explicit opt-in
  // condition, not a missing-channel fallback.
  return {
    channel: 'clawsocial',
    messageId: actionId ?? 'clawsocial-baseline',
    meta: {
      registered: true,
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

interface ClawSocialEntry {
  id: string;
  name: string;
  description: string;
  configSchema: { schema: Record<string, unknown> };
  register: (api: OpenClawPluginApi) => void;
  channelPlugin: ChannelPlugin<ArenaAccount>;
}

export const entry: ClawSocialEntry = {
  id: 'clawsocial',
  name: 'ClawSocialArena',
  description:
    'ClawSocialArena research channel: routes OpenClaw outbound/inbound traffic through the Python audit gateway.',
  configSchema: {
    schema: {
      type: 'object',
      additionalProperties: false,
      properties: {},
    },
  },
  register(api) {
    api.registerChannel({ plugin });
  },
  channelPlugin: plugin,
};

export default entry;
