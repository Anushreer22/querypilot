import { describe, it, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/mocks/server";
import { api, ApiClientError } from "./client";

describe("api client and ApiClientError mapping", () => {
  it("successfully parses valid 200 response", async () => {
    const res = await api.getHealth();
    expect(res.status).toBe("ok");
    expect(res.app_db).toBe("ok");
    expect(res.shop_db).toBe("ok");
  });

  it("maps 422 validation failure with reason and custom userMessage", async () => {
    try {
      await api.executeQuery({ sql: "DELETE FROM users WHERE id = 1;" });
      expect.unreachable("Should have thrown ApiClientError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError);
      const apiErr = err as ApiClientError;
      expect(apiErr.statusCode).toBe(422);
      expect(apiErr.userMessage).toContain("SQL Rejected");
    }
  });

  it("maps 400 execution error with database error message", async () => {
    try {
      await api.executeQuery({ sql: "SELECT * FROM SYNTAX_ERROR;" });
      expect.unreachable("Should have thrown ApiClientError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError);
      const apiErr = err as ApiClientError;
      expect(apiErr.statusCode).toBe(400);
      expect(apiErr.userMessage).toContain("SQL Execution Error");
      expect(apiErr.userMessage).toContain("syntax error");
    }
  });

  it("maps 409 benchmark lock conflict error", async () => {
    try {
      await api.optimizeQuery({ sql: "SELECT id FROM orders WHERE id = 1 LOCKED;" });
      expect.unreachable("Should have thrown ApiClientError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError);
      const apiErr = err as ApiClientError;
      expect(apiErr.statusCode).toBe(409);
      expect(apiErr.userMessage).toContain("Benchmark Conflict");
      expect(apiErr.userMessage).toContain("already running");
    }
  });

  it("maps 429 rate limit error with retry hint", async () => {
    server.use(
      http.post("*/api/query/execute", () => {
        return HttpResponse.json(
          { detail: "Rate limit exceeded" },
          { status: 429 }
        );
      })
    );

    try {
      await api.executeQuery({ sql: "SELECT 1;" });
      expect.unreachable("Should have thrown ApiClientError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError);
      const apiErr = err as ApiClientError;
      expect(apiErr.statusCode).toBe(429);
      expect(apiErr.userMessage).toContain("Rate Limit Exceeded");
      expect(apiErr.userMessage).toContain("60 seconds");
    }
  });

  it("maps 504 statement timeout with execution advice", async () => {
    try {
      await api.executeQuery({ sql: "SELECT * FROM orders TIMEOUT;" });
      expect.unreachable("Should have thrown ApiClientError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError);
      const apiErr = err as ApiClientError;
      expect(apiErr.statusCode).toBe(504);
      expect(apiErr.userMessage).toContain("Gateway Timeout");
      expect(apiErr.userMessage).toContain("5000ms");
    }
  });

  it("maps 503 service unavailable with copy database hint", async () => {
    try {
      await api.optimizeQuery({ sql: "SELECT id FROM orders OFFLINE;" });
      expect.unreachable("Should have thrown ApiClientError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError);
      const apiErr = err as ApiClientError;
      expect(apiErr.statusCode).toBe(503);
      expect(apiErr.userMessage).toContain("Service Unavailable");
    }
  });

  it("maps network connection error (status 0) when server is down", async () => {
    server.use(
      http.get("*/ready", () => {
        return HttpResponse.error();
      }),
      http.get("*/health", () => {
        return HttpResponse.error();
      })
    );

    try {
      await api.getHealth();
      expect.unreachable("Should have thrown ApiClientError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError);
      const apiErr = err as ApiClientError;
      expect(apiErr.statusCode).toBe(0);
      expect(apiErr.userMessage).toContain("Network Connection Error");
    }
  });
});

