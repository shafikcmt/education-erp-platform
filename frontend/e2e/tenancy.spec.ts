import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import { loadAdmin, trackCspViolations } from "./support";

/**
 * Phase 3 M9, platform host: a Super Admin provisions an organisation with the wizard, sees it
 * in the registry, overrides its limits (step-up) and opens "My organisations". Tenant-host
 * screens need tenant hosts, which stay disabled in this stack (D1); the two-host E2E is M10.
 */
/** The admin's single-use recovery codes are split between the two projects, so these sign-ins
 * never compete with other workers for a TOTP step (the server rejects replayed steps). */
function recoveryCodes(project: string): [string, string] {
  const codes = loadAdmin().recoveryCodes;
  const [first, second] = project.startsWith("mobile")
    ? [codes[2], codes[3]]
    : [codes[0], codes[1]];
  if (!first || !second) throw new Error("bootstrap left too few recovery codes");
  return [first, second];
}

async function signInAsAdmin(page: Page, code: string) {
  const admin = loadAdmin();
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill(admin.email);
  await page.getByLabel("Password").fill(admin.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/en\/login\/mfa/);
  await page.getByRole("button", { name: "Use a recovery code instead" }).click();
  await page.getByLabel("Recovery code").fill(code);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/);
  return admin;
}

async function noSeriousA11yIssues(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact ?? ""),
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

test("provision an organisation, override its limits and list my organisations", async ({
  page,
}, info) => {
  const cspViolations = await trackCspViolations(page);
  const [loginCode, stepUpCode] = recoveryCodes(info.project.name);
  const admin = await signInAsAdmin(page, loginCode);
  const slug = `e2e${info.project.name.startsWith("mobile") ? "m" : "d"}${Date.now().toString(36)}`;

  await page.getByRole("link", { name: "Tenants" }).first().click();
  await expect(page).toHaveURL(/\/en\/platform\/tenants$/);
  await page.getByRole("button", { name: "New organisation" }).click();
  const wizard = page.getByRole("dialog");
  await wizard.getByLabel("Organisation name").fill("E2E Academy");
  await wizard.getByLabel("Address name").fill(slug);
  await wizard.getByLabel("Institution type").selectOption("madrasa");
  await wizard.getByLabel("Institution name").fill("E2E Madrasa");
  await wizard.getByLabel("Main campus name").fill("Main");
  await wizard.getByLabel("Owner's email").fill(`owner-${slug}@example.test`);
  await wizard.getByRole("button", { name: "Create organisation" }).click();
  await expect(wizard).toBeHidden();
  await noSeriousA11yIssues(page);

  await page.getByLabel("Search by name or address").fill(slug);
  const row = page.getByRole("row").filter({ hasText: slug });
  await expect(row).toContainText("Active");
  await expect(row).toContainText("1 institutions · 3 campuses");
  await row.getByRole("link", { name: "E2E Academy" }).click();
  await expect(page.getByRole("heading", { name: "E2E Academy" })).toBeVisible();

  // Limit override needs a reason and a fresh step-up (ADR-010).
  await page.getByRole("button", { name: "Change limits" }).click();
  const limits = page.getByRole("dialog");
  await limits.getByLabel("Institutions").fill("4");
  await limits.getByLabel("Campuses").fill("9");
  await limits.getByLabel("Reason").fill("Pilot contract signed for four schools");
  await limits.getByRole("button", { name: "Save" }).click();
  const stepUp = page.getByRole("dialog", { name: "Confirm it's you" });
  await expect(stepUp).toBeVisible();
  await stepUp.getByLabel("Password", { exact: true }).fill(admin.password);
  await stepUp.getByRole("button", { name: "Use a recovery code instead" }).click();
  await stepUp.getByLabel("Recovery code").fill(stepUpCode);
  await stepUp.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("4 institutions · 9 campuses")).toBeVisible();
  await expect(page.getByText("Pilot contract signed for four schools")).toBeVisible();

  await page.getByRole("link", { name: "My organisations" }).first().click();
  await expect(page.getByText("You are not a member of any organisation yet.")).toBeVisible();
  // Tenant screens don't exist on the platform host.
  const response = await page.goto("/en/institutions");
  expect(response?.status()).toBe(404);
  expect(await cspViolations()).toEqual([]);
});
