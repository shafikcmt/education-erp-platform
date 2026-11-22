import { readFileSync } from "node:fs";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { type APIRequestContext, type Browser, expect, type Page, request } from "@playwright/test";

import { BASE_URL, linkFrom, loadAdmin, strongPassword, totp, waitForMail } from "./support";

/** Shared steps of the tenant-host journeys (Phase 3 M10, Phase 4 M7). */

/** Labels come straight from the message catalogues, so the journey runs in both languages. */
export type Messages = Record<string, Record<string, unknown>>;
export const catalog = (locale: "en" | "bn"): Messages =>
  JSON.parse(
    readFileSync(path.join(import.meta.dirname, `../src/messages/${locale}.json`), "utf8"),
  ) as Messages;
export function label(
  messages: Messages,
  dotted: string,
  values: Record<string, string> = {},
): string {
  const value = dotted.split(".").reduce<unknown>((node, key) => (node as Messages)[key], messages);
  return Object.entries(values).reduce(
    (text, [key, v]) => text.replace(`{${key}}`, v),
    String(value),
  );
}
export const PORT = new URL(BASE_URL).port || "80";
export const hostUrl = (slug: string) => `http://${slug}.localhost:${PORT}`;

export async function noSeriousA11yIssues(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact ?? ""),
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

/** Platform API session of the bootstrap admin with single-use recovery codes (no TOTP step
 * shared with other workers). */
export async function platformAdmin(
  loginCode: string,
  stepUpCode: string,
): Promise<APIRequestContext> {
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

export async function apiPost(api: APIRequestContext, url: string, data: object) {
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
export async function joinAndSignIn(
  page: Page,
  slug: string,
  email: string,
  tenantName: string,
  locale: "en" | "bn" = "en",
) {
  const m = catalog(locale);
  const password = strongPassword();
  const mail = await waitForMail(email, new RegExp(tenantName));
  const link = linkFrom(mail, "accept-invitation").replace(/^\/(en|bn)\//, `/${locale}/`);
  await page.goto(hostUrl(slug) + link);
  await expect(page).not.toHaveURL(/#token=/);
  await expect(
    page.getByRole("heading", { name: label(m, "tenancy.accept.title", { name: tenantName }) }),
  ).toBeVisible();
  await expect(page.getByTestId("brand")).toHaveText(tenantName);
  await noSeriousA11yIssues(page);
  await page.getByLabel(label(m, "account.displayName")).fill(email.split("@")[0]!);
  await page.getByLabel(label(m, "auth.password")).fill(password);
  await page.getByRole("button", { name: label(m, "tenancy.accept.submit") }).click();
  await expect(page.getByText(label(m, "tenancy.accept.createdDone"))).toBeVisible();
  await page.getByRole("link", { name: label(m, "tenancy.accept.goToSignIn") }).click();
  await page.getByLabel(label(m, "auth.email")).fill(email);
  await page.getByLabel(label(m, "auth.password")).fill(password);
  await page.getByRole("button", { name: label(m, "auth.login.submit"), exact: true }).click();
  return password;
}

/** Privileged tenant role → MFA enrolment on the tenant host (manual key behind a step-up). */
export async function enrollMfa(
  page: Page,
  password: string,
  locale: "en" | "bn" = "en",
): Promise<string> {
  const m = catalog(locale);
  await expect(page).toHaveURL(new RegExp(`/${locale}/login/mfa-setup$`));
  await page.getByRole("button", { name: label(m, "mfaSetup.cantScan") }).click();
  await page.getByRole("dialog").getByLabel(label(m, "auth.password")).fill(password);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: label(m, "stepUp.submit") })
    .click();
  const secret = (await page.getByTestId("manual-key").textContent())!.replaceAll(" ", "");
  await page.getByLabel(label(m, "mfaSetup.codeLabel")).fill(totp(secret));
  await page.getByRole("button", { name: label(m, "mfaSetup.confirm") }).click();
  await expect(page.getByTestId("recovery-codes").locator("li")).toHaveCount(10);
  await page.getByLabel(label(m, "mfaSetup.ack")).check();
  await page.getByRole("button", { name: label(m, "mfaSetup.continue") }).click();
  await expect(page).toHaveURL(new RegExp(`/${locale}/dashboard$`));
  return secret;
}

export async function newPage(browser: Browser) {
  const context = await browser.newContext();
  return { context, page: await context.newPage() };
}
