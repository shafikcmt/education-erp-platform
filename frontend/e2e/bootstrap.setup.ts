import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import { ADMIN_EMAIL, linkFrom, saveAdmin, strongPassword, totp, waitForMail } from "./support";

/**
 * Acceptance criterion 1 (plan §16): the Super Admin created by `create_platform_admin` activates
 * via the Mailpit email, sets a password, is forced into MFA enrollment, uses the one-time
 * manual key after a step-up (ADR-038), receives recovery codes once, then signs in with MFA and
 * with a recovery code. Runs once, before the desktop/mobile projects.
 */
async function expectNoSeriousA11yIssues(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact ?? ""),
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

test("bootstrap admin: activation → forced MFA → manual key once → recovery codes → MFA login", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const password = strongPassword();

  // Activation link from Mailpit (token in the URL fragment).
  const activationMail = await waitForMail(ADMIN_EMAIL, /activate/i);
  await page.goto(linkFrom(activationMail, "activate"));
  await expect(page).not.toHaveURL(/#token=/); // fragment is cleared immediately
  await expectNoSeriousA11yIssues(page);
  await page.getByLabel("New password", { exact: true }).fill(password);
  await page.getByLabel("Confirm new password").fill(password);
  await page.getByRole("button", { name: "Activate account" }).click();
  await expect(page.getByText("Your account is active")).toBeVisible();

  // Sign in → privileged account must enroll first.
  await page.goto("/en/login");
  await expectNoSeriousA11yIssues(page);
  await page.getByLabel("Email address").fill(ADMIN_EMAIL);
  await page.getByLabel("Password").fill(password);
  const setupResponse = page.waitForResponse(
    (r) => r.url().endsWith("/api/v1/me/mfa/totp/setup/") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/en\/login\/mfa-setup$/);
  const setupBody = await (await setupResponse).text();
  expect(setupBody).not.toContain("otpauth");
  const deviceId = (JSON.parse(setupBody) as { device_id: string }).device_id;
  await expect(page.getByTestId("mfa-qr")).toBeVisible();
  await expectNoSeriousA11yIssues(page);
  // The app is unusable until enrollment completes.
  const blocked = await page.request.get("/api/v1/platform/users/");
  expect((await blocked.json()).code).toBe("mfa_enrollment_required");

  // Manual key: needs a step-up, is shown once.
  await page.getByRole("button", { name: /Can't scan/ }).click();
  await page.getByRole("dialog").getByLabel("Password").fill(password);
  await page.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  const key = (await page.getByTestId("manual-key").textContent())!.replaceAll(" ", "");
  expect(key).toMatch(/^[A-Z2-7]{32}$/);
  expect(setupBody).not.toContain(key);
  // A second reveal is refused (410) and never returns the key again.
  const again = await page.evaluate(async (url) => {
    const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
    const res = await fetch(url, { method: "POST", headers: { "X-CSRFToken": csrf } });
    return { status: res.status, body: await res.text() };
  }, `/api/v1/me/mfa/totp/setup/${deviceId}/manual-key/`);
  expect(again.status).toBe(410);
  expect(again.body).not.toContain(key);

  await page.getByLabel("6-digit code from the app").fill(totp(key));
  await page.getByRole("button", { name: "Confirm and turn on" }).click();
  await expect(page.getByTestId("recovery-codes").locator("li")).toHaveCount(10);
  const codes = await page.getByTestId("recovery-codes").locator("li").allTextContents();
  saveAdmin({ email: ADMIN_EMAIL, password, secret: key, recoveryCodes: codes });
  expect(codes).toHaveLength(10);
  await page.getByLabel(/I have saved my recovery codes/).check();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/);
  await expect(page.getByRole("link", { name: "Users", exact: true })).toBeVisible();

  // Sign out, then sign in with a recovery code (TOTP logins are covered by the other specs).
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/en\/login$/);
  await page.getByLabel("Email address").fill(ADMIN_EMAIL);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/en\/login\/mfa/);
  await expectNoSeriousA11yIssues(page);
  await page.getByRole("button", { name: "Use a recovery code instead" }).click();
  await page.getByLabel("Recovery code").fill(codes[0]!);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/);
  saveAdmin({ email: ADMIN_EMAIL, password, secret: key, recoveryCodes: codes.slice(1) });
});
