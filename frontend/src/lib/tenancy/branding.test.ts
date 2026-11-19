import { describe, expect, it } from "vitest";

import { brandStyle } from "./branding";

describe("brandStyle", () => {
  it("uses a valid hex colour", () => {
    expect(brandStyle({ primary_color: "#0F766E" })).toEqual({
      "--primary": "#0F766E",
      "--ring": "#0F766E",
    });
  });

  it("ignores anything else (no CSS injection)", () => {
    for (const value of ["red", "#fff", "#0F766E; background:url(x)", 42, null]) {
      expect(brandStyle({ primary_color: value })).toEqual({});
    }
    expect(brandStyle(undefined)).toEqual({});
  });
});
