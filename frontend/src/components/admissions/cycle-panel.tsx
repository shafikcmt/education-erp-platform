"use client";

import type { Schemas } from "@erp/api-client";
import { useQuery } from "@tanstack/react-query";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { ActionDialog, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, localName, useTenantContext } from "@/lib/tenancy/context";

import { ADMISSIONS_KEY, Tabs, useAdmissionsRefresh, useStatusName } from "./shared";
import { StaffEntry } from "./staff-entry";
import { TestCard } from "./tests-section";

type Cycle = Schemas["Cycle"];
type Application = Schemas["Application"];
const PANELS = ["applications", "tests", "merit"] as const;
const SEATABLE = new Set(["submitted", "under_review", "test_scheduled"]);
const AWAITING = new Set(["submitted", "under_review", "evaluated"]);

/** One cycle: its applications (review, decision, documents), tests and merit lists. */
export function CyclePanel({ cycle }: { cycle: Cycle }) {
  const t = useTranslations("admissions");
  const locale = useLocale();
  const { data: context } = useTenantContext();
  const panels = PANELS.filter((p) =>
    canAnywhere(context, p === "tests" ? "admissions.test.manage" : "admissions.application.view"),
  );
  const [active, setActive] = useState<(typeof PANELS)[number] | null>(null);
  const current = active ?? panels[0] ?? null;
  const applications = useQuery({
    queryKey: [...ADMISSIONS_KEY, "applications", cycle.id],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/admissions/applications/", { params: { query: { cycle: cycle.id } } }),
      ),
    enabled: canAnywhere(context, "admissions.application.view"),
  });
  return (
    <section aria-label={localName(cycle, locale)} className="grid gap-3">
      <h2 className="text-lg font-semibold">{localName(cycle, locale)}</h2>
      {current ? (
        <Tabs
          label={localName(cycle, locale)}
          tabs={panels}
          current={current}
          onChange={setActive}
          name={(key) => t(`panels.${key}`)}
        />
      ) : null}
      {current === "applications" ? (
        <ApplicationsPanel cycle={cycle} rows={applications.data ?? []} />
      ) : null}
      {current === "tests" ? <TestsPanel cycle={cycle} rows={applications.data} /> : null}
      {current === "merit" ? <MeritPanel cycle={cycle} /> : null}
    </section>
  );
}

function ApplicationsPanel({ cycle, rows }: { cycle: Cycle; rows: Application[] }) {
  const t = useTranslations("admissions");
  const statusName = useStatusName();
  const { data: context } = useTenantContext();
  const review = canAnywhere(context, "admissions.application.review");
  const decide = canAnywhere(context, "admissions.application.decide");
  const refresh = useAdmissionsRefresh();
  const { run, failure } = useAction();
  const [docs, setDocs] = useState<string | null>(null);
  const units = Object.fromEntries(cycle.targets.map((g) => [g.id, g.unit_name]));
  const act = (path: "review" | "evaluate", id: string) =>
    run(async () => {
      const call =
        path === "review"
          ? api().POST("/api/v1/admissions/applications/{application_id}/review/", {
              params: { path: { application_id: id } },
            })
          : api().POST("/api/v1/admissions/applications/{application_id}/evaluate/", {
              params: { path: { application_id: id } },
            });
      await unwrap(call);
      await refresh();
    });
  const answer = (id: string, accept: boolean) =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/admissions/applications/{application_id}/offer-response/", {
          params: { path: { application_id: id } },
          body: { accept },
        }),
      );
      await refresh();
    });
  return (
    <Card>
      <CardContent className="grid gap-2 pt-6">
        {review && cycle.status === "open" ? (
          <div className="flex justify-end">
            <StaffEntry cycle={cycle} onDone={() => void refresh()} />
          </div>
        ) : null}
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        {rows.length ? (
          <ul className="grid gap-2 text-sm" data-testid="applications">
            {rows
              .filter((a) => a.status !== "draft")
              .map((a) => (
                <li key={a.id} className="grid gap-1 rounded-md border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span>
                      <span className="font-medium">{a.applicant_name}</span>{" "}
                      <span className="text-muted-foreground text-xs">
                        {[a.number, units[a.target], statusName(a.status)]
                          .filter(Boolean)
                          .join(" · ")}
                        {a.score !== null
                          ? ` · ${t("applications.score", { score: a.score })}`
                          : ""}
                        {a.merit_rank ? ` · ${t("applications.rank", { rank: a.merit_rank })}` : ""}
                      </span>
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {review && a.status === "submitted" && !a.workflow_instance_id ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void act("review", a.id)}
                        >
                          {t("applications.startReview")}
                        </Button>
                      ) : null}
                      {review && (a.status === "submitted" || a.status === "under_review") ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => void act("evaluate", a.id)}
                        >
                          {t("applications.evaluate")}
                        </Button>
                      ) : null}
                      {decide && AWAITING.has(a.status) ? <Decide application={a} /> : null}
                      {decide && a.status === "offered" ? (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void answer(a.id, true)}
                          >
                            {t("applications.accepted")}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => void answer(a.id, false)}
                          >
                            {t("applications.declined")}
                          </Button>
                        </>
                      ) : null}
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-expanded={docs === a.id}
                        onClick={() => setDocs(docs === a.id ? null : a.id)}
                      >
                        {t("applications.documents")}
                      </Button>
                    </div>
                  </div>
                  {a.workflow_instance_id ? (
                    <WorkflowControl instance={a.workflow_instance_id} />
                  ) : null}
                  {docs === a.id ? <Documents application={a.id} /> : null}
                </li>
              ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{t("applications.none")}</p>
        )}
      </CardContent>
    </Card>
  );
}

