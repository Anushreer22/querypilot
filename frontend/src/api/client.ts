import type {
  AgentAskRequest,
  AgentAskResponse,
  AgentRunDetailResponse,
  AgentRunSummary,
  AskRequest,
  AskResponse,
  ExecuteQueryResponse,
  HealthResponse,
  OptimizeResponse,
  QueryHistoryResponse,
  SchemaResponse,
} from "../types";

/**
 * Standard typed API error representing HTTP or network failures across QueryPilot.
 */
export class ApiClientError extends Error {
  public readonly statusCode: number;
  public readonly reason: string | null;
  public readonly detail: unknown;
  public readonly userMessage: string;

  constructor(
    statusCode: number,
    detail: unknown,
    reason: string | null = null,
    userMessage?: string
  ) {
    let derivedMessage = userMessage;
    let detailStr = "";

    if (typeof detail === "string") {
      detailStr = detail;
    } else if (detail && typeof detail === "object") {
      const obj = detail as Record<string, unknown>;
      if (typeof obj.detail === "string") {
        detailStr = obj.detail;
      } else if (typeof obj.message === "string") {
        detailStr = obj.message;
      } else if (typeof obj.reason === "string") {
        detailStr = obj.reason;
      } else {
        detailStr = JSON.stringify(detail);
      }
    }

    if (!derivedMessage) {
      if (statusCode === 422) {
        derivedMessage = `SQL Rejected: ${reason || detailStr || "Query failed security validation."}`;
      } else if (statusCode === 400) {
        derivedMessage = `SQL Execution Error: ${detailStr || "PostgreSQL query failed."}`;
      } else if (statusCode === 409) {
        derivedMessage = `Benchmark Conflict: ${detailStr || "A query benchmark is already running on sample_shop_bench. Please wait for it to finish."}`;
      } else if (statusCode === 429) {
        derivedMessage =
          "Rate Limit Exceeded: Max request allowance reached. Please wait 60 seconds before submitting again.";
      } else if (statusCode === 504) {
        derivedMessage =
          "Gateway Timeout: Statement or execution time exceeded limits (5000ms). Consider refining filters or adding an index.";
      } else if (statusCode === 502 || statusCode === 503) {
        derivedMessage = `Service Unavailable: ${detailStr || "AI provider or benchmark copy database is temporarily unreachable."}`;
      } else if (statusCode === 0) {
        derivedMessage =
          "Network Connection Error: Could not reach the QueryPilot backend server at http://127.0.0.1:8000.";
      } else {
        derivedMessage = detailStr || `Request failed with HTTP status ${statusCode}.`;
      }
    }

    super(derivedMessage);
    this.name = "ApiClientError";
    this.statusCode = statusCode;
    this.reason = reason;
    this.detail = detail;
    this.userMessage = derivedMessage;
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  let response: Response;

  try {
    response = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw err;
    }
    throw new ApiClientError(0, err instanceof Error ? err.message : "Network failure");
  }

  // Handle degraded health/ready check 503 as valid payload
  if ((endpoint === "/ready" || endpoint === "/health") && response.status === 503) {
    return (await response.json()) as T;
  }

  if (!response.ok) {
    let errorData: unknown;
    let reason: string | null = null;
    try {
      errorData = await response.json();
      if (errorData && typeof errorData === "object") {
        const obj = errorData as Record<string, unknown>;
        if (typeof obj.reason === "string") reason = obj.reason;
        else if (typeof obj.detail === "string" && obj.detail.includes("reason")) {
          reason = obj.detail;
        }
      }
    } catch {
      errorData = await response.text();
    }

    throw new ApiClientError(response.status, errorData, reason);
  }

  return (await response.json()) as T;
}

export const api = {
  /** Check live status of backend and databases */
  getHealth: (): Promise<HealthResponse> => request<HealthResponse>("/ready"),

  /** Inspect business table schema */
  getSchema: (): Promise<SchemaResponse> => request<SchemaResponse>("/api/schema"),

  /** Execute validated read-only SQL query */
  executeQuery: (payload: {
    sql: string;
    source?: string;
    timeout_ms?: number;
  }): Promise<ExecuteQueryResponse> =>
    request<ExecuteQueryResponse>("/api/query/execute", {
      method: "POST",
      body: JSON.stringify({
        source: "manual",
        timeout_ms: 5000,
        ...payload,
      }),
    }),

  /** Get query execution audit history */
  getQueryHistory: (limit = 50, offset = 0): Promise<QueryHistoryResponse> =>
    request<QueryHistoryResponse>(`/api/query/history?limit=${limit}&offset=${offset}`),

  /** Natural language to SQL prompt-and-repair flow (Phase 4) */
  askSimple: (payload: AskRequest): Promise<AskResponse> =>
    request<AskResponse>("/api/ask", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Autonomous multi-step tool-calling agent (Phase 5) */
  askAgent: (payload: AgentAskRequest): Promise<AgentAskResponse> =>
    request<AgentAskResponse>("/api/agent/ask", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Get full details of an agent run */
  getAgentRun: (runId: string): Promise<AgentRunDetailResponse> =>
    request<AgentRunDetailResponse>(`/api/agent/runs/${runId}`),

  /** List recent agent runs */
  listAgentRuns: (limit = 20): Promise<AgentRunSummary[]> =>
    request<AgentRunSummary[]>(`/api/agent/runs?limit=${limit}`),

  /** Analyze query plan bottlenecks and optionally benchmark on sample_shop_bench (Phase 6) */
  optimizeQuery: (
    payload: {
      sql: string;
      benchmark?: boolean;
      iterations?: number;
    },
    signal?: AbortSignal
  ): Promise<OptimizeResponse> =>
    request<OptimizeResponse>("/api/optimize", {
      method: "POST",
      body: JSON.stringify({
        benchmark: false,
        iterations: 7,
        ...payload,
      }),
      signal,
    }),
};

export const getHealth = api.getHealth;
export type { HealthResponse };

