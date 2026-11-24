import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useFragmentToken } from "./fragment-token";

describe("useFragmentToken", () => {
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("reads the token once and removes it from the address bar", async () => {
    const token = "A".repeat(43);
    window.history.replaceState(null, "", `/en/reset-password#token=${token}`);
    const { result } = renderHook(() => useFragmentToken());
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.token).toBe(token);
    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain(token);
  });

  it("rejects malformed tokens", async () => {
    window.history.replaceState(null, "", "/en/activate#token=<script>");
    const { result } = renderHook(() => useFragmentToken());
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.token).toBeNull();
  });

  it("reads a new link opened in the same tab (hash change without a reload)", async () => {
    window.history.replaceState(null, "", "/en/apply/status#token=" + "a".repeat(43));
    const { result } = renderHook(() => useFragmentToken());
    await waitFor(() => expect(result.current.token).toBe("a".repeat(43)));
    const first = result.current.version;
    act(() => {
      window.history.replaceState(null, "", "/en/apply/status#token=" + "b".repeat(43));
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    await waitFor(() => expect(result.current.token).toBe("b".repeat(43)));
    expect(result.current.version).toBeGreaterThan(first);
    expect(window.location.hash).toBe("");
  });
});
