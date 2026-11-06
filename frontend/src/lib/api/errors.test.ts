import { describe, expect, it } from "vitest";

import type { ApiError } from "./errors";
import { isApiError, unwrap } from "./errors";

const response = (status: number) => new Response(null, { status });

describe("unwrap", () => {
  it("returns data for 2xx", async () => {
    await expect(
      unwrap(Promise.resolve({ data: { a: 1 }, response: response(200) })),
    ).resolves.toEqual({ a: 1 });
  });

  it("maps Problem Details to ApiError with code, retry and field errors", async () => {
    const error = await unwrap(
      Promise.resolve({
        error: {
          code: "rate_limited",
          retry_after: 42,
          errors: [{ field: "password", code: "too_short", message: "Too short" }],
        },
        response: response(429),
      }),
    ).catch((e: unknown) => e);
    expect(isApiError(error, "rate_limited")).toBe(true);
    expect((error as ApiError).retryAfter).toBe(42);
    expect((error as ApiError).fieldErrors).toEqual({ password: ["Too short"] });
  });

  it("maps network failures to network_error", async () => {
    const error = await unwrap(Promise.reject(new TypeError("offline"))).catch((e: unknown) => e);
    expect(isApiError(error, "network_error")).toBe(true);
  });
});
