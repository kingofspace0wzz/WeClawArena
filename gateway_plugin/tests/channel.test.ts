// Tests for the ClawSocialArena channel factory (Task A9).
//
// These tests use the same `http.createServer` pattern as
// `gateway-client.test.ts`: a local server on an ephemeral port with
// per-path canned responses, so the tests do not depend on msw or any
// network mock library. We do not extract the helper yet because the two
// files have different plan/response policies; when a third test file
// appears we should factor it out.
//
// The channel factory wraps `GatewayClient` and exposes the callbacks
// that OpenClaw's plugin SDK expects (the real SDK's outbound + gateway
// lifecycle hooks). The "OpenClaw hook" surface is wired in
// `src/index.ts`; these tests focus on the arena-owned behavior:
//   * outbound routing via `channel.sendMessage(...)`,
//   * inbound polling via `channel.start()` + `onInbound` callback,
//   * polling teardown on `channel.stop()`,
//   * tool-call reporting via `channel.reportToolCall(...)`.

import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import http from 'node:http';
import { AddressInfo } from 'node:net';

import { createChannel } from '../src/channel';
import plugin from '../src/index';
// `ChannelPlugin` lives in `openclaw/plugin-sdk/channel-core`.
import type { ChannelPlugin } from 'openclaw/plugin-sdk/channel-core';

interface CapturedRequest {
  method: string;
  url: string;
  body: unknown;
}

interface ResponsePlan {
  status: number;
  body?: unknown;
  // Sequenced plans (used for /recv polling tests): each request consumes
  // the next entry. Once exhausted, we fall through to `status`/`body`.
  sequence?: Array<{ status: number; body?: unknown }>;
}

let server: http.Server;
let baseUrl: string;
const captured: CapturedRequest[] = [];
const plans = new Map<string, ResponsePlan>();
const sequenceCursor = new Map<string, number>();

function planKey(method: string, pathname: string): string {
  return `${method} ${pathname}`;
}

function setPlan(method: string, pathname: string, plan: ResponsePlan): void {
  plans.set(planKey(method, pathname), plan);
  sequenceCursor.set(planKey(method, pathname), 0);
}

async function readBody(req: http.IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk) => chunks.push(Buffer.from(chunk)));
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      if (raw === '') {
        resolve(null);
        return;
      }
      try {
        resolve(JSON.parse(raw));
      } catch (err) {
        reject(err);
      }
    });
    req.on('error', reject);
  });
}

const openSockets = new Set<import('node:net').Socket>();

beforeAll(async () => {
  server = http.createServer(async (req, res) => {
    const url = req.url ?? '/';
    const method = req.method ?? 'GET';
    let body: unknown = null;
    try {
      body = await readBody(req);
    } catch {
      res.statusCode = 400;
      res.end('bad json');
      return;
    }
    captured.push({ method, url, body });

    const key = planKey(method, url);
    const plan = plans.get(key);
    if (!plan) {
      res.statusCode = 500;
      res.end(`no plan for ${method} ${url}`);
      return;
    }

    let resolved: { status: number; body?: unknown };
    if (plan.sequence && plan.sequence.length > 0) {
      const i = sequenceCursor.get(key) ?? 0;
      if (i < plan.sequence.length) {
        resolved = plan.sequence[i];
        sequenceCursor.set(key, i + 1);
      } else {
        resolved = { status: plan.status, body: plan.body };
      }
    } else {
      resolved = { status: plan.status, body: plan.body };
    }

    res.statusCode = resolved.status;
    if (resolved.body === undefined || resolved.body === null) {
      res.end();
      return;
    }
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify(resolved.body));
  });

  server.on('connection', (socket) => {
    openSockets.add(socket);
    socket.once('close', () => openSockets.delete(socket));
  });

  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve());
  });

  const addr = server.address() as AddressInfo;
  baseUrl = `http://127.0.0.1:${addr.port}`;
});

afterAll(async () => {
  for (const socket of openSockets) {
    socket.destroy();
  }
  openSockets.clear();
  await new Promise<void>((resolve, reject) => {
    server.close((err) => (err ? reject(err) : resolve()));
  });
});

beforeEach(() => {
  captured.length = 0;
  plans.clear();
  sequenceCursor.clear();
});

describe('createChannel.sendMessage', () => {
  it('maps {from,to,body} to the gateway /send payload', async () => {
    setPlan('POST', '/send', { status: 200, body: { action_id: 'x' } });
    const channel = createChannel({ baseUrl, agentId: 'alice' });
    const actionId = await channel.sendMessage({
      from: 'alice',
      to: 'bob',
      body: 'hello',
    });
    expect(actionId).toBe('x');
    expect(captured).toHaveLength(1);
    expect(captured[0].method).toBe('POST');
    expect(captured[0].url).toBe('/send');
    expect(captured[0].body).toEqual({
      sender_id: 'alice',
      recipient_id: 'bob',
      content: 'hello',
    });
  });
});

