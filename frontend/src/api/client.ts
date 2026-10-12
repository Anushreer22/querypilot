export interface HealthResponse {
  status: "ok" | "error";
  app_db: "ok" | "error";
  shop_db: "ok" | "error";
}

const API_BASE_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

/**
 * Fetch backend and database health status from GET /health.
 * Handles both 200 (healthy) and 503 (degraded/unhealthy) JSON responses.
 */
export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
  });

  if (response.ok || response.status === 503) {
    return (await response.json()) as HealthResponse;
  }

  throw new Error(`Unexpected HTTP status ${response.status}: ${response.statusText}`);
}

