import { describe, it, expect } from 'vitest';
import entry, { plugin, plugin as named } from '../src/index';
// `ChannelPlugin` lives in `openclaw/plugin-sdk/channel-core`.
// The `channel-contract` subpath only re-exports adapter types, so we verify
// type conformance against the canonical export here.
import type { ChannelPlugin } from 'openclaw/plugin-sdk/channel-core';

describe('clawsocial plugin scaffold', () => {
  it('exports the OpenClaw extension entry as the default export', () => {
    expect(entry.id).toBe('clawsocial');
    expect(entry.register).toBeTypeOf('function');
    expect(entry.channelPlugin).toBe(plugin);
  });

  it('exports a named plugin for direct channel tests', () => {
    expect(named).toBe(plugin);
  });

  it('declares a stable id', () => {
    expect(plugin.id).toBe('clawsocial');
  });

  it('satisfies the ChannelPlugin type', () => {
    const typed: ChannelPlugin = plugin;
    expect(typed).toBeDefined();
  });
});
