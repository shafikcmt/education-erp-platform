import AxeBuilder from "@axe-core/playwright";
import {
  type APIRequestContext,
  type Browser,
  expect,
  type Page,
  request,
  test,
} from "@playwright/test";

import {
  BASE_URL,
  linkFrom,
  loadAdmin,
  strongPassword,
  totp,
  trackCspViolations,
  waitForMail,
} from "./support";

/**
 * Phase 3 plan §15.1, M10: two tenants on `{slug}.localhost` (tenant hosts enabled for this
 * stack only, `E2E_TENANT_HOSTS=1`; production refuses `localhost` as a tenant domain).
 *
 * provisioning → owner invitation → new account → MFA enrolment → campus → member invitation
 * with a campus-scoped role → the member sees only their scope → the other tenant is out of
 * reach → support session approved by the owner (banner) and revoked.
 */
const ENABLED = Boolean(process.env.E2E_TENANT_HOSTS);
const PORT = new URL(BASE_URL).port || "80";
const hostUrl = (slug: string) => `http://${slug}.localhost:${PORT}`;

async function noSeriousA11yIssues(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact ?? ""),
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

/** Platform API session of the bootstrap admin with single-use recovery codes (no TOTP step
 * shared with other workers). */
async function platformAdmin(loginCode: string, stepUpCode: string): Promise<APIRequestContext> {
  const admin = loadAdmin();
  const api = await request.newContext({ baseURL: BASE_URL });
  const csrf = async () => {
    await api.get("/api/v1/auth/csrf/");
    const cookie = (await api.storageState()).cookies.find((c) => c.name === "csrftoken");
    return { "X-CSRFToken": cookie?.value ?? "", Referer: BASE_URL };
  };
  const post = async (url: string, data: object) => {
    const response = await api.post(url, { data, headers: await csrf() });
    expect(response.ok(), `${url}: ${await response.text()}`).toBe(true);
    return response;
  };
  await post("/api/v1/auth/login/", { email: admin.email, password: admin.password });
  await post("/api/v1/auth/mfa/verify/", { recovery_code: loginCode });
  await post("/api/v1/auth/step-up/", { password: admin.password, recovery_code: stepUpCode });
  return api;
}

async function apiPost(api: APIRequestContext, url: string, data: object) {
  await api.get("/api/v1/auth/csrf/");
  const token = (await api.storageState()).cookies.find((c) => c.name === "csrftoken")?.value;
  const response = await api.post(url, {
    data,
    headers: { "X-CSRFToken": token ?? "", Referer: BASE_URL },
  });
  expect(response.ok(), `${url}: ${await response.text()}`).toBe(true);
  return response.json();
}

