import { describe, expect, it } from "vitest";

import { safeNextPath } from "./next-path";

describe("safeNextPath (open-redirect guard)", () => {
  it.each([
    [undefined, "/dashboard"],
    ["", "/dashboard"],
    ["https://evil.example", "/dashboard"],
    ["//evil.example", "/dashboard"],
    ["/\\evil.example", "/dashboard"],
    ["/platform/users", "/platform/users"],
    ["/bn/account/security", "/account/security"],
    ["/en", "/dashboard"],
  ])("%s -> %s", (input, expected) => {
    expect(safeNextPath(input)).toBe(expected);
  });
});
