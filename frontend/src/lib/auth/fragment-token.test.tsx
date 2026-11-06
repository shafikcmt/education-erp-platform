import { renderHook, waitFor } from "@testing-library/react";
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
});
