import { describe, expect, it, vi } from "vitest";

import { CSRF_HEADER_NAME, createApiClient, readCookie } from "./client";

function mockFetch() {
  return vi.fn<typeof fetch>(async () =>
    Response.json({ status: "ok", version: "1", environment: "test" }),
  );
}

/** openapi-fetch always calls fetch with a Request object. */
function sentRequest(fetch: ReturnType<typeof mockFetch>, index = 0): Request {
  return fetch.mock.calls[index]![0] as Request;
}

describe("readCookie", () => {
  it("reads a named cookie and decodes it", () => {
    expect(readCookie("a=1; csrftoken=abc%3D%3D; b=2", "csrftoken")).toBe("abc==");
    expect(readCookie("a=1", "csrftoken")).toBeUndefined();
  });
});

describe("createApiClient", () => {
  it("sends credentials and no CSRF header on safe requests", async () => {
    const fetch = mockFetch();
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetch,
      getCookies: () => "csrftoken=t0k",
    });
    const { data } = await client.GET("/api/v1/system/health/");
    expect(data?.status).toBe("ok");
    const request = sentRequest(fetch);
    expect(request.url).toBe("http://api.test/api/v1/system/health/");
    expect(request.credentials).toBe("include");
    expect(request.headers.get(CSRF_HEADER_NAME)).toBeNull();
  });

  it("attaches X-CSRFToken to unsafe requests from the CSRF cookie", async () => {
    const fetch = mockFetch();
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetch,
      getCookies: () => "csrftoken=t0k",
    });
    // Unsafe method against a path not yet in the schema: exercise middleware via a cast.
    await (client as unknown as { POST: (p: string, o: object) => Promise<unknown> }).POST(
      "/api/v1/system/health/",
      { body: {} },
    );
    expect(sentRequest(fetch).headers.get(CSRF_HEADER_NAME)).toBe("t0k");
  });

  it("never touches localStorage or sessionStorage (ADR-011)", async () => {
    const local = vi.spyOn(Storage.prototype, "getItem");
    const set = vi.spyOn(Storage.prototype, "setItem");
    const client = createApiClient({ baseUrl: "http://api.test", fetch: mockFetch() });
    await client.GET("/api/v1/system/health/");
    expect(local).not.toHaveBeenCalled();
    expect(set).not.toHaveBeenCalled();
  });
});
