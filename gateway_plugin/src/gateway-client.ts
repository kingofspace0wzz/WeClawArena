// WeClawArena audit gateway HTTP client, used by the channel plugin to
// forward every outbound message, tool call, memory write, and LLM event
// into the audit layer.
//
// All methods are thin wrappers around `fetch`. The Python gateway lives in
// `clawsocialarena/gateway/routes.py`; request/response shapes here mirror
// that contract exactly (see Tasks A3-A6 and the 179-test suite).

export interface GatewayClientOptions {
  baseUrl: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

// Provenance field threaded through every endpoint that records an
// ActionRecord. The Python ``ActionRecord`` dataclass exposes
// ``source_action_ids: list[str]`` so Phase C (MSWM) and Phase F
// (attribution) can walk the causal chain without positional
// heuristics. The gateway defaults it to ``[]`` when the caller omits
// it, so this is strictly optional on the wire.
export interface ActionProvenance {
  source_action_ids?: string[];
}

export interface SendBody extends ActionProvenance {
  sender_id: string;
  recipient_id: string;
  content: string;
}

export interface Inbound {
  sender_id: string;
  content: string;
}

export interface ToolCallBody extends ActionProvenance {
  agent_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
}

export interface ToolObservationBody extends ActionProvenance {
  agent_id: string;
  tool_call_action_id: string;
  tool_name: string;
  observation: string;
}

export interface MemoryWriteBody extends ActionProvenance {
  agent_id: string;
  content: string;
  tags?: string[];
}

export interface LlmCallBody extends ActionProvenance {
  agent_id: string;
  input_tokens: number;
  output_tokens: number;
  cached_tokens?: number;
  latency_ms: number;
  model: string;
}

export interface McpCallBody extends ActionProvenance {
  agent_id: string;
  arguments: Record<string, unknown>;
}

export interface McpCallResponse {
  tool_call_action_id: string | null;
  tool_observation_action_id: string | null;
  observation: unknown;
}

// Generic non-2xx response that is not otherwise specialised (e.g. 400
// validation on /send or /recv, 500s from the server). Callers can inspect
// `status` and `responseBody` for diagnostics.
export class GatewayClientError extends Error {
  public readonly status: number;
  public readonly responseBody: string;

  constructor(message: string, status: number, responseBody: string) {
    super(message);
    this.name = 'GatewayClientError';
    this.status = status;
    this.responseBody = responseBody;
  }
}

// Typed 404 from `POST /mcp/<tool_name>` when the gateway's in-process host
// does not know the requested tool. The channel plugin surfaces this as a
// dispatch error rather than retrying.
export class UnknownToolError extends Error {
  public readonly toolName: string;

  constructor(toolName: string, message?: string) {
    super(message ?? `unknown tool: ${toolName}`);
    this.name = 'UnknownToolError';
    this.toolName = toolName;
  }
}

const DEFAULT_TIMEOUT_MS = 5000;

export class GatewayClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;

  constructor(opts: GatewayClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/$/, '');
    // Bind to globalThis so calls like `this.fetchImpl(...)` do not trip the
    // native fetch `Illegal invocation` check that fires when the method is
    // detached from its receiver.
    this.fetchImpl = opts.fetchImpl ?? fetch.bind(globalThis);
    this.timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  async send(body: SendBody): Promise<string | null> {
    const res = await this.post('/send', body);
    if (!res.ok) {
      throw await this.asError(res);
    }
    const data = (await res.json()) as { action_id?: string | null };
    return data.action_id ?? null;
  }

  async recv(recipient_id: string): Promise<Inbound | null> {
    const res = await this.post('/recv', { recipient_id });
    if (res.status === 204) {
      // Drain the (empty) body so the connection can return to the pool.
      await res.text().catch(() => '');
      return null;
    }
    if (!res.ok) {
      throw await this.asError(res);
    }
    const data = (await res.json()) as Inbound;
    return { sender_id: data.sender_id, content: data.content };
  }

  async recordToolCall(body: ToolCallBody): Promise<string | null> {
    return this.postForActionId('/tool_call', body);
  }

  async recordToolObservation(body: ToolObservationBody): Promise<string | null> {
    return this.postForActionId('/tool_observation_return', body);
  }

  async recordMemoryWrite(body: MemoryWriteBody): Promise<string | null> {
    // The Python server defaults `tags` to `[]`; we mirror that here so the
    // wire payload is deterministic regardless of caller-side omission.
    // ``source_action_ids`` is forwarded verbatim so Phase C/F analysis
    // code can walk causal links even when this client is talking to a
    // BASELINE gateway that will discard them.
    const payload: {
      agent_id: string;
      content: string;
      tags: string[];
      source_action_ids?: string[];
    } = {
      agent_id: body.agent_id,
      content: body.content,
      tags: body.tags ?? [],
    };
    if (body.source_action_ids !== undefined) {
      payload.source_action_ids = body.source_action_ids;
    }
    return this.postForActionId('/memory_write', payload);
  }

  async recordLlmCall(body: LlmCallBody): Promise<string | null> {
    return this.postForActionId('/llm_call', body);
  }

  async callMcp(toolName: string, body: McpCallBody): Promise<McpCallResponse> {
    const res = await this.post(`/mcp/${encodeURIComponent(toolName)}`, body);
    if (res.status === 404) {
      const text = await res.text().catch(() => '');
      throw new UnknownToolError(toolName, text || undefined);
    }
    if (!res.ok) {
      throw await this.asError(res);
    }
    const data = (await res.json()) as McpCallResponse;
    return {
      tool_call_action_id: data.tool_call_action_id ?? null,
      tool_observation_action_id: data.tool_observation_action_id ?? null,
      observation: data.observation,
    };
  }

  private async postForActionId(path: string, body: unknown): Promise<string | null> {
    const res = await this.post(path, body);
    if (!res.ok) {
      throw await this.asError(res);
    }
    const data = (await res.json()) as { action_id?: string | null };
    return data.action_id ?? null;
  }

  private async post(path: string, body: unknown): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      return await this.fetchImpl(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }
  }

  private async asError(res: Response): Promise<GatewayClientError> {
    const text = await res.text().catch(() => '');
    return new GatewayClientError(
      `gateway HTTP ${res.status}`,
      res.status,
      text,
    );
  }
}