describe('createChannel.start / inbound polling', () => {
  it('delivers inbound messages via the onInbound callback', async () => {
    // First /recv returns a message, subsequent /recv calls return 204.
    setPlan('POST', '/recv', {
      status: 204,
      sequence: [
        { status: 200, body: { sender_id: 'carol', content: 'hi alice' } },
        { status: 204 },
      ],
    });
    const received: Array<{ sender_id: string; content: string }> = [];
    const channel = createChannel({
      baseUrl,
      agentId: 'alice',
      pollMs: 20,
      onInbound: (msg) => {
        received.push(msg);
      },
    });
    channel.start();
    // Wait long enough for at least one poll cycle and the onInbound
    // dispatch. 120ms covers ~6 poll ticks at 20ms, which is enough even
    // on a loaded CI runner without the test becoming flaky.
    await new Promise((r) => setTimeout(r, 120));
    await channel.stop();
    expect(received).toHaveLength(1);
    expect(received[0]).toEqual({ sender_id: 'carol', content: 'hi alice' });
    // First /recv body must include the agentId.
    const firstRecv = captured.find((c) => c.url === '/recv');
    expect(firstRecv?.body).toEqual({ recipient_id: 'alice' });
  });

  it('stops polling after stop() is called', async () => {
    setPlan('POST', '/recv', { status: 204 });
    const channel = createChannel({
      baseUrl,
      agentId: 'alice',
      pollMs: 20,
    });
    channel.start();
    // Let it tick a few times.
    await new Promise((r) => setTimeout(r, 80));
    await channel.stop();
    const countAtStop = captured.filter((c) => c.url === '/recv').length;
    // Wait another window and confirm no additional /recv requests arrive.
    await new Promise((r) => setTimeout(r, 80));
    const countAfterStop = captured.filter((c) => c.url === '/recv').length;
    expect(countAfterStop).toBe(countAtStop);
    // Sanity: we did actually poll at least once before stop.
    expect(countAtStop).toBeGreaterThan(0);
  });
});

describe('createChannel.reportToolCall', () => {
  it('forwards to the gateway /tool_call endpoint', async () => {
    setPlan('POST', '/tool_call', {
      status: 200,
      body: { action_id: 'tc-42' },
    });
    const channel = createChannel({ baseUrl, agentId: 'alice' });
    const actionId = await channel.reportToolCall({
      tool_name: 'search',
      arguments: { q: 'hello' },
    });
    expect(actionId).toBe('tc-42');
    expect(captured).toHaveLength(1);
    expect(captured[0].url).toBe('/tool_call');
    expect(captured[0].body).toEqual({
      agent_id: 'alice',
      tool_name: 'search',
      arguments: { q: 'hello' },
    });
  });
});

describe('plugin channel surface', () => {
  it('conforms to the OpenClaw ChannelPlugin type', () => {
    // Compile-time assignability check: if this assignment does not
    // typecheck, `npx pnpm -C gateway_plugin typecheck` will fail.
    const typed: ChannelPlugin = plugin;
    expect(typed).toBeDefined();
    // Outbound adapter wiring is the integration point the SDK calls for
    // agent-initiated sends; we assert it is populated by A9.
    expect(plugin.outbound).toBeDefined();
    expect(typeof plugin.outbound?.sendText).toBe('function');
  });

  it('throws when outbound.sendText fires without a registered channel', async () => {
    // Sole-egress invariant: the plugin must never invent a fake
    // messageId. If no channel has been registered via plugin.start(),
    // outbound.sendText must throw so the SDK / arena runtime surfaces
    // the misconfiguration rather than letting the send leak past the
    // audit gateway. Account id intentionally chosen to NOT match any
    // channel that might be left over from a prior test.
    await expect(
      plugin.outbound!.sendText!({
        accountId: 'unregistered-agent-xyz',
        to: 'bob',
        text: 'hello',
      } as Parameters<NonNullable<NonNullable<ChannelPlugin['outbound']>['sendText']>>[0]),
    ).rejects.toThrow(/no channel registered/i);
  });

  it('delivers via the registered channel after plugin.start()', async () => {
    // After a channel has been started, outbound.sendText routes the
    // message through the channel's gateway client and surfaces the
    // gateway's action_id as ``messageId``. This closes out the
    // fails-closed path by pinning the happy path behavior.
    setPlan('POST', '/send', {
      status: 200,
      body: { action_id: 'act-12345' },
    });

    type PluginWithStart = typeof plugin & {
      start: (opts: {
        agentId: string;
        accountId: string;
        baseUrl: string;
        autoStartPolling?: boolean;
      }) => Promise<unknown>;
      stop: (accountId: string) => Promise<void>;
    };
    const p = plugin as PluginWithStart;
    await p.start({
      agentId: 'alice',
      accountId: 'registered-alice',
      baseUrl,
      autoStartPolling: false,
    });
    try {
      const result = await plugin.outbound!.sendText!({
        accountId: 'registered-alice',
        to: 'bob',
        text: 'hello',
      } as Parameters<NonNullable<NonNullable<ChannelPlugin['outbound']>['sendText']>>[0]);
      expect(result.channel).toBe('clawsocial');
      expect(result.messageId).toBe('act-12345');
      expect(result.meta).toMatchObject({ registered: true });
    } finally {
      await p.stop('registered-alice');
    }
  });
});