/** The application's review request: its state and the transitions this member may take
 * (each transition is checked by the server with its own permission). */
function WorkflowControl({ instance }: { instance: string }) {
  const t = useTranslations("admissions");
  const refresh = useAdmissionsRefresh();
  const { run, failure } = useAction();
  const request = useQuery({
    queryKey: [...ADMISSIONS_KEY, "workflow", instance],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/customization/workflow-requests/{instance_id}/", {
          params: { path: { instance_id: instance } },
        }),
      ),
  });
  const take = (transition: string) =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/customization/workflow-requests/{instance_id}/transition/", {
          params: { path: { instance_id: instance } },
          body: { transition, note: "" },
        }),
      );
      await refresh();
    });
  const row = request.data;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="workflow">
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <span className="text-muted-foreground">
        {row
          ? row.finished_at
            ? t("applications.workflowDone", { state: row.state })
            : t("applications.workflowState", { state: row.state })
          : t("applications.inWorkflow")}
      </span>
      {row && !row.finished_at
        ? row.actions.map((action) => (
            <Button key={action} size="sm" variant="outline" onClick={() => void take(action)}>
              {action}
            </Button>
          ))
        : null}
    </div>
  );
}

function Decide({ application }: { application: Application }) {
  const t = useTranslations("admissions");
  const refresh = useAdmissionsRefresh();
  const [decision, setDecision] = useState<"offered" | "rejected">("offered");
  const [note, setNote] = useState("");
  return (
    <ActionDialog
      trigger={<Button size="sm">{t("applications.decide")}</Button>}
      title={t("applications.decideTitle", { name: application.applicant_name })}
      description={t("applications.decideHint")}
      submit={t("save")}
      onSubmit={async () => {
        await unwrap(
          api().POST("/api/v1/admissions/applications/{application_id}/decision/", {
            params: { path: { application_id: application.id } },
            body: { decision, note },
          }),
        );
        await refresh();
      }}
    >
      <fieldset className="grid gap-2 text-sm">
        <legend className="sr-only">{t("applications.decide")}</legend>
        {(["offered", "rejected"] as const).map((d) => (
          <label key={d} className="flex items-center gap-2">
            <input
              type="radio"
              name="decision"
              checked={decision === d}
              onChange={() => setDecision(d)}
            />
            {t(`applications.${d === "offered" ? "offer" : "reject"}`)}
          </label>
        ))}
      </fieldset>
      <Field id="decision-note" label={t("applications.note")} hint={t("applications.noteHint")}>
        {(aria) => (
          <Input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} {...aria} />
        )}
      </Field>
    </ActionDialog>
  );
}

function Documents({ application }: { application: string }) {
  const t = useTranslations("admissions");
  const { run, failure } = useAction();
  const files = useQuery({
    queryKey: [...ADMISSIONS_KEY, "documents", application],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/admissions/applications/{application_id}/documents/", {
          params: { path: { application_id: application } },
        }),
      ),
  });
  const open = (file: string) =>
    run(async () => {
      const link = await unwrap(
        api().GET(
          "/api/v1/admissions/applications/{application_id}/documents/{file_id}/download/",
          {
            params: { path: { application_id: application, file_id: file } },
          },
        ),
      );
      window.location.assign(link.url); // attachment disposition: the browser downloads it
    });
  return (
    <div className="grid gap-1 ps-2">
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      {files.data?.length ? (
        files.data.map((f) => (
          <div key={f.id} className="flex flex-wrap items-center gap-2 text-xs">
            <span>{f.original_name}</span>
            <span className="text-muted-foreground">
              {t(`documents.states.${f.status}`)}
              {f.scan_state === "unscanned" ? ` · ${t("documents.unscanned")}` : ""}
            </span>
            {f.status === "ready" ? (
              <Button size="sm" variant="ghost" onClick={() => void open(f.id)}>
                {t("documents.download")}
              </Button>
            ) : null}
          </div>
        ))
      ) : (
        <p className="text-muted-foreground text-xs">{t("documents.none")}</p>
      )}
    </div>
  );
}

