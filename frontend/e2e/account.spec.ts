import AxeBuilder from "@axe-core/playwright";
import { type Browser, expect, type Page, test } from "@playwright/test";

import { adminApi, linkFrom, strongPassword, uniqueEmail, waitForMail } from "./support";

/**
 * Plan §10 frontend E2E, per project (desktop + mobile) and per locale (en + bn):
 * activation via Mailpit → sign-in → session revoke → step-up dialog → idle-timeout warning →
 * sign-out → password reset via Mailpit → sign-in with the new password; axe on auth pages.
 */
const LOCALES = {
  en: {
    newPassword: "New password",
    confirm: "Confirm new password",
    activate: "Activate account",
    activated: "Your account is active",
    email: "Email address",
    password: "Password",
    signIn: "Sign in",
    revokeOthers: "Sign out all other sessions",
    newEmail: "New email address",
    changeEmail: "Change email",
    emailSent: "Check the new address",
    stepUpConfirm: "Confirm",
    stay: "Stay signed in",
    signOut: "Sign out",
    forgot: "Forgot your password?",
    sendReset: "Send reset link",
    resetSent: "If the address belongs",
    setPassword: "Set new password",
    resetDone: "Your password was changed",
  },
  bn: {
    newPassword: "নতুন পাসওয়ার্ড",
    confirm: "নতুন পাসওয়ার্ড আবার লিখুন",
    activate: "অ্যাকাউন্ট চালু করুন",
    activated: "আপনার অ্যাকাউন্ট চালু হয়েছে",
    email: "ইমেইল ঠিকানা",
    password: "পাসওয়ার্ড",
    signIn: "সাইন ইন করুন",
    revokeOthers: "অন্য সব সেশন থেকে সাইন আউট",
    newEmail: "নতুন ইমেইল ঠিকানা",
    changeEmail: "ইমেইল পরিবর্তন করুন",
    emailSent: "নিশ্চিতকরণ লিংকের জন্য",
    stepUpConfirm: "নিশ্চিত করুন",
    stay: "সাইন ইন থাকুন",
    signOut: "সাইন আউট",
    forgot: "পাসওয়ার্ড ভুলে গেছেন?",
    sendReset: "রিসেট লিংক পাঠান",
    resetSent: "ঠিকানাটি কোনো সক্রিয় অ্যাকাউন্টের হলে",
    setPassword: "নতুন পাসওয়ার্ড সেট করুন",
    resetDone: "আপনার পাসওয়ার্ড পরিবর্তন হয়েছে",
  },
} as const;
type Locale = keyof typeof LOCALES;

async function a11y(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact ?? ""),
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

async function signIn(page: Page, locale: Locale, email: string, password: string) {
  const L = LOCALES[locale];
  await page.goto(`/${locale}/login`);
  await page.getByLabel(L.email).fill(email);
  await page.getByLabel(L.password, { exact: true }).fill(password);
  await page.getByRole("button", { name: L.signIn, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/${locale}/dashboard$`));
}

async function newSession(browser: Browser) {
  const context = await browser.newContext();
  return { context, page: await context.newPage() };
}

// English on desktop, Bengali on mobile: both locales and both viewports, while keeping the
// number of sign-ins from the single E2E IP under the per-IP login limit (plan §6.2).
test("account lifecycle and security", async ({ page, browser }, testInfo) => {
  test.setTimeout(180_000);
  const locale: Locale = testInfo.project.name.startsWith("mobile") ? "bn" : "en";
  const L = LOCALES[locale];
  const email = uniqueEmail(`user-${locale}`);
  let password = strongPassword();

  const { api, post } = await adminApi();
  await post("/api/v1/platform/users/", { email, locale, display_name: "E2E" });
  await api.dispose();

  // Activation (email is in the user's language).
  const mail = await waitForMail(email, locale === "bn" ? /চালু/ : /Activate/);
  await page.clock.install();
  await page.goto(linkFrom(mail, "activate"));
  await a11y(page);
  await page.getByLabel(L.newPassword, { exact: true }).fill(password);
  await page.getByLabel(L.confirm).fill(password);
  await page.getByRole("button", { name: L.activate }).click();
  await expect(page.getByText(L.activated)).toBeVisible();

  await signIn(page, locale, email, password);
  await page.goto(`/${locale}/account/security`);

  // A second session elsewhere, then revoke it from here.
  const other = await newSession(browser);
  await signIn(other.page, locale, email, password);
  await page.reload();
  await expect(page.getByTestId("sessions").locator("li")).toHaveCount(2);
  await page.getByRole("button", { name: L.revokeOthers }).click();
  await expect(page.getByTestId("sessions").locator("li")).toHaveCount(1);
  await other.page.goto(`/${locale}/account/security`);
  await expect(other.page).toHaveURL(new RegExp(`/${locale}/login$`));
  await other.context.close();

  // Step-up dialog on a sensitive action (no MFA for this ordinary account: password only).
  await page.getByLabel(L.newEmail).fill(uniqueEmail("moved"));
  await page.getByRole("button", { name: L.changeEmail }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByLabel(L.password, { exact: true }).fill(password);
  await dialog.getByRole("button", { name: L.stepUpConfirm }).click();
  await expect(page.getByText(L.emailSent)).toBeVisible();

  // Idle-timeout warning two minutes before the 30-minute limit.
  await page.clock.fastForward("28:30");
  await expect(page.getByTestId("idle-warning")).toBeVisible();
  await page.getByRole("button", { name: L.stay }).click();
  await expect(page.getByTestId("idle-warning")).toBeHidden();

  // Sign out, then reset the password through Mailpit.
  await page.getByRole("button", { name: L.signOut }).first().click();
  await expect(page).toHaveURL(new RegExp(`/${locale}/login$`));
  await page.getByRole("link", { name: L.forgot }).click();
  await a11y(page);
  await page.getByLabel(L.email).fill(email);
  await page.getByRole("button", { name: L.sendReset }).click();
  await expect(page.getByText(L.resetSent)).toBeVisible();
  const reset = await waitForMail(email, locale === "bn" ? /রিসেট/ : /Reset your password/);
  await page.goto(linkFrom(reset, "reset-password"));
  await a11y(page);
  password = strongPassword();
  await page.getByLabel(L.newPassword, { exact: true }).fill(password);
  await page.getByLabel(L.confirm).fill(password);
  await page.getByRole("button", { name: L.setPassword }).click();
  await expect(page.getByText(L.resetDone)).toBeVisible();
  await signIn(page, locale, email, password);
});

test("unknown and wrong-password sign-ins look identical", async ({ page }) => {
  const messages: string[] = [];
  for (const email of [uniqueEmail("nobody"), "e2e-admin@example.test"]) {
    await page.goto("/en/login");
    await page.getByLabel("Email address").fill(email);
    await page.getByLabel("Password").fill("Definitely-wrong-123");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    messages.push((await page.getByRole("alert").textContent()) ?? "");
  }
  expect(messages[0]).toBe(messages[1]);
});

test("signed-out visitors are sent to sign-in", async ({ page }) => {
  await page.goto("/en/account/security");
  await expect(page).toHaveURL(/\/en\/login$/);
});
