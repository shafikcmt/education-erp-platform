import { type APIRequestContext, expect, type Page, test } from "@playwright/test";

import {
  adminApi,
  BASE_URL,
  freshTotp,
  linkFrom,
  loadAdmin,
  totp,
  trackCspViolations,
  waitForMail,
} from "./support";
import {
  catalog,
  enrollMfa,
  joinAndSignIn,
  label,
  newPage,
  noSeriousA11yIssues,
} from "./tenant-flows";

/**
 * Phase 5 M8: presets, the Customization Studio and self-service sign-up through the real stack
 * (tenant hosts and sign-up are enabled in this throwaway stack only).
 */
const ENABLED = Boolean(process.env.E2E_TENANT_HOSTS);
const SIGNUP = Boolean(process.env.E2E_SIGNUP);
const TYPES = [
  "school",
  "college",
  "university",
  "madrasa",
  "coaching_center",
  "training_institute",
] as const;
const m = catalog("en");

/** A TOTP code from a later 30-second step than `afterStep` (the server refuses replays). */
async function codeAfter(secret: string, afterStep: number): Promise<string> {
  while (Math.floor(Date.now() / 30_000) <= afterStep)
    await new Promise((r) => setTimeout(r, 1_000));
  return totp(secret);
}

async function adminStepUp(api: APIRequestContext) {
  const admin = loadAdmin();
  for (let attempt = 0; attempt < 3; attempt++) {
    await api.get("/api/v1/auth/csrf/");
    const token = (await api.storageState()).cookies.find((c) => c.name === "csrftoken")?.value;
    const response = await api.post("/api/v1/auth/step-up/", {
      data: { password: admin.password, code: await freshTotp(admin.secret) },
      headers: { "X-CSRFToken": token ?? "", Referer: BASE_URL },
    });
    if (response.ok()) return;
  }
  throw new Error("admin step-up failed three times");
}

/** Fill the step-up dialog with the password and a fresh code, when it appears. */
async function confirmStepUp(page: Page, password: string, code: () => Promise<string>) {
  const dialog = page.getByRole("dialog", { name: label(m, "stepUp.title") });
  // A step-up from the last 10 minutes (e.g. during MFA enrolment) may still be fresh.
  if (
    !(await dialog.waitFor({ timeout: 5_000 }).then(
      () => true,
      () => false,
    ))
  )
    return;
  await dialog.getByLabel(label(m, "auth.password"), { exact: true }).fill(password);
  await dialog.getByLabel(label(m, "auth.mfa.code")).fill(await code());
  await dialog.getByRole("button", { name: label(m, "stepUp.submit") }).click();
  await expect(dialog).toBeHidden();
}

