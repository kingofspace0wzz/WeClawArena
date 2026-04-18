// ClawSocialArena OpenClaw channel plugin.
// Exports the plugin entry expected by OpenClaw's plugin SDK channel contract,
// plus the HTTP gateway-client surface used by the channel plugin (Task A8).
// Channel adapter wiring lands in Task A9.
//
// Note: the `ChannelPlugin` type is exported from `openclaw/plugin-sdk/channel-core`.
// The `openclaw/plugin-sdk/channel-contract` subpath only re-exports adapter
// and message-action types. We therefore pull `ChannelPlugin` from
// `channel-core`; the contract subpath is imported below purely to assert
// that the adapter surface remains available to plugin authors.

import type { ChannelPlugin } from 'openclaw/plugin-sdk/channel-core';
// Side-effect-free type-only import from the contract subpath to make sure
// the SDK surface is reachable. Actual adapter wiring lands in A9.
import type {} from 'openclaw/plugin-sdk/channel-contract';

// Re-export the HTTP gateway client so A9 can import it from the plugin
// package root rather than reaching into `./gateway-client` directly.
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

// TODO(A9): the fields below are minimal scaffold stubs that satisfy the
// `ChannelPlugin` type contract. They do not implement any real behavior.
// Replace with real wiring once the channel adapter layer lands.
// TODO(A9): tighten to ChannelPlugin<ArenaAccount> once the account shape lands.
export const plugin: ChannelPlugin = {
  id: 'clawsocial',
  meta: {
    id: 'clawsocial',
    label: 'ClawSocialArena',
    selectionLabel: 'ClawSocialArena',
    docsPath: 'docs/channels/clawsocial.md',
    blurb: 'ClawSocialArena research channel (scaffold only; wired in A9).',
  },
  capabilities: {
    chatTypes: ['direct'],
  },
  config: {
    // TODO(A9): populate from arena config once the channel layer lands.
    listAccountIds: () => [],
    // TODO(A9): resolve the per-account record from OpenClawConfig.
    resolveAccount: () => ({} as never),
  },
};

export default plugin;
