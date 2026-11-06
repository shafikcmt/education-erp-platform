import { expect, test } from "@playwright/test";

import { trackCspViolations } from "./support";

/** Security review M3: real HTML responses through Nginx carry a strict, nonce-based CSP. */
for (const path of ["/en/login", "/bn/forgot-password", "/en/activate", "/en"]) {
  test(`strict nonce CSP on ${path}`, async ({ page, request }) => {
    const response = await request.get(path);
    const csp = response.headers()["content-security-policy"] ?? "";
    const script = csp.split("; ").find((d) => d.startsWith("script-src ")) ?? "";
    const nonce = script.match(/'nonce-([^']+)'/)?.[1];
    expect(nonce, csp).toBeTruthy();
    expect(script).not.toMatch(/unsafe-inline|unsafe-eval/);
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("img-src 'self' data:");
    // Every script Next.js rendered carries this response's nonce.
    const html = await response.text();
    const scripts = [...html.matchAll(/<script\b[^>]*>/g)].map((m) => m[0]);
    expect(scripts.length).toBeGreaterThan(0);
    for (const tag of scripts) expect(tag).toContain(`nonce="${nonce}"`);
    // A second request gets a different nonce.
    const again = await request.get(path);
    expect(again.headers()["content-security-policy"]).not.toContain(`'nonce-${nonce}'`);

    const violations = await trackCspViolations(page);
    await page.goto(path);
    await expect(page.locator("h1")).toBeVisible();
    expect(await violations()).toEqual([]);
  });
}

test("API responses carry a no-content CSP", async ({ request }) => {
  const response = await request.get("/api/v1/auth/csrf/");
  expect(response.headers()["content-security-policy"]).toBe(
    "default-src 'none'; frame-ancestors 'none'",
  );
});
