import { describe, expect, it } from "vitest";

import type { TenantContext } from "@/lib/tenancy/context";
import { isEntitled, usagePercent } from "@/lib/tenancy/entitlements";

const context = {
  entitlements: { modules: ["tenancy", "billing"], flags: {}, limits: {} },
} as unknown as TenantContext;

describe("entitlements", () => {
  it("reads enabled modules from the context and fails closed", () => {
    expect(isEntitled(context, "billing")).toBe(true);
    expect(isEntitled(context, "hostel")).toBe(false);
    expect(isEntitled(undefined, "tenancy")).toBe(false);
  });

  it("computes a clamped usage share", () => {
    expect(usagePercent({ limit: 4, used: 1 })).toBe(25);
    expect(usagePercent({ limit: 2, used: 5 })).toBe(100);
    expect(usagePercent({ limit: 0, used: 0 })).toBe(100);
  });
});