/** Accept an emailed invitation on the tenant host with a new account, then sign in. */
async function joinAndSignIn(page: Page, slug: string, email: string, tenantName: string) {
  const password = strongPassword();
  const mail = await waitForMail(email, new RegExp(tenantName));
  await page.goto(hostUrl(slug) + linkFrom(mail, "accept-invitation"));
  await expect(page).not.toHaveURL(/#token=/);
  await expect(page.getByRole("heading", { name: `Join ${tenantName}` })).toBeVisible();
  await expect(page.getByTestId("brand")).toHaveText(tenantName);
  await noSeriousA11yIssues(page);
  await page.getByLabel("Display name").fill(email.split("@")[0]!);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Join" }).click();
  await expect(page.getByText("Your account is ready")).toBeVisible();
  await page.getByRole("link", { name: "Go to sign in" }).click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  return password;
}

/** Privileged tenant role → MFA enrolment on the tenant host (manual key behind a step-up). */
async function enrollMfa(page: Page, password: string): Promise<string> {
  await expect(page).toHaveURL(/\/en\/login\/mfa-setup$/);
  await page.getByRole("button", { name: /Can't scan/ }).click();
  await page.getByRole("dialog").getByLabel("Password").fill(password);
  await page.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  const secret = (await page.getByTestId("manual-key").textContent())!.replaceAll(" ", "");
  await page.getByLabel("6-digit code from the app").fill(totp(secret));
  await page.getByRole("button", { name: "Confirm and turn on" }).click();
  await expect(page.getByTestId("recovery-codes").locator("li")).toHaveCount(10);
  await page.getByLabel(/I have saved my recovery codes/).check();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/en\/dashboard$/);
  return secret;
}

async function newPage(browser: Browser) {
  const context = await browser.newContext();
  return { context, page: await context.newPage() };
}

test.describe("two tenants on their own hosts", () => {
  test.skip(!ENABLED, "tenant hosts are disabled in this stack (set E2E_TENANT_HOSTS=1)");

  test("owner and member journeys stay inside their tenant and scope", async ({
    page,
    browser,
  }, info) => {
    test.skip(info.project.name !== "desktop-chromium", "one full journey per run");
    test.setTimeout(240_000);
    const cspViolations = await trackCspViolations(page);
    const run = Date.now().toString(36);
    const tenants = {
      a: { slug: `ta${run}`, name: `Alpha ${run}`, owner: `owner-a-${run}@example.test` },
      b: { slug: `tb${run}`, name: `Beta ${run}`, owner: `owner-b-${run}@example.test` },
    };
    const codes = loadAdmin().recoveryCodes;
    const admin = await platformAdmin(codes[4]!, codes[5]!);
    const ids: Record<string, string> = {};
    for (const [key, t] of Object.entries(tenants)) {
      const created = (await apiPost(admin, "/api/v1/platform/tenants/", {
        slug: t.slug,
        name: t.name,
        owner_email: t.owner,
        default_locale: "en",
        locales: ["en", "bn"],
        timezone: "Asia/Dhaka",
        currency: "BDT",
        country: "BD",
        institution: {
          institution_type: key === "a" ? "school" : "madrasa",
          code: "main",
          name: `${t.name} School`,
          campus_code: "main",
          campus_name: "Main",
        },
      })) as { id: string };
      ids[key] = created.id;
    }

    // K3 (plan §15.3) through the real stack: rounds of 10 concurrent requests to both tenant
    // hosts, interleaved, through Nginx and the ASGI server (within Nginx's per-IP rate limit);
    // every answer belongs to its own host.
    const stack = await request.newContext({ baseURL: BASE_URL });
    const wrong: unknown[] = [];
    for (let round = 0; round < 10; round++) {
      const answers = await Promise.all(
        Array.from({ length: 10 }, async (_, i) => {
          const t = i % 2 ? tenants.b : tenants.a;
          const response = await stack.get("/api/v1/public/tenant/", {
            headers: { Host: `${t.slug}.localhost:${PORT}` },
          });
          const body = response.ok() ? ((await response.json()) as { name: string }) : null;
          return { expected: t.name, status: response.status(), name: body?.name };
        }),
      );
      wrong.push(...answers.filter((r) => r.status !== 200 || r.name !== r.expected));
      await new Promise((resolve) => setTimeout(resolve, 600));
    }
    expect(wrong).toEqual([]);
    await stack.dispose();

    // Owner of A: invitation → account → MFA enrolment (tenant_owner is privileged).
    const ownerPassword = await joinAndSignIn(
      page,
      tenants.a.slug,
      tenants.a.owner,
      tenants.a.name,
    );
    const ownerSecret = await enrollMfa(page, ownerPassword);
    await expect(page.getByTestId("brand")).toHaveText(tenants.a.name);
    await noSeriousA11yIssues(page);

    // A second campus, then a teacher invited to it.
    await page.getByRole("link", { name: "Institutions" }).first().click();
    await page.getByRole("link", { name: `${tenants.a.name} School` }).click();
    await page.getByRole("button", { name: "New campus" }).click();
    await page.getByRole("dialog").getByLabel("Campus name").fill("North");
    await page.getByRole("dialog").getByLabel("Code").fill("north");
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("North", { exact: true })).toBeVisible();

    const memberEmail = `teacher-${run}@example.test`;
    await page.getByRole("link", { name: "Members" }).first().click();
    await page.getByRole("button", { name: "Invite someone" }).click();
    const invite = page.getByRole("dialog");
    await invite.getByLabel("Email address").fill(memberEmail);
    await invite.getByLabel("Role").selectOption({ label: "Teacher" });
    await invite.getByLabel("Where").selectOption("campus");
    await invite.getByLabel("Institution").selectOption({ label: `${tenants.a.name} School` });
    await invite.getByLabel("Campus").selectOption({ label: "North" });
    await invite.getByRole("button", { name: "Send invitation" }).click();
    await expect(page.getByText(memberEmail)).toBeVisible();

    // The member joins and sees only what the campus-scoped teacher role allows.
    const member = await newPage(browser);
    const memberPassword = await joinAndSignIn(
      member.page,
      tenants.a.slug,
      memberEmail,
      tenants.a.name,
    );
    await expect(member.page).toHaveURL(/\/en\/dashboard$/);
    const nav = member.page.getByRole("navigation", { name: "Main navigation" });
    await expect(nav.getByRole("link", { name: "Settings" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Members" })).toHaveCount(0);
    const membersStatus = await member.page.evaluate(
      async () => (await fetch("/api/v1/members/")).status,
    );
    expect(membersStatus).toBe(403);

    // Tenant B is out of reach: A's session cookie is host-only, so B's host treats the
    // member as signed out; and A's member can't sign in on B's host (generic answer, D7).
    await member.page.goto(`${hostUrl(tenants.b.slug)}/en/dashboard`);
    await expect(member.page).toHaveURL(/\/en\/login$/);
    await expect(member.page.getByTestId("brand")).toHaveText(tenants.b.name);
    // Node can't resolve *.localhost: talk to the same Nginx with B's Host header.
    const b = await request.newContext({
      baseURL: BASE_URL,
      extraHTTPHeaders: { Host: `${tenants.b.slug}.localhost:${PORT}` },
    });
    await b.get("/api/v1/auth/csrf/");
    const bToken = (await b.storageState()).cookies.find((c) => c.name === "csrftoken")?.value;
    const signIn = await b.post("/api/v1/auth/login/", {
      data: { email: memberEmail, password: memberPassword },
      headers: { "X-CSRFToken": bToken ?? "", Origin: hostUrl(tenants.b.slug) },
    });
    expect(signIn.status()).toBe(401);
    expect((await signIn.json()).code).toBe("invalid_credentials");
    await b.dispose();
    await member.page.goto(`${hostUrl(tenants.a.slug)}/en/dashboard`);

    // Support access: requested on the platform, approved by A's owner, visible to members,
    // revoked by the owner.
    await apiPost(admin, "/api/v1/platform/support-sessions/", {
      tenant: ids.a,
      reason: "E2E: investigate a report problem",
      ticket_ref: `E2E-${run}`,
      minutes: 30,
    });
    await page.getByRole("link", { name: "Support access" }).first().click();
    await page.getByRole("button", { name: "Approve" }).click();
    const stepUp = page.getByRole("dialog", { name: "Confirm it's you" });
    if (await stepUp.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await stepUp.getByLabel("Password", { exact: true }).fill(ownerPassword);
      await stepUp
        .getByLabel("Verification code")
        .fill(totp(ownerSecret, Math.floor(Date.now() / 30_000) + 1));
      await stepUp.getByRole("button", { name: "Confirm" }).click();
    }
    await expect(page.getByText("Approved")).toBeVisible();
    await member.page.reload();
    await expect(
      member.page
        .getByRole("status")
        .filter({ hasText: "Platform support has read-only access until" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Revoke" }).click();
    await expect(page.getByText("Revoked")).toBeVisible();
    await member.page.reload();
    await expect(member.page.getByText("Platform support has read-only access until")).toHaveCount(
      0,
    );

    expect(await cspViolations()).toEqual([]);
    await member.context.close();
    await admin.dispose();
  });
});
