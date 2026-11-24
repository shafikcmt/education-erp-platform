import { expect, type Page, test } from "@playwright/test";

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
  hostUrl,
  joinAndSignIn,
  label,
  newPage,
  noSeriousA11yIssues,
} from "./tenant-flows";

/**
 * Phase 6 M8: academic structure and the public admission journey through the real stack:
 * a madrasa organisation builds its structure in its own terminology, publishes an
 * application form, opens a cycle; an applicant applies, confirms by email, uploads a document
 * to the object store (presigned POST), and accepts the offer made down the merit list.
 * Tenant hosts are enabled in this throwaway stack only.
 */
const ENABLED = Boolean(process.env.E2E_TENANT_HOSTS);
const m = catalog("en");
const LAYOUT = {
  sections: [
    {
      key: "applicant",
      labels: { en: "Applicant", bn: "আবেদনকারী" },
      fields: [
        { source: "core", name: "applicant_name", required: true },
        { source: "core", name: "applicant_email", required: true },
        { source: "core", name: "guardian_name" },
      ],
    },
  ],
};
const FLOW = {
  states: [
    { key: "screening", labels: { en: "Screening" } },
    { key: "done", labels: { en: "Done" }, final: true },
  ],
  initial: "screening",
  start_permission: "admissions.application.review",
  transitions: [
    {
      key: "complete",
      from: ["screening"],
      to: "done",
      labels: { en: "Complete" },
      permission: "admissions.application.review",
    },
  ],
};
// The smallest valid PDF header is enough: the server checks size and declared type.
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

async function codeAfter(secret: string, afterStep: number): Promise<string> {
  while (Math.floor(Date.now() / 30_000) <= afterStep)
    await new Promise((r) => setTimeout(r, 1_000));
  return totp(secret);
}

/** A same-origin API call from the signed-in page (Node cannot resolve *.localhost). */
async function call(page: Page, method: string, url: string, body?: object) {
  return page.evaluate(
    async ([method, url, body]) => {
      const csrf = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)?.[1] ?? "";
      const response = await fetch(url as string, {
        method: method as string,
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: body ? JSON.stringify(body) : undefined,
      });
      return { status: response.status, body: await response.text() };
    },
    [method, url, body] as const,
  );
}

