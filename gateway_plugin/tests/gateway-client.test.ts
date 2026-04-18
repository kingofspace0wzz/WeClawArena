// Tests for the HTTP gateway client. We stand up a local `http.createServer`
// bound to an ephemeral port and hand-route request URLs to canned responses
// so the test suite does not depend on msw or node-fetch. Node's built-in
// http module is all we need.

import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import http from 'node:http';
import { AddressInfo } from 'node:net';

import {
  GatewayClient,
  GatewayClientError,
  UnknownToolError,
} from '../src/gateway-client';

// Captured-request shape so tests can assert both the URL path and the decoded
// JSON body a handler received.
interface CapturedRequest {
  method: string;
  url: string;
  body: unknown;
}

// Per-path response plan. Handlers can defer sending the response (`delayMs`)
// to let the timeout test fire, and `passthrough` lets a handler synthesize
// its own response based on the captured body.
interface ResponsePlan {
  status: number;
  body?: unknown;
  delayMs?: number;
  passthrough?: (body: unknown) => { status: number; body?: unknown };
}

let server: http.Server;
let baseUrl: string;
const captured: CapturedRequest[] = [];
const plans = new Map<string, ResponsePlan>();

function planKey(method: string, pathname: string): string {
  return `${method} ${pathname}`;
}

function setPlan(method: string, pathname: string, plan: ResponsePlan): void {
  plans.set(planKey(method, pathname), plan);
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

// Track open sockets so the `afterAll` teardown can destroy them immediately.
// Without this, Node's http keep-alive holds each client socket open for its
// default timeout and `server.close()` stalls for several seconds waiting.
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

    const plan = plans.get(planKey(method, url));
    if (!plan) {
      res.statusCode = 500;
      res.end(`no plan for ${method} ${url}`);
      return;
    }

    if (plan.delayMs && plan.delayMs > 0) {
      // Defer the response past the client's configured timeout so the
      // AbortController path can be exercised. A reasonable ceiling keeps the
      // test suite snappy when the abort fires early.
      await new Promise((r) => setTimeout(r, plan.delayMs));
    }

    const resolved = plan.passthrough
      ? plan.passthrough(body)
      : { status: plan.status, body: plan.body };

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
});

describe('GatewayClient.send', () => {
  it('returns the action_id on success', async () => {
    setPlan('POST', '/send', { status: 200, body: { action_id: 'abc-123' } });
    const client = new GatewayClient({ baseUrl });
    const actionId = await client.send({
      sender_id: 'alice',
      recipient_id: 'bob',
      content: 'hello',
    });
    expect(actionId).toBe('abc-123');
    expect(captured).toHaveLength(1);
    expect(captured[0].method).toBe('POST');
    expect(captured[0].url).toBe('/send');
    expect(captured[0].body).toEqual({
      sender_id: 'alice',
      recipient_id: 'bob',
      content: 'hello',
    });
  });

  it('returns null when the baseline gateway returns null action_id', async () => {
    setPlan('POST', '/send', { status: 200, body: { action_id: null } });
    const client = new GatewayClient({ baseUrl });
    const actionId = await client.send({
      sender_id: 'alice',
      recipient_id: 'bob',
      content: 'hello',
    });
    expect(actionId).toBeNull();
  });
});

describe('GatewayClient.recv', () => {
  it('returns null on HTTP 204', async () => {
    setPlan('POST', '/recv', { status: 204 });
    const client = new GatewayClient({ baseUrl });
    const msg = await client.recv('bob');
    expect(msg).toBeNull();
    expect(captured[0].body).toEqual({ recipient_id: 'bob' });
  });

  it('returns the inbound message on HTTP 200', async () => {
    setPlan('POST', '/recv', {
      status: 200,
      body: { sender_id: 'alice', content: 'hi bob' },
    });
    const client = new GatewayClient({ baseUrl });
    const msg = await client.recv('bob');
    expect(msg).toEqual({ sender_id: 'alice', content: 'hi bob' });
  });

  it('throws on HTTP 400', async () => {
    setPlan('POST', '/recv', {
      status: 400,
      body: { error: 'missing_required_fields', fields: ['recipient_id'] },
    });
    const client = new GatewayClient({ baseUrl });
    await expect(client.recv('')).rejects.toBeInstanceOf(GatewayClientError);
  });
});

describe('GatewayClient.recordToolCall', () => {
  it('posts the expected body to /tool_call', async () => {
    setPlan('POST', '/tool_call', {
      status: 200,
      body: { action_id: 'tc-1' },
    });
    const client = new GatewayClient({ baseUrl });
    const id = await client.recordToolCall({
      agent_id: 'alice',
      tool_name: 'search',
      arguments: { q: 'hello' },
    });
    expect(id).toBe('tc-1');
    expect(captured[0].body).toEqual({
      agent_id: 'alice',
      tool_name: 'search',
      arguments: { q: 'hello' },
    });
  });
});

