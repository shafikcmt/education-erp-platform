import { describe, expect, it } from "vitest";

import type { TenantContext } from "@/lib/tenancy/context";

import { scopePermissions } from "./scope-switcher";

const context = {
  scopes: [
    { scope_type: "tenant", institution: null, campus: null, permissions: ["tenancy.tenant.view"] },
    {
      scope_type: "institution",
      institution: "i",
      campus: null,
      permissions: ["tenancy.campus.create"],
    },
  ],
} as unknown as TenantContext;

describe("scopePermissions", () => {
  it("unions every scope for 'all' and narrows to one scope otherwise", () => {
    expect([...scopePermissions(context, "all")].sort()).toEqual([
      "tenancy.campus.create",
      "tenancy.tenant.view",
    ]);
    expect([...scopePermissions(context, "1")]).toEqual(["tenancy.campus.create"]);
    expect(scopePermissions(context, "9").size).toBe(0);
    expect(scopePermissions(undefined, "all").size).toBe(0);
  });
});