async function confirmStepUp(page: Page, password: string, code: () => Promise<string>) {
  const dialog = page.getByRole("dialog", { name: label(m, "stepUp.title") });
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

const iso = (offsetDays: number) =>
  new Date(Date.now() + offsetDays * 86_400_000).toISOString().slice(0, 10);

test.describe("academic structure and the public admission journey", () => {
  test.skip(!ENABLED, "tenant hosts are disabled in this stack (set E2E_TENANT_HOSTS=1)");

  test("structure in the preset's words; apply → verify → upload → review → test → merit → accept", async ({
    page,
    browser,
  }, info) => {
    test.skip(info.project.name !== "desktop-chromium", "one journey per run");
    test.setTimeout(420_000);
    const run = Date.now().toString(36);
    const org = { slug: `ad${run}`, name: `Admissions ${run}` };
    const ownerEmail = `owner-adm-${run}@example.test`;

    // 1. Platform: a madrasa organisation with the academics and admissions modules.
    const { api, post } = await adminApi();
    const admin = loadAdmin();
    for (let attempt = 0; attempt < 3; attempt++) {
      const csrf = (await api.storageState()).cookies.find((c) => c.name === "csrftoken")?.value;
      const response = await api.post("/api/v1/auth/step-up/", {
        data: { password: admin.password, code: await freshTotp(admin.secret) },
        headers: { "X-CSRFToken": csrf ?? "", Referer: BASE_URL },
      });
      if (response.ok()) break;
    }
    const tenant = (await post("/api/v1/platform/tenants/", {
      slug: org.slug,
      name: org.name,
      owner_email: ownerEmail,
      default_locale: "en",
      locales: ["en", "bn"],
      timezone: "Asia/Dhaka",
      currency: "BDT",
      country: "BD",
      institution: { institution_type: "madrasa", code: "main", name: `Madrasa ${run}` },
    })) as { id: string };
    for (const code of ["academics", "admissions"]) {
      await post(`/api/v1/platform/tenants/${tenant.id}/subscription/overrides/`, {
        module: code,
        kind: "grant",
        reason: "E2E pilot for the admissions journey",
      });
    }
    await api.dispose();

    // 2. The owner joins, enrols MFA and steps up once for the publications below.
    const csp = await trackCspViolations(page);
    const password = await joinAndSignIn(page, org.slug, ownerEmail, org.name);
    const enrolledStep = Math.floor(Date.now() / 30_000);
    const secret = await enrollMfa(page, password);
    const stepUp = await call(page, "POST", "/api/v1/auth/step-up/", {
      password,
      code: await codeAfter(secret, enrolledStep),
    });
    expect(stepUp.status, stepUp.body).toBe(200);

    // 3. Academics: the structure levels carry the madrasa preset's names.
    const nav = page.getByRole("navigation", { name: label(m, "nav.main") });
    await nav.getByRole("link", { name: label(m, "nav.academics") }).click();
    await expect(page).toHaveURL(/\/en\/academics$/);
    await noSeriousA11yIssues(page);
    await page.getByRole("button", { name: label(m, "academics.years.add") }).click();
    let dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "academics.code")).fill(`Y${run}`);
    await dialog.getByLabel(label(m, "academics.name")).fill("Session 1448");
    await dialog.getByLabel(label(m, "academics.years.start")).fill(iso(30));
    await dialog.getByLabel(label(m, "academics.years.end")).fill(iso(390));
    await dialog.getByRole("button", { name: label(m, "academics.save") }).click();
    await expect(page.getByTestId("years")).toContainText("Session 1448");
    for (const [level, code, name, parent] of [
      ["Marhala", "m1", "Ibtidaiyyah", ""],
      ["Jamaat", "j1", "First Jamaat", "Ibtidaiyyah"],
    ] as const) {
      await page.getByRole("button", { name: label(m, "academics.units.add") }).click();
      dialog = page.getByRole("dialog");
      await dialog.getByLabel(label(m, "academics.units.level")).selectOption({ label: level });
      if (parent) {
        await dialog
          .getByLabel(label(m, "academics.units.parent"))
          .selectOption({ label: `Marhala · ${parent}` });
      }
      await dialog.getByLabel(label(m, "academics.code")).fill(code);
      await dialog.getByLabel(label(m, "academics.name")).fill(name);
      await dialog.getByRole("button", { name: label(m, "academics.save") }).click();
      await expect(page.getByTestId("units")).toContainText(name);
    }
    await expect(page.getByTestId("units")).toContainText("Jamaat");

    // 4. Studio: the application form (published with the fresh step-up).
    const draft = await call(page, "POST", "/api/v1/customization/forms/", {
      key: "admission",
      entity: "admissions.application",
      name: "Admission form",
      layout: LAYOUT,
    });
    expect(draft.status, draft.body).toBeLessThan(300);
    const published = await call(page, "POST", "/api/v1/customization/forms/admission/publish/");
    expect(published.status, published.body).toBeLessThan(300);

    const flow = await call(page, "POST", "/api/v1/customization/workflows/", {
      key: "screening",
      subject: "admissions.application",
      name: "Screening",
      spec: FLOW,
    });
    expect(flow.status, flow.body).toBeLessThan(300);
    const flowPublished = await call(
      page,
      "POST",
      "/api/v1/customization/workflows/screening/publish/",
    );
    expect(flowPublished.status, flowPublished.body).toBeLessThan(300);

    // 5. Admissions: a cycle (form + review workflow) with one target, opened.
    await nav.getByRole("link", { name: label(m, "nav.admissions") }).click();
    await expect(page).toHaveURL(/\/en\/admissions$/);
    await page.getByRole("button", { name: label(m, "admissions.cycles.add") }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "admissions.cycles.fields.code")).fill(`c${run}`);
    await dialog.getByLabel(label(m, "admissions.cycles.fields.name")).fill("Admission 1448");
    await dialog.getByLabel(label(m, "admissions.cycles.fields.opens_on")).fill(iso(-1));
    await dialog.getByLabel(label(m, "admissions.cycles.fields.closes_on")).fill(iso(30));
    await dialog.getByLabel(label(m, "admissions.cycles.fields.form_key")).fill("admission");
    await dialog.getByLabel(label(m, "admissions.cycles.fields.workflow_key")).fill("screening");
    await dialog.getByRole("button", { name: label(m, "admissions.save") }).click();
    const cycleRow = page.getByTestId("cycles").getByRole("listitem").first();
    await expect(cycleRow).toContainText("Admission 1448");
    await cycleRow.getByRole("button", { name: label(m, "admissions.cycles.addTarget") }).click();
    dialog = page.getByRole("dialog");
    await dialog
      .getByLabel(label(m, "admissions.cycles.unit"))
      .selectOption({ label: "First Jamaat (j1)" });
    await dialog.getByLabel(label(m, "admissions.cycles.capacity")).fill("1");
    await dialog.getByRole("button", { name: label(m, "admissions.save") }).click();
    await expect(cycleRow).toContainText("First Jamaat");
    await cycleRow
      .getByRole("button", { name: label(m, "admissions.cycles.to.open"), exact: true })
      .click();
    await expect(cycleRow).toContainText(label(m, "admissions.cycles.statuses.open"));
    await noSeriousA11yIssues(page);

    // 6. An applicant applies on the organisation's host and confirms by email.
    const applicantEmail = `applicant-${run}@example.test`;
    const applicant = await newPage(browser);
    const applicantCsp = await trackCspViolations(applicant.page);
    await applicant.page.goto(`${hostUrl(org.slug)}/en/apply`);
    await expect(
      applicant.page.getByRole("heading", { name: label(m, "apply.title") }),
    ).toBeVisible();
    await applicant.page.getByLabel(/applicant_name/).fill("Abdullah Rahman");
    await applicant.page.getByLabel(/applicant_email/).fill(applicantEmail);
    await noSeriousA11yIssues(applicant.page);
    await applicant.page.getByRole("button", { name: label(m, "apply.send") }).click();
    await expect(applicant.page.getByText(label(m, "apply.sent"))).toBeVisible();
    const verifyMail = await waitForMail(applicantEmail, /Confirm your application/);
    await applicant.page.goto(hostUrl(org.slug) + linkFrom(verifyMail, "apply/verify"));
    await expect(applicant.page).not.toHaveURL(/#token=/);
    await applicant.page.getByRole("button", { name: label(m, "apply.confirm") }).click();
    await expect(applicant.page.getByText(label(m, "apply.verified"))).toBeVisible();
    const statusMail = await waitForMail(applicantEmail, /Your application to/);
    const statusLink = hostUrl(org.slug) + linkFrom(statusMail, "apply/status");

    // 7. With the status link: the status, and a document uploaded to the object store.
    await applicant.page.goto(statusLink);
    const status = applicant.page.getByTestId("status");
    await expect(status).toHaveText(label(m, "admissions.statuses.submitted"));
    await applicant.page
      .getByLabel(label(m, "apply.addDocument"))
      .setInputFiles({ name: "birth-certificate.pdf", mimeType: "application/pdf", buffer: PDF });
    await expect(applicant.page.getByText("birth-certificate.pdf")).toBeVisible();

    // 8. Staff: the document is verified in the object store; review through the workflow,
    //    a test score, the merit list (step-up) and the offer.
    await page.reload();
    await cycleRow.getByRole("button", { name: label(m, "admissions.cycles.manage") }).click();
    const panel = page.getByRole("region", { name: "Admission 1448" });
    const application = page.getByTestId("applications").getByRole("listitem").first();
    await expect(application).toContainText("Abdullah Rahman");
    await expect(async () => {
      await page.reload();
      await cycleRow.getByRole("button", { name: label(m, "admissions.cycles.manage") }).click();
      await application
        .getByRole("button", { name: label(m, "admissions.applications.documents") })
        .click();
      await expect(
        application.getByRole("button", { name: label(m, "admissions.documents.download") }),
      ).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 60_000 });
    await application
      .getByRole("button", { name: label(m, "admissions.applications.startReview") })
      .click();
    await expect(application).toContainText(label(m, "admissions.statuses.under_review"));
    // The review workflow started when staff took the public application in; finish it.
    const workflow = application.getByTestId("workflow");
    await expect(workflow).toContainText("screening");
    await workflow.getByRole("button", { name: "complete" }).click();
    await expect(workflow).toContainText(
      label(m, "admissions.applications.workflowDone", { state: "done" }),
    );
    // An admission test: schedule it, seat the applicant, enter the score.
    await panel.getByRole("tab", { name: label(m, "admissions.panels.tests") }).click();
    await page.getByRole("button", { name: label(m, "admissions.tests.add") }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "admissions.tests.fields.name")).fill("Written test");
    await dialog.getByLabel(label(m, "admissions.tests.fields.starts_at")).fill(`${iso(2)}T10:00`);
    await dialog.getByLabel(label(m, "admissions.tests.fields.venue")).fill("Hall A");
    await dialog.getByLabel(label(m, "admissions.tests.fields.capacity")).fill("20");
    await dialog.getByLabel(label(m, "admissions.tests.fields.max_score")).fill("100");
    await dialog.getByRole("button", { name: label(m, "admissions.save") }).click();
    await page.getByRole("button", { name: label(m, "admissions.tests.seatList") }).click();
    await page.getByRole("button", { name: label(m, "admissions.tests.seat") }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "admissions.applications.one")).selectOption({ index: 1 });
    await dialog.getByRole("button", { name: label(m, "admissions.tests.seat") }).click();
    const seats = page.getByTestId("seat-list");
    await expect(seats).toContainText("Abdullah Rahman");
    await seats.getByLabel(label(m, "admissions.tests.enterScore", { seat: "1" })).fill("72.5");
    await seats.getByRole("button", { name: label(m, "admissions.save") }).click();
    await expect(seats).toContainText(label(m, "admissions.tests.score", { score: "72.50" }));
    await panel.getByRole("tab", { name: label(m, "admissions.panels.applications") }).click();
    await expect(application).toContainText(label(m, "admissions.statuses.evaluated"));
    await panel.getByRole("tab", { name: label(m, "admissions.panels.merit") }).click();
    await page.getByRole("button", { name: label(m, "admissions.merit.publish") }).click();
    await confirmStepUp(page, password, () => codeAfter(secret, Math.floor(Date.now() / 30_000)));
    await expect(page.getByTestId("merit")).toContainText("Abdullah Rahman");
    await page.getByRole("button", { name: label(m, "admissions.merit.offer") }).click();
    await panel.getByRole("tab", { name: label(m, "admissions.panels.applications") }).click();
    await expect(application).toContainText(label(m, "admissions.statuses.offered"));

    // 9. The applicant accepts the offer with the status link.
    await applicant.page.goto(statusLink);
    await expect(status).toHaveText(label(m, "admissions.statuses.offered"));
    await applicant.page.getByRole("button", { name: label(m, "apply.accept") }).click();
    await expect(status).toHaveText(label(m, "admissions.statuses.accepted"));
    expect(await applicantCsp()).toEqual([]);
    await applicant.context.close();
    expect(await csp()).toEqual([]);
  });
});
