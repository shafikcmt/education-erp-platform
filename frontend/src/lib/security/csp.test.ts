import { describe, expect, it } from "vitest";

import { buildCsp, createNonce, uploadOriginOf } from "./csp";

describe("Content-Security-Policy (review M3)", () => {
  it("is nonce-based with no unsafe script allowances in production", () => {
    const csp = buildCsp("abc123");
    const script = csp.split("; ").find((d) => d.startsWith("script-src "))!;
    expect(script).toBe("script-src 'self' 'nonce-abc123' 'strict-dynamic'");
    expect(csp).not.toContain("unsafe-eval");
    expect(script).not.toContain("unsafe-inline");
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("img-src 'self' data:");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("style-src 'self' 'unsafe-inline'");
  });

  it("allows eval only in development (React Refresh)", () => {
    expect(buildCsp("n", { dev: true })).toContain("'unsafe-eval'");
  });

  it("adds only a bare upload origin to connect-src", () => {
    expect(buildCsp("n")).toContain("connect-src 'self';");
    const origin = uploadOriginOf("https://files.example.com");
    expect(origin).toBe("https://files.example.com");
    expect(buildCsp("n", { uploadOrigin: origin })).toContain(
      "connect-src 'self' https://files.example.com;",
    );
    for (const bad of ["javascript:alert(1)", "https://x.example/path", "*", "", undefined]) {
      expect(uploadOriginOf(bad)).toBeNull();
    }
  });

  it("creates fresh 128-bit nonces", () => {
    const a = createNonce();
    expect(atob(a)).toHaveLength(16);
    expect(createNonce()).not.toBe(a);
  });
});
