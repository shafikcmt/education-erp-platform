import { describe, expect, it } from "vitest";

import { getDirection } from "./direction";
import { routing } from "./routing";

describe("getDirection", () => {
  it("is LTR for launch locales and RTL for Arabic-script languages", () => {
    expect(getDirection("en")).toBe("ltr");
    expect(getDirection("bn")).toBe("ltr");
    expect(getDirection("ar")).toBe("rtl");
    expect(getDirection("ur-PK")).toBe("rtl");
  });

  it("launches with English and Bengali (ADR-021)", () => {
    expect(routing.locales).toEqual(["en", "bn"]);
    expect(routing.defaultLocale).toBe("en");
  });
});
