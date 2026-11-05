import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("Phase 1 stack smoke (through Nginx, single origin)", () => {
  test("root redirects to the default locale", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/en$/);
  });

  test("English landing page renders with correct lang/dir", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => msg.type() === "error" && errors.push(msg.text()));
    await page.goto("/en");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Education ERP");
    expect(errors).toEqual([]);
  });

  test("Bengali landing page renders translated content", async ({ page }) => {
    await page.goto("/bn");
    await expect(page.locator("html")).toHaveAttribute("lang", "bn");
    await expect(page.getByText("সিস্টেমের অবস্থা দেখুন")).toBeVisible();
  });

  test("locale switcher keeps the current page", async ({ page }) => {
    await page.goto("/en/system");
    await page.getByRole("link", { name: "বাংলা" }).click();
    await expect(page).toHaveURL(/\/bn\/system$/);
  });

  test("system page shows the API as operational via the generated client", async ({ page }) => {
    await page.goto("/en/system");
    await expect(page.getByTestId("api-status").locator("[data-state]")).toHaveAttribute(
      "data-state",
      "ok",
    );
  });

  test("API, probes and security headers are served through Nginx", async ({ request }) => {
    const health = await request.get("/api/v1/system/health/");
    expect(health.status()).toBe(200);
    expect(await health.json()).toMatchObject({ status: "ok" });
    expect(health.headers()["x-request-id"]).toBeTruthy();
    expect(health.headers()["x-content-type-options"]).toBe("nosniff");

    const ready = await request.get("/readyz");
    expect(ready.status()).toBe(200);

    const missing = await request.get("/api/v1/does-not-exist/");
    expect(missing.status()).toBe(404);
    expect(missing.headers()["content-type"]).toContain("application/problem+json");
  });

  test("landing page has no serious accessibility violations", async ({ page }) => {
    await page.goto("/en");
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = results.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact ?? ""),
    );
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  });
});
