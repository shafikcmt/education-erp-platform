import { describe, expect, it } from "vitest";

import bn from "./bn.json";
import en from "./en.json";

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === "object" ? keys(v as object, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

describe("translation catalogs", () => {
  it("bn has exactly the same keys as en (no missing or stray strings)", () => {
    expect(keys(bn).sort()).toEqual(keys(en).sort());
  });

  it("has no empty strings", () => {
    const values = (o: object): string[] =>
      Object.values(o).flatMap((v) =>
        typeof v === "object" ? values(v as object) : [v as string],
      );
    expect(values(en).every((v) => v.trim().length > 0)).toBe(true);
    expect(values(bn).every((v) => v.trim().length > 0)).toBe(true);
  });
});