describe('GatewayClient.recordToolObservation', () => {
  it('posts the expected body to /tool_observation_return', async () => {
    setPlan('POST', '/tool_observation_return', {
      status: 200,
      body: { action_id: 'obs-1' },
    });
    const client = new GatewayClient({ baseUrl });
    const id = await client.recordToolObservation({
      agent_id: 'alice',
      tool_call_action_id: 'tc-1',
      tool_name: 'search',
      observation: 'result text',
    });
    expect(id).toBe('obs-1');
    expect(captured[0].body).toEqual({
      agent_id: 'alice',
      tool_call_action_id: 'tc-1',
      tool_name: 'search',
      observation: 'result text',
    });
  });
});

describe('GatewayClient.recordMemoryWrite', () => {
  it('defaults tags to an empty array when not provided', async () => {
    setPlan('POST', '/memory_write', {
      status: 200,
      body: { action_id: 'mw-1' },
    });
    const client = new GatewayClient({ baseUrl });
    const id = await client.recordMemoryWrite({
      agent_id: 'alice',
      content: 'note to self',
    });
    expect(id).toBe('mw-1');
    expect(captured[0].body).toEqual({
      agent_id: 'alice',
      content: 'note to self',
      tags: [],
    });
  });

  it('preserves explicit tags', async () => {
    setPlan('POST', '/memory_write', {
      status: 200,
      body: { action_id: 'mw-2' },
    });
    const client = new GatewayClient({ baseUrl });
    await client.recordMemoryWrite({
      agent_id: 'alice',
      content: 'x',
      tags: ['a', 'b'],
    });
    expect(captured[0].body).toEqual({
      agent_id: 'alice',
      content: 'x',
      tags: ['a', 'b'],
    });
  });
});

describe('GatewayClient.recordLlmCall', () => {
  it('includes all token-accounting fields', async () => {
    setPlan('POST', '/llm_call', {
      status: 200,
      body: { action_id: 'llm-1' },
    });
    const client = new GatewayClient({ baseUrl });
    const id = await client.recordLlmCall({
      agent_id: 'alice',
      input_tokens: 100,
      output_tokens: 50,
      cached_tokens: 20,
      latency_ms: 900,
      model: 'claude-opus',
    });
    expect(id).toBe('llm-1');
    expect(captured[0].body).toEqual({
      agent_id: 'alice',
      input_tokens: 100,
      output_tokens: 50,
      cached_tokens: 20,
      latency_ms: 900,
      model: 'claude-opus',
    });
  });

  it('omits cached_tokens when not provided (server defaults it to 0)', async () => {
    setPlan('POST', '/llm_call', {
      status: 200,
      body: { action_id: 'llm-2' },
    });
    const client = new GatewayClient({ baseUrl });
    await client.recordLlmCall({
      agent_id: 'alice',
      input_tokens: 10,
      output_tokens: 5,
      latency_ms: 100,
      model: 'claude-opus',
    });
    const body = captured[0].body as Record<string, unknown>;
    expect(body.agent_id).toBe('alice');
    expect('cached_tokens' in body).toBe(false);
  });
});

describe('GatewayClient.callMcp', () => {
  it('returns the full response on success', async () => {
    setPlan('POST', '/mcp/search', {
      status: 200,
      body: {
        tool_call_action_id: 'tc-1',
        tool_observation_action_id: 'obs-1',
        observation: { hits: [{ title: 'x' }] },
      },
    });
    const client = new GatewayClient({ baseUrl });
    const resp = await client.callMcp('search', {
      agent_id: 'alice',
      arguments: { q: 'hello' },
    });
    expect(resp).toEqual({
      tool_call_action_id: 'tc-1',
      tool_observation_action_id: 'obs-1',
      observation: { hits: [{ title: 'x' }] },
    });
    expect(captured[0].url).toBe('/mcp/search');
  });

  it('throws UnknownToolError on HTTP 404', async () => {
    setPlan('POST', '/mcp/nope', {
      status: 404,
      body: { error: 'unknown tool', tool_name: 'nope' },
    });
    const client = new GatewayClient({ baseUrl });
    await expect(
      client.callMcp('nope', { agent_id: 'alice', arguments: {} }),
    ).rejects.toBeInstanceOf(UnknownToolError);
  });

  it('throws GatewayClientError on other non-2xx', async () => {
    setPlan('POST', '/mcp/boom', {
      status: 500,
      body: { error: 'internal' },
    });
    const client = new GatewayClient({ baseUrl });
    await expect(
      client.callMcp('boom', { agent_id: 'alice', arguments: {} }),
    ).rejects.toBeInstanceOf(GatewayClientError);
  });
});

describe('GatewayClient timeout', () => {
  it('aborts when the server exceeds timeoutMs', async () => {
    setPlan('POST', '/send', {
      status: 200,
      body: { action_id: 'late' },
      delayMs: 200,
    });
    const client = new GatewayClient({ baseUrl, timeoutMs: 30 });
    await expect(
      client.send({ sender_id: 'a', recipient_id: 'b', content: 'c' }),
    ).rejects.toThrow();
  });
});

describe('GatewayClient baseUrl normalisation', () => {
  it('does not emit double slashes when baseUrl has a trailing slash', async () => {
    setPlan('POST', '/send', { status: 200, body: { action_id: 'n1' } });
    const client = new GatewayClient({ baseUrl: `${baseUrl}/` });
    const id = await client.send({
      sender_id: 'a',
      recipient_id: 'b',
      content: 'c',
    });
    expect(id).toBe('n1');
    expect(captured[0].url).toBe('/send');
  });
});
