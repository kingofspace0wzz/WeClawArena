import { describe, it, expect } from 'vitest';
import plugin, { plugin as named } from '../src/index';
// `ChannelPlugin` lives in `openclaw/plugin-sdk/channel-core`.
// The `channel-contract` subpath only re-exports adapter types, so we verify
// type conformance against the canonical export here.
import type { ChannelPlugin } from 'openclaw/plugin-sdk/channel-core';

describe('clawsocial plugin scaffold', () => {
  it('exports a default and a named plugin that are the same object', () => {
    expect(plugin).toBe(named);
  });

  it('declares a stable id', () => {
    expect(plugin.id).toBe('clawsocial');
  });

  it('satisfies the ChannelPlugin type', () => {
    const typed: ChannelPlugin = plugin;
    expect(typed).toBeDefined();
  });
});
