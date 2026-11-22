import { describe, expect, it } from "vitest";

import { suggestSlug } from "./slug";

describe("suggestSlug", () => {
  it("makes a valid web address from the organisation name", () => {
    expect(suggestSlug("Echo Foundation")).toBe("echo-foundation");
    expect(suggestSlug("  42 Rose  Academy!! ")).toBe("rose-academy");
    expect(suggestSlug("ঢাকা স্কুল")).toBe("");
    expect(suggestSlug("a".repeat(40))).toHaveLength(32);
  });
});
