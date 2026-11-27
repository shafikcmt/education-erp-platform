import { expect, type Page, test } from "@playwright/test";

import { adminApi, BASE_URL, freshTotp, loadAdmin, totp, trackCspViolations } from "./support";
import {
  catalog,
  enrollMfa,
  joinAndSignIn,
  label,
  newPage,
  noSeriousA11yIssues,
} from "./tenant-flows";

/**
 * Phase 7 M10: students, guardians, staff, timetable, the import and the guardian portal
 * through the real stack (object store, worker, mail). A school organisation enrols a student
 * with a guardian, previews an ID card from a Studio template, adds staff, builds a timetable,
 * imports students from a CSV (a dry run first), and invites the guardian, who then sees only
 * their child and the child's week in the portal. Tenant hosts are enabled in this throwaway
 * stack only.
 */
const ENABLED = Boolean(process.env.E2E_TENANT_HOSTS);
const m = catalog("en");

async function codeAfter(secret: string, afterStep: number): Promise<string> {
  while (Math.floor(Date.now() / 30_000) <= afterStep)
    await new Promise((r) => setTimeout(r, 1_000));
  return totp(secret);
}

/** A same-origin API call from the signed-in page (Node cannot resolve *.localhost). */
async function call(page: Page, method: string, url: string, body?: object) {
  const result = await page.evaluate(
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
  expect(result.status, `${method} ${url}: ${result.body}`).toBeLessThan(300);
  return result.body ? JSON.parse(result.body) : null;
}

/** Confirm the step-up dialog if the action asked for one (the window may have lapsed). */
async function stepUpIfAsked(page: Page, password: string, secret: string) {
  const dialog = page.getByRole("dialog", { name: label(m, "stepUp.title") });
  if (
    !(await dialog.waitFor({ timeout: 4_000 }).then(
      () => true,
      () => false,
    ))
  )
    return;
  await dialog.getByLabel(label(m, "auth.password"), { exact: true }).fill(password);
  await dialog
    .getByLabel(label(m, "auth.mfa.code"))
    .fill(await codeAfter(secret, Math.floor(Date.now() / 30_000)));
  await dialog.getByRole("button", { name: label(m, "stepUp.submit") }).click();
  await expect(dialog).toBeHidden();
}

const iso = (offsetDays: number) =>
  new Date(Date.now() + offsetDays * 86_400_000).toISOString().slice(0, 10);

test.describe("students, staff, timetable, import and the guardian portal", () => {
  test.skip(!ENABLED, "tenant hosts are disabled in this stack (set E2E_TENANT_HOSTS=1)");

  test("enrol with a guardian → staff → timetable → import → the guardian's portal", async ({
    page,
    browser,
  }, info) => {
    test.skip(info.project.name !== "desktop-chromium", "one journey per run");
    test.setTimeout(480_000);
    const run = Date.now().toString(36);
    const org = { slug: `pp${run}`, name: `People ${run}` };
    const ownerEmail = `owner-pp-${run}@example.test`;
    const guardianEmail = `guardian-${run}@example.test`;

    // 1. Platform: a school with the Phase 7 modules.
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
      institution: { institution_type: "school", code: "main", name: `School ${run}` },
    })) as { id: string };
    for (const code of ["academics", "students", "staff", "timetable", "parent_portal"]) {
      await post(`/api/v1/platform/tenants/${tenant.id}/subscription/overrides/`, {
        module: code,
        kind: "grant",
        reason: "E2E pilot for the people journey",
      });
    }
    await api.dispose();

    // 2. The owner joins, enrols MFA and steps up.
    const csp = await trackCspViolations(page);
    const password = await joinAndSignIn(page, org.slug, ownerEmail, org.name);
    const enrolledStep = Math.floor(Date.now() / 30_000);
    const secret = await enrollMfa(page, password);
    await call(page, "POST", "/api/v1/auth/step-up/", {
      password,
      code: await codeAfter(secret, enrolledStep),
    });

    // 3. The structure (tested through its own screens in Phase 6): a year, a class with a
    //    section, a subject taught there, and an ID card template.
    const [institution] = (await call(page, "GET", "/api/v1/institutions/")) as { id: string }[];
    const inst = institution!.id;
    const setup = await call(page, "GET", `/api/v1/academics/setup/?institution=${inst}`);
    const [topLevel, leafLevel] = setup.levels as string[];
    const year = await call(page, "POST", "/api/v1/academics/years/", {
      institution: inst, code: `Y${run}`, name: "2027", start_date: iso(-1), end_date: iso(300),
    }); // prettier-ignore
    const six = await call(page, "POST", "/api/v1/academics/units/", {
      institution: inst, level_key: topLevel, code: "6", name: "Six",
    }); // prettier-ignore
    await call(page, "POST", "/api/v1/academics/units/", {
      institution: inst, level_key: leafLevel, code: "6A", name: "Six A", parent: six.id,
    }); // prettier-ignore
    const units = (await call(page, "GET", `/api/v1/academics/units/?institution=${inst}`)) as {
      id: string;
      code: string;
    }[];
    const sixA = units.find((u) => u.code === "6A")!;
    const maths = await call(page, "POST", "/api/v1/academics/subjects/", {
      institution: inst, code: "M", name: "Maths",
    }); // prettier-ignore
    await call(page, "POST", "/api/v1/academics/offerings/", {
      year: year.id, unit: sixA.id, subject: maths.id,
    }); // prettier-ignore
    await call(page, "POST", "/api/v1/customization/templates/", {
      key: "card", kind: "students.id_card", name: "ID card",
      content: { en: { body: "<p>{{ name }} · {{ number }} · {{ unit }}</p>" } },
    }); // prettier-ignore
    await call(page, "POST", "/api/v1/customization/templates/card/publish/");

    // 4. Students: create, enrol, link and invite a guardian, preview the ID card.
    const nav = page.getByRole("navigation", { name: label(m, "nav.main") });
    await nav.getByRole("link", { name: label(m, "nav.students") }).click();
    await expect(page).toHaveURL(/\/en\/students$/);
    await noSeriousA11yIssues(page);
    await page.getByRole("button", { name: label(m, "students.add") }).click();
    let dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "students.fields.name")).fill("Ana Rahman");
    await dialog.getByLabel(label(m, "students.fields.number")).fill("N-1");
    await dialog.getByRole("button", { name: label(m, "students.save") }).click();
    await expect(page.getByRole("heading", { name: "Ana Rahman" })).toBeVisible();
    await page.getByRole("button", { name: label(m, "students.enroll") }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "students.year")).selectOption({ label: "2027" });
    await dialog.getByLabel(label(m, "students.unit")).selectOption({ label: "Six A (6A)" });
    await dialog.getByLabel(label(m, "students.rollNumber")).fill("1");
    await dialog.getByRole("button", { name: label(m, "students.save") }).click();
    await expect(page.getByTestId("enrollments")).toContainText("Six A");
    await page.getByRole("button", { name: label(m, "students.guardians.add") }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "students.fields.name")).fill("Rina Rahman");
    await dialog.getByLabel(label(m, "students.fields.phone")).fill("01711000001");
    await dialog.getByLabel(label(m, "students.fields.email")).fill(guardianEmail);
    await dialog.getByRole("button", { name: label(m, "students.save") }).click();
    const guardians = page.getByTestId("guardians");
    await expect(guardians).toContainText("Rina Rahman");
    await guardians.getByRole("button", { name: label(m, "students.invite") }).click();
    await stepUpIfAsked(page, password, secret);
    await expect(
      guardians.getByRole("button", { name: label(m, "students.invited") }),
    ).toBeVisible();
    // Accessibility before the preview: axe can't enter a sandboxed frame without scripts.
    await noSeriousA11yIssues(page);
    await page.getByLabel(label(m, "students.actions.template")).fill("card");
    await page.getByRole("button", { name: label(m, "students.actions.idCard") }).click();
    const preview = page.getByTestId("print-preview");
    await expect(preview).toHaveAttribute("sandbox", "");
    await expect(preview).toHaveAttribute("srcdoc", /Ana Rahman · N-1 · Six A/);

    // 5. Staff: a staff member without a login.
    await nav.getByRole("link", { name: label(m, "nav.staff") }).click();
    await page.getByRole("button", { name: label(m, "staff.add") }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "staff.fields.name")).fill("Rahim Uddin");
    await dialog.getByLabel(label(m, "staff.fields.number")).fill("T-1");
    await dialog.getByRole("button", { name: label(m, "staff.save") }).click();
    await expect(page.getByTestId("staff")).toContainText(label(m, "staff.noLogin"));
    await noSeriousA11yIssues(page);

    // 6. Timetable: a bell schedule with a period, a room, and a Monday lesson.
    await nav.getByRole("link", { name: label(m, "nav.timetable") }).click();
    await page.getByRole("button", { name: label(m, "timetable.addSchedule") }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "timetable.code")).fill("DAY");
    await dialog.getByLabel(label(m, "timetable.name")).fill("Day");
    await dialog.getByRole("button", { name: label(m, "timetable.save") }).click();
    await page.getByRole("button", { name: label(m, "timetable.addPeriod") }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "timetable.schedule")).selectOption({ label: "Day" });
    await dialog.getByLabel(label(m, "timetable.name")).fill("P1");
    await dialog.getByLabel(label(m, "timetable.start")).fill("08:00");
    await dialog.getByLabel(label(m, "timetable.end")).fill("08:45");
    await dialog.getByRole("button", { name: label(m, "timetable.save") }).click();
    await page.getByRole("button", { name: label(m, "timetable.addRoom") }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "timetable.code")).fill("R1");
    await dialog.getByLabel(label(m, "timetable.name")).fill("Room 1");
    await dialog.getByRole("button", { name: label(m, "timetable.save") }).click();
    await page.getByLabel(label(m, "timetable.unit")).selectOption({ label: "Six A (6A)" });
    await page.getByRole("button", { name: label(m, "timetable.lesson.add") }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel(label(m, "timetable.lesson.year")).selectOption({ label: "2027" });
    await dialog.getByLabel(label(m, "timetable.lesson.offering")).selectOption({ label: "Maths" });
    await dialog.getByLabel(label(m, "timetable.lesson.period")).selectOption({ index: 1 });
    await dialog.getByLabel(label(m, "timetable.lesson.room")).selectOption({ index: 1 });
    await dialog.getByRole("button", { name: label(m, "timetable.save") }).click();
    await expect(page.getByTestId("week-grid")).toContainText("Maths");
    await noSeriousA11yIssues(page);

    // 7. Import: a CSV through the object store; the dry run reports the bad row, then apply.
    await nav.getByRole("link", { name: label(m, "nav.students") }).click();
    await page.getByRole("link", { name: label(m, "students.import.title") }).click();
    await expect(page).toHaveURL(/\/en\/students\/import$/);
    const csv = "Name,Number,Class,Roll\nBo Karim,N-2,6A,2\n,N-3,6A,3\n";
    await page
      .getByLabel(label(m, "students.import.file"))
      .setInputFiles({ name: "students.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
    await stepUpIfAsked(page, password, secret);
    await expect(page.getByText(label(m, "students.import.ready"))).toBeVisible({
      timeout: 60_000,
    });
    await page
      .getByLabel(label(m, "students.import.targets.unit"), { exact: true })
      .selectOption("Class");
    await page
      .getByLabel(label(m, "students.import.targets.roll_number"), { exact: true })
      .selectOption("Roll");
    await page.getByLabel(label(m, "students.import.year")).selectOption({ label: "2027" });
    await page.getByRole("button", { name: label(m, "students.import.start") }).click();
    await stepUpIfAsked(page, password, secret);
    const summary = page.getByTestId("import-summary");
    await expect(summary).toHaveText(label(m, "students.import.rows", { ok: "1", total: "2" }), {
      timeout: 60_000,
    });
    await expect(page.getByTestId("import-errors")).toContainText("name");
    await page.getByRole("button", { name: label(m, "students.import.apply") }).click();
    await stepUpIfAsked(page, password, secret);
    await expect(page.getByText(label(m, "students.import.statuses.applied"))).toBeVisible({
      timeout: 60_000,
    });
    await nav.getByRole("link", { name: label(m, "nav.students") }).click();
    await expect(page.getByTestId("students")).toContainText("Bo Karim");

    // 8. The guardian accepts the invitation and sees only their child and the week.
    const guardian = await newPage(browser);
    const guardianCsp = await trackCspViolations(guardian.page);
    await joinAndSignIn(guardian.page, org.slug, guardianEmail, org.name);
    await expect(guardian.page).toHaveURL(/\/en\/dashboard$/);
    const guardianNav = guardian.page.getByRole("navigation", { name: label(m, "nav.main") });
    await guardianNav.getByRole("link", { name: label(m, "nav.portal") }).click();
    await expect(guardian.page.getByTestId("child")).toContainText("N-1");
    await expect(guardian.page.getByTestId("child")).toContainText("Six A");
    await expect(guardian.page.getByTestId("week-grid")).toContainText("Maths");
    await expect(guardian.page.getByText("Bo Karim")).toHaveCount(0);
    await noSeriousA11yIssues(guardian.page);
    expect(await guardianCsp()).toEqual([]);
    await guardian.context.close();
    expect(await csp()).toEqual([]);
  });
});
