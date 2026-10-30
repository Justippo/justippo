import { describe, it, expect, vi } from "vitest";
import worker, { Env } from "./index";

const fetchWorker = worker.fetch as unknown as (
  request: Request,
  env: Env,
  context: ExecutionContext,
) => Promise<Response>;

describe("Worker / Proxy Entry Point", () => {
  // A helper function to build mock environments
  const getMockEnv = (overrides: Partial<Env> = {}): Env => ({
    FASTAPI_ORIGIN: "https://mock-backend.test",
    SENTRY_DSN: "",
    ...overrides,
  });

  const getMockCtx = (): ExecutionContext =>
    ({
      waitUntil: vi.fn(),
      passThroughOnException: vi.fn(),
    }) as unknown as ExecutionContext;

  it("handles the /__warm path without forwarding", async () => {
    const request = new Request("http://localhost/__warm");
    const response = await fetchWorker(request, getMockEnv(), getMockCtx());

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("OK");
  });

  it("handles the /health liveness probe without forwarding", async () => {
    const request = new Request("http://localhost/health");
    const response = await fetchWorker(request, getMockEnv(), getMockCtx());

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("OK");
  });

  it("returns 404 for non-/api/v1/* paths", async () => {
    const request = new Request("http://localhost/assets/logo.png");
    const response = await fetchWorker(request, getMockEnv(), getMockCtx());

    expect(response.status).toBe(404);
    expect(await response.text()).toBe("Not Found");
  });

  it("returns 503 if FASTAPI_ORIGIN is not configured", async () => {
    const request = new Request("http://localhost/api/v1/health");
    const response = await fetchWorker(
      request,
      { FASTAPI_ORIGIN: "" } as Env,
      getMockCtx(),
    );

    expect(response.status).toBe(503);
    const body = await response.json();
    expect(body).toEqual({ error: "FASTAPI_ORIGIN not configured" });
  });

  describe("Feature Flags", () => {
    it("returns 403 for /api/v1/exchange/* if ENABLE_MATRIX_EXCHANGE is not 'true'", async () => {
      const request = new Request("http://localhost/api/v1/exchange/test");
      const response = await fetchWorker(
        request,
        getMockEnv({ ENABLE_MATRIX_EXCHANGE: "false" }),
        getMockCtx(),
      );

      expect(response.status).toBe(403);
      const body = await response.json();
      expect(body).toEqual({
        detail: "feature not enabled",
        flag: "ENABLE_MATRIX_EXCHANGE",
      });
    });

    it("allows /api/v1/exchange/* if ENABLE_MATRIX_EXCHANGE is 'true'", async () => {
      const request = new Request("http://localhost/api/v1/exchange/test");

      const mockFetch = vi
        .fn()
        .mockResolvedValue(new Response("Allowed", { status: 200 }));
      const envWithBinding = getMockEnv({
        ENABLE_MATRIX_EXCHANGE: "true",
        BACKEND: { fetch: mockFetch },
      });

      const response = await fetchWorker(request, envWithBinding, getMockCtx());

      expect(response.status).toBe(200);
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  describe("Proxying", () => {
    it("proxies via BACKEND service binding if available", async () => {
      const request = new Request("http://localhost/api/v1/users", {
        method: "POST",
        headers: { "Content-Type": "application/json", "CF-Ray": "ray-123" },
        body: JSON.stringify({ name: "Test" }),
      });

      const mockBackendResponse = new Response("Backend OK", { status: 201 });
      const mockFetch = vi.fn().mockResolvedValue(mockBackendResponse);
      const testEnv = getMockEnv({ BACKEND: { fetch: mockFetch } });

      const response = await fetchWorker(request, testEnv, getMockCtx());

      expect(response.status).toBe(201);
      expect(await response.text()).toBe("Backend OK");

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const forwardedReq: Request = mockFetch.mock.calls[0][0];

      expect(forwardedReq.url).toBe("https://mock-backend.test/api/v1/users");
      expect(forwardedReq.method).toBe("POST");
      expect(forwardedReq.headers.get("CF-Ray")).toBe("ray-123");
      expect(forwardedReq.headers.get("X-Request-ID")).toMatch(
        /^[0-9a-f-]{36}$/,
      );
      expect(response.headers.get("X-Request-ID")).toBe(
        forwardedReq.headers.get("X-Request-ID"),
      );
      expect(forwardedReq.headers.get("host")).toBe("mock-backend.test");
      expect(forwardedReq.redirect).toBe("manual");
    });

    it("preserves a valid caller request ID across the proxy boundary", async () => {
      const mockFetch = vi
        .fn()
        .mockResolvedValue(new Response("OK", { status: 200 }));
      const request = new Request("http://localhost/api/v1/health", {
        headers: { "X-Request-ID": "test-request_123" },
      });

      const response = await fetchWorker(
        request,
        getMockEnv({ BACKEND: { fetch: mockFetch } }),
        getMockCtx(),
      );
      const forwardedReq: Request = mockFetch.mock.calls[0][0];

      expect(forwardedReq.headers.get("X-Request-ID")).toBe("test-request_123");
      expect(response.headers.get("X-Request-ID")).toBe("test-request_123");
    });

    it("passes OAuth redirects through the service binding unchanged", async () => {
      const authorizationUrl =
        "https://account.matrix.org/authorize?response_type=code&code_challenge_method=S256";
      const mockFetch = vi.fn().mockResolvedValue(
        new Response(null, {
          status: 302,
          headers: { Location: authorizationUrl },
        }),
      );
      const testEnv = getMockEnv({ BACKEND: { fetch: mockFetch } });
      const request = new Request("http://localhost/api/v1/auth/matrix/login");

      const response = await fetchWorker(request, testEnv, getMockCtx());

      expect(response.status).toBe(302);
      expect(response.headers.get("Location")).toBe(authorizationUrl);
      const forwardedReq: Request = mockFetch.mock.calls[0][0];
      expect(forwardedReq.url).toBe(
        "https://mock-backend.test/api/v1/auth/matrix/login",
      );
      expect(forwardedReq.redirect).toBe("manual");
    });

    it("returns 502 if upstream fetch fails", async () => {
      const request = new Request("http://localhost/api/v1/users", {
        method: "POST",
      });

      const mockFetch = vi.fn().mockRejectedValue(new Error("Network Error"));
      const testEnv = getMockEnv({ BACKEND: { fetch: mockFetch } });

      const response = await fetchWorker(request, testEnv, getMockCtx());

      expect(response.status).toBe(502);
      const body = (await response.json()) as {
        error: string;
        detail: string;
        target: string;
        request_id: string;
      };
      expect(body).toEqual({
        error: "upstream fetch failed",
        detail: "Network Error",
        target: "https://mock-backend.test/api/v1/users",
        request_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      });
      expect(response.headers.get("X-Request-ID")).toBe(body.request_id);
    });
  });
});
