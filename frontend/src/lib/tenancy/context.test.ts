import { describe, expect, it } from "vitest";

import { canAnywhere, canTenantWide, localName, type TenantContext } from "./context";

const context = {
  scopes: [
    { scope_type: "tenant", institution: null, campus: null, permissions: ["tenancy.tenant.view"] },
    {
      scope_type: "institution",
      institution: "i-1",
      campus: null,
      permissions: ["tenancy.campus.create"],
    },
  ],
} as unknown as TenantContext;

describe("tenant context helpers", () => {
  it("finds permissions held in any scope", () => {
    expect(canAnywhere(context, "tenancy.campus.create")).toBe(true);
    expect(canAnywhere(context, "tenancy.member.remove")).toBe(false);
    expect(canAnywhere(undefined, "tenancy.tenant.view")).toBe(false);
  });

  it("distinguishes tenant-wide permissions", () => {
    expect(canTenantWide(context, "tenancy.tenant.view")).toBe(true);
    expect(canTenantWide(context, "tenancy.campus.create")).toBe(false);
  });

  it("uses the localised name when present", () => {
    expect(localName({ name: "North", name_i18n: { bn: "উত্তর" } }, "bn")).toBe("উত্তর");
    expect(localName({ name: "North", name_i18n: { bn: "" } }, "bn")).toBe("North");
    expect(localName({ name: "North" }, "en")).toBe("North");
  });
});
