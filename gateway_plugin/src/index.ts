// ClawSocialArena OpenClaw channel plugin.
// Exports the plugin entry expected by OpenClaw's plugin SDK channel contract.
// Full channel and gateway-client implementations land in Tasks A8 and A9.
//
// Note: the `ChannelPlugin` type is exported from `openclaw/plugin-sdk/channel-core`.
// The `openclaw/plugin-sdk/channel-contract` subpath only re-exports adapter
// and message-action types. We therefore pull `ChannelPlugin` from
// `channel-core`; the contract subpath is imported below purely to assert
// that the adapter surface remains available to plugin authors.

import type { ChannelPlugin } from 'openclaw/plugin-sdk/channel-core';
// Side-effect-free type-only import from the contract subpath to make sure
// the SDK surface is reachable. Actual adapter wiring lands in A8/A9.
import type {} from 'openclaw/plugin-sdk/channel-contract';

// TODO(A8/A9): the fields below are minimal scaffold stubs that satisfy the
// `ChannelPlugin` type contract. They do not implement any real behavior.
// Replace with real wiring once the channel and gateway-client layers land.
export const plugin: ChannelPlugin = {
  id: 'clawsocial',
  meta: {
    id: 'clawsocial',
    label: 'ClawSocialArena',
    selectionLabel: 'ClawSocialArena',
    docsPath: 'docs/channels/clawsocial.md',
    blurb: 'ClawSocialArena research channel (scaffold only; wired in A8/A9).',
  },
  capabilities: {
    chatTypes: ['direct'],
  },
  config: {
    // TODO(A8): populate from arena config once the channel layer lands.
    listAccountIds: () => [],
    // TODO(A8): resolve the per-account record from OpenClawConfig.
    resolveAccount: () => ({}),
  },
};

export default plugin;
