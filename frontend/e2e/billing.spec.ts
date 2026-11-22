import { expect, type Page, test } from "@playwright/test";

import { BASE_URL, freshTotp, loadAdmin, trackCspViolations } from "./support";
import { enrollMfa, joinAndSignIn, newPage, noSeriousA11yIssues } from "./tenant-flows";

/**
 * Phase 4 M7: plans, subscriptions and entitlements through the real stack.
 *
 * The platform admin creates a plan and records a test price (owner data; the value is a
 * placeholder for this throwaway stack), provisions an organisation, assigns the plan in the
 * subscription panel; the organisation's owner sees the plan, the limits with usage and the
 * modules (an unbuilt module is listed as "coming soon", never enabled).
 */
const ENABLED = Boolean(process.env.E2E_TENANT_HOSTS);

/** TOTP sign-in that retries on the next step if another worker used this one (the server
 * rejects replayed steps). */
async function signInWithTotp(page: Page) {
  const admin = loadAdmin();
  await page.goto("/en/login");
  await page.getByLabel("Email address").fill(admin.email);
  await page.getByLabel("Password").fill(admin.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/en\/login\/mfa/);
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.getByLabel("Verification code").fill(await freshTotp(admin.secret));
    await page.getByRole("button", { name: "Verify" }).click();
    if (
      await page.waitForURL(/\/en\/dashboard$/, { timeout: 5_000 }).then(
        () => true,
        () => false,
      )
    )
      return admin;
  }
  throw new Error("admin TOTP sign-in failed three times");
}

async function csrfPost(page: Page, url: string, data: object) {
  await page.request.get(`${BASE_URL}/api/v1/auth/csrf/`);
  const token = (await page.context().cookies()).find((c) => c.name === "csrftoken")?.value;
  const response = await page.request.post(`${BASE_URL}${url}`, {
    data,
    headers: { "X-CSRFToken": token ?? "", Referer: BASE_URL },
  });
  expect(response.ok(), `${url}: ${await response.text()}`).toBe(true);
  return response.json() as Promise<{ id: string }>;
}

test.describe("plans, subscriptions and entitlements", () => {
  test.skip(!ENABLED, "tenant hosts are disabled in this stack (set E2E_TENANT_HOSTS=1)");

  test("plan → price → subscription → the owner's subscription page", async ({
    page,
    browser,
  }, info) => {
    test.skip(info.project.name !== "desktop-chromium", "one journey per run");
    test.setTimeout(180_000);
    const cspViolations = await trackCspViolations(page);
    const run = Date.now().toString(36);
    const plan = { code: `p${run}`, name: `Pilot ${run}` };
    const org = { slug: `tc${run}`, name: `Gamma ${run}`, owner: `owner-c-${run}@example.test` };
    const admin = await signInWithTotp(page);

    // Plans and pricing (billing.plan.manage, billing.price.manage).
    await page.getByRole("link", { name: "Plans" }).first().click();
    await expect(page).toHaveURL(/\/en\/platform\/plans$/);
    await page.getByRole("button", { name: "Create plan" }).click();
    const create = page.getByRole("dialog");
    await create.getByLabel("Code").fill(plan.code);
    await create.getByLabel("Name").fill(plan.name);
    await create.getByLabel("Institutions").fill("2");
    await create.getByLabel("Campuses").fill("5");
    await create.getByRole("checkbox", { name: "fees" }).check();
    await create.getByRole("button", { name: "Create plan" }).click();
    await expect(create).toBeHidden();
    await expect(page.getByTestId("plans")).toContainText(plan.name);
    await noSeriousA11yIssues(page);

    await page.getByRole("button", { name: "Add price" }).click();
    const price = page.getByRole("dialog");
    await price.getByLabel("Price for").selectOption(`plan:${plan.code}`);
    await price.getByLabel("Currency").fill("BDT");
    await price.getByLabel("Amount").fill("1.00");
    await price.getByRole("button", { name: "Add price" }).click();
    // Price changes need a fresh step-up: the last recovery code left by the bootstrap.
    const stepUp = page.getByRole("dialog", { name: "Confirm it's you" });
    await expect(stepUp).toBeVisible();
    await stepUp.getByLabel("Password", { exact: true }).fill(admin.password);
    await stepUp.getByRole("button", { name: "Use a recovery code instead" }).click();
    await stepUp.getByLabel("Recovery code").fill(admin.recoveryCodes[8]!);
    await stepUp.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByTestId("prices")).toContainText("1.00 BDT");

    // An organisation, then its plan in the subscription panel (reason, fresh step-up).
    const created = await csrfPost(page, "/api/v1/platform/tenants/", {
      slug: org.slug,
      name: org.name,
      owner_email: org.owner,
      default_locale: "en",
      locales: ["en", "bn"],
      timezone: "Asia/Dhaka",
      currency: "BDT",
      country: "BD",
      institution: { institution_type: "school", code: "main", name: `${org.name} School` },
    });
    await page.goto(`/en/platform/tenants/${created.id}`);
    const panel = page.getByTestId("subscription-panel");
    await expect(panel.getByTestId("sub-plan-name")).toHaveText("No plan");
    await panel.getByRole("button", { name: "Assign plan" }).click();
    const assign = page.getByRole("dialog");
    await assign.getByLabel("Plan").selectOption({ label: plan.name });
    await assign.getByLabel("Reason").fill("E2E: pilot agreement signed");
    await assign.getByRole("button", { name: "Assign plan" }).click();
    await expect(panel.getByTestId("sub-plan-name")).toHaveText(plan.name);

    // The owner joins and sees the plan, limits with usage and modules.
    const owner = await newPage(browser);
    const password = await joinAndSignIn(owner.page, org.slug, org.owner, org.name);
    await enrollMfa(owner.page, password);
    const nav = owner.page.getByRole("navigation", { name: "Main navigation" });
    await nav.getByRole("link", { name: "Subscription" }).click();
    await expect(owner.page).toHaveURL(/\/en\/subscription$/);
    await expect(owner.page.getByTestId("plan-name")).toHaveText(plan.name);
    await expect(owner.page.getByTestId("plan-status")).toHaveText("Active");
    await expect(owner.page.getByTestId("limit-max_institutions")).toContainText("1 of 2");
    await expect(owner.page.getByTestId("limit-max_campuses")).toContainText("1 of 5");
    await expect(owner.page.getByTestId("modules-enabled")).toContainText("tenancy");
    await expect(owner.page.getByTestId("modules-disabled")).toContainText("fees");
    await expect(owner.page.getByTestId("modules-disabled")).toContainText("coming soon");
    await noSeriousA11yIssues(owner.page);

    expect(await cspViolations()).toEqual([]);
    await owner.context.close();
  });
});