test.describe("presets, the Studio and self-service sign-up", () => {
  test.skip(!ENABLED, "tenant hosts are disabled in this stack (set E2E_TENANT_HOSTS=1)");

  // One journey with ONE admin sign-in: every extra admin TOTP sign-in competes with the other
  // journeys for 30-second steps.
  test("sign-up → approval; a tenant per type; Studio publish and rollback", async ({
    page,
    browser,
  }, info) => {
    test.skip(info.project.name !== "desktop-chromium", "one journey per run");
    test.setTimeout(420_000);
    const run = Date.now().toString(36);
    const org = { slug: `su${run}`, name: `Signup ${run}`, email: `founder-${run}@example.test` };

    // 1. A visitor asks for an organisation and confirms the emailed link (sign-up stack only).
    if (SIGNUP) {
      const visitor = await newPage(browser);
      const visitorCsp = await trackCspViolations(visitor.page);
      await visitor.page.goto("/en/login");
      await visitor.page.getByRole("link", { name: label(m, "signup.create") }).click();
      await expect(visitor.page).toHaveURL(/\/en\/signup$/);
      await visitor.page.getByLabel(label(m, "signup.organisation")).fill(org.name);
      await visitor.page.getByLabel(label(m, "signup.slug")).fill(org.slug);
      await visitor.page.getByLabel(label(m, "signup.institutionType")).selectOption("college");
      await visitor.page.getByLabel(label(m, "signup.institutionName")).fill(`${org.name} College`);
      await visitor.page.getByLabel(label(m, "signup.currency")).fill("BDT");
      await visitor.page.getByLabel(label(m, "auth.email"), { exact: true }).fill(org.email);
      await noSeriousA11yIssues(visitor.page);
      await visitor.page.getByRole("button", { name: label(m, "signup.submit") }).click();
      await expect(visitor.page.getByText(label(m, "signup.sent"))).toBeVisible();
      const mail = await waitForMail(org.email, new RegExp(org.name));
      await visitor.page.goto(linkFrom(mail, "signup/verify"));
      await expect(visitor.page).not.toHaveURL(/#token=/);
      await visitor.page.getByRole("button", { name: label(m, "signup.confirm") }).click();
      await expect(visitor.page.getByText(label(m, "signup.verified"))).toBeVisible();
      expect(await visitorCsp()).toEqual([]);
      await visitor.context.close();
    }

    // 2. One admin session (MFA + fresh step-up): six tenants, one per institution type.
    const { api, post } = await adminApi();
    await adminStepUp(api);
    const slugs: Record<string, string> = {};
    for (const [i, type] of TYPES.entries()) {
      const slug = `p${i}${run}`;
      const created = (await post("/api/v1/platform/tenants/", {
        slug,
        name: `Preset ${type} ${run}`,
        owner_email: `owner-${type.replace("_", "-")}-${run}@example.test`,
        default_locale: "en",
        locales: ["en", "bn"],
        timezone: "Asia/Dhaka",
        currency: "BDT",
        country: "BD",
        institution: { institution_type: type, code: "main", name: `${type} ${run}` },
      })) as { status: string };
      expect(created.status).toBe("active");
      slugs[type] = slug;
    }

    // 3. The same admin approves the sign-up on the platform page (session reused, so no new
    //    TOTP step); the founder then joins the new organisation as its owner.
    if (SIGNUP) {
      const adminUi = await browser.newContext({ storageState: await api.storageState() });
      const adminPage = await adminUi.newPage();
      await adminPage.goto("/en/dashboard");
      await adminPage
        .getByRole("link", { name: label(m, "nav.signups") })
        .first()
        .click();
      await expect(adminPage).toHaveURL(/\/en\/platform\/signups$/);
      const card = adminPage.getByTestId("signups").locator("div", { hasText: org.slug }).first();
      await expect(card).toBeVisible();
      await noSeriousA11yIssues(adminPage);
      await card.getByRole("button", { name: label(m, "signup.admin.approve") }).click();
      await expect(adminPage.getByText(org.slug)).toHaveCount(0);
      await adminUi.close();
      const founder = await newPage(browser);
      const founderPassword = await joinAndSignIn(founder.page, org.slug, org.email, org.name);
      await enrollMfa(founder.page, founderPassword);
      await expect(founder.page.getByTestId("brand")).toHaveText(org.name);
      await founder.context.close();
    }
    await api.dispose();

    // 4. The madrasa owner joins; the institution carries its type's preset terminology.
    const cspViolations = await trackCspViolations(page);
    const madrasa = { slug: slugs.madrasa!, name: `Preset madrasa ${run}` };
    const password = await joinAndSignIn(
      page,
      madrasa.slug,
      `owner-madrasa-${run}@example.test`,
      madrasa.name,
    );
    const enrolledStep = Math.floor(Date.now() / 30_000);
    const secret = await enrollMfa(page, password);
    // Fetched by the browser: Node cannot resolve *.localhost, the browser can.
    const context = (await page.evaluate(async () => {
      const response = await fetch("/api/v1/me/context/", { credentials: "same-origin" });
      return response.json();
    })) as { institution_terminology: Record<string, Record<string, Record<string, string>>> };
    const [terms] = Object.values(context.institution_terminology);
    expect(terms?.bn?.["unit.class"]).toBe("জামাত");
    expect(terms?.en?.["unit.subject"]).toBe("Kitab");

    // 5. Studio: draft → publish (step-up) → second version → restore the first.
    const nav = page.getByRole("navigation", { name: label(m, "nav.main") });
    await nav.getByRole("link", { name: label(m, "nav.studio") }).click();
    await expect(page).toHaveURL(/\/en\/studio$/);
    await expect(page.getByRole("heading", { name: label(m, "studio.title") })).toBeVisible();
    await noSeriousA11yIssues(page);
    const week = page.getByLabel(label(m, "studio.settings.weekStart"));
    const history = page.getByTestId("history");
    await week.selectOption("5");
    await page.getByRole("button", { name: label(m, "studio.saveDraft") }).click();
    await page.getByRole("button", { name: label(m, "studio.publish") }).click();
    await confirmStepUp(page, password, () => codeAfter(secret, enrolledStep));
    await expect(history).toContainText(label(m, "studio.version", { number: "1" }));
    await week.selectOption("6");
    await page.getByRole("button", { name: label(m, "studio.saveDraft") }).click();
    await page.getByRole("button", { name: label(m, "studio.publish") }).click();
    await expect(history).toContainText(label(m, "studio.version", { number: "2" }));
    await expect(
      page.getByText(label(m, "studio.settings.effective", { value: "6" })),
    ).toBeVisible();
    await history
      .getByRole("listitem")
      .filter({ hasText: label(m, "studio.version", { number: "1" }) + " ·" })
      .getByRole("button", { name: label(m, "studio.rollback") })
      .click();
    await expect(history).toContainText(label(m, "studio.version", { number: "3" }));
    await expect(
      page.getByText(label(m, "studio.settings.effective", { value: "5" })),
    ).toBeVisible();
    expect(await cspViolations()).toEqual([]);
  });
});