function TestsPanel({ cycle, rows }: { cycle: Cycle; rows: Application[] | undefined }) {
  const t = useTranslations("admissions");
  const refresh = useAdmissionsRefresh();
  const tests = useQuery({
    queryKey: [...ADMISSIONS_KEY, "cycle-tests", cycle.id],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/admissions/cycles/{cycle_id}/tests/", {
          params: { path: { cycle_id: cycle.id } },
        }),
      ),
  });
  const empty = { name: "", starts_at: "", venue: "", capacity: "", max_score: "" };
  const [form, setForm] = useState(empty);
  const [open, setOpen] = useState<string | null>(null);
  const seatFrom = rows
    ?.filter((a) => SEATABLE.has(a.status))
    .map((a) => ({ id: a.id, label: [a.number, a.applicant_name].filter(Boolean).join(" · ") }));
  const valid =
    form.name.trim() &&
    form.starts_at &&
    Number(form.capacity) >= 1 &&
    /^\d+(\.\d{1,2})?$/.test(form.max_score) &&
    Number(form.max_score) > 0;
  return (
    <div className="grid gap-3">
      <ActionDialog
        trigger={
          <Button size="sm" className="justify-self-start">
            {t("tests.add")}
          </Button>
        }
        title={t("tests.add")}
        submit={t("save")}
        disabled={!valid}
        onSubmit={async () => {
          await unwrap(
            api().POST("/api/v1/admissions/cycles/{cycle_id}/tests/", {
              params: { path: { cycle_id: cycle.id } },
              body: {
                name: form.name.trim(),
                starts_at: new Date(form.starts_at).toISOString(),
                venue: form.venue.trim(),
                capacity: Number(form.capacity),
                max_score: form.max_score,
              },
            }),
          );
          setForm(empty);
          await refresh();
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {(
            [
              ["name", "text"],
              ["starts_at", "datetime-local"],
              ["venue", "text"],
              ["capacity", "number"],
              ["max_score", "text"],
            ] as const
          ).map(([key, type]) => (
            <Field key={key} id={`test-${key}`} label={t(`tests.fields.${key}`)}>
              {(aria) => (
                <Input
                  type={type}
                  inputMode={key === "max_score" ? "decimal" : undefined}
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  {...aria}
                />
              )}
            </Field>
          ))}
        </div>
      </ActionDialog>
      {tests.data?.length ? (
        tests.data.map((test) => (
          <TestCard
            key={test.id}
            test={test}
            open={open === test.id}
            onToggle={() => setOpen(open === test.id ? null : test.id)}
            seatFrom={seatFrom}
          />
        ))
      ) : (
        <p className="text-muted-foreground text-sm">{t("tests.none")}</p>
      )}
    </div>
  );
}

function MeritPanel({ cycle }: { cycle: Cycle }) {
  const t = useTranslations("admissions");
  return (
    <div className="grid gap-3">
      <p className="text-muted-foreground text-sm">
        {cycle.merit_rule_key
          ? t("merit.byRule", { rule: cycle.merit_rule_key })
          : t("merit.byScore")}
      </p>
      {cycle.targets.map((target) => (
        <TargetMerit key={target.id} target={target} />
      ))}
    </div>
  );
}

function TargetMerit({ target }: { target: Schemas["Target"] }) {
  const t = useTranslations("admissions");
  const format = useFormatter();
  const { data: context } = useTenantContext();
  const refresh = useAdmissionsRefresh();
  const { run, failure } = useAction();
  const merit = useQuery({
    queryKey: [...ADMISSIONS_KEY, "merit", target.id],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/admissions/targets/{target_id}/merit/", {
          params: { path: { target_id: target.id } },
        }),
      ),
  });
  const publish = () =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/admissions/targets/{target_id}/merit/publish/", {
          params: { path: { target_id: target.id } },
        }),
      );
      await refresh();
    });
  const offer = () =>
    run(async () => {
      await unwrap(
        api().POST("/api/v1/admissions/targets/{target_id}/merit/offers/", {
          params: { path: { target_id: target.id } },
        }),
      );
      await refresh();
    });
  const published = merit.data?.published;
  const rows = published?.ranking ?? merit.data?.preview ?? [];
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle className="text-base">
            {t("cycles.target", { unit: target.unit_name, seats: target.capacity })}
          </CardTitle>
          <p className="text-muted-foreground text-xs">
            {published
              ? t("merit.published", {
                  version: published.version,
                  at: format.dateTime(new Date(published.published_at), {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }),
                })
              : t("merit.preview")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canAnywhere(context, "admissions.merit.publish") ? (
            <Button size="sm" variant="outline" onClick={() => void publish()}>
              {published ? t("merit.republish") : t("merit.publish")}
            </Button>
          ) : null}
          {published && canAnywhere(context, "admissions.application.decide") ? (
            <Button size="sm" onClick={() => void offer()}>
              {t("merit.offer")}
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="grid gap-2">
        {failure ? <Alert variant="destructive">{failure}</Alert> : null}
        {merit.isError ? <Alert variant="destructive">{t("merit.failed")}</Alert> : null}
        {rows.length ? (
          <ol className="grid gap-1 text-sm" data-testid="merit">
            {rows.map((r) => (
              <li key={r.application} className="flex flex-wrap gap-2">
                <span className="w-8 font-mono text-xs">{r.rank}</span>
                <span className="flex-1">
                  {r.applicant_name}{" "}
                  <span className="text-muted-foreground text-xs">{r.number}</span>
                </span>
                <span className="text-xs">{t("merit.value", { value: r.score })}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-muted-foreground text-sm">{t("merit.empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}
