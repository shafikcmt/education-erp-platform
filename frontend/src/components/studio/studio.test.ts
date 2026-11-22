import { describe, expect, it } from "vitest";

import { coerce, label } from "./dynamic-form";
import { onboardingSteps } from "./onboarding";
import { buildDocument } from "./settings-section";
import { type Artefact, latestByKey } from "./shared";

const version = (key: string, number: number, status: string): Artefact => ({
  id: `${key}-${number}`,
  key,
  name: key,
  number,
  status,
  published_at: null,
  body: {},
});

describe("latestByKey", () => {
  it("keeps the newest version per key and remembers the published one", () => {
    // The API lists versions newest first.
    const items = [
      version("late_fine", 3, "draft"),
      version("late_fine", 2, "published"),
      version("late_fine", 1, "archived"),
      version("promotion", 1, "draft"),
    ];
    const out = latestByKey(items);
    expect(out.map((i) => [i.key, i.number, i.status, i.publishedNumber])).toEqual([
      ["late_fine", 3, "draft", 2],
      ["promotion", 1, "draft", undefined],
    ]);
  });
});

describe("buildDocument", () => {
  const base = {
    "customization.capabilities": { "academics.credit_based": true },
    "tenancy.week_start": 6,
    "customization.terminology": { en: { class: "Grade" } },
  };

  it("keeps keys the screen does not edit and replaces the edited ones", () => {
    const doc = buildDocument(base, {
      week: "7",
      month: "1",
      rows: [{ locale: "bn", key: "section", label: "জামাত" }],
    });
    expect(doc).toEqual({
      "customization.capabilities": { "academics.credit_based": true },
      "tenancy.week_start": 7,
      "tenancy.academic_year_start_month": 1,
      "customization.terminology": { bn: { section: "জামাত" } },
    });
    expect(base["tenancy.week_start"]).toBe(6); // not mutated
  });

  it("removes cleared keys so the scope inherits them", () => {
    const doc = buildDocument(base, {
      week: "",
      month: "",
      rows: [{ locale: "en", key: "class", label: "" }],
    });
    expect(doc).toEqual({ "customization.capabilities": { "academics.credit_based": true } });
  });
});

describe("dynamic form helpers", () => {
  it("coerces input values to what the server validates", () => {
    expect(coerce("number", "42")).toBe(42);
    expect(coerce("number", "")).toBeNull();
    expect(coerce("decimal", "10.50")).toBe("10.50");
    expect(coerce("boolean", true)).toBe(true);
    expect(coerce("multi_select", ["a", "b"])).toEqual(["a", "b"]);
    expect(coerce("text", "hello")).toBe("hello");
  });

  it("falls back from the locale to English to the key", () => {
    expect(label({ en: "Name", bn: "নাম" }, "bn", "name")).toBe("নাম");
    expect(label({ en: "Name" }, "bn", "name")).toBe("Name");
    expect(label(undefined, "bn", "name")).toBe("name");
  });
});

describe("onboardingSteps", () => {
  it("marks steps done from server state", () => {
    const steps = onboardingSteps({
      institutions: 1,
      members: 1,
      settingsPublished: true,
      customFields: 0,
    });
    expect(steps.map((s) => [s.key, s.done])).toEqual([
      ["institution", true],
      ["settings", true],
      ["fields", false],
      ["members", false],
    ]);
  });
});
