"use client";

import { useQuery } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { ActionDialog, SELECT_CLASS, useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { canAnywhere, useTenantContext } from "@/lib/tenancy/context";

import { ADMISSIONS_KEY, useAdmissionsRefresh } from "./shared";

type TestRow = {
  id: string;
  name: string;
  starts_at: string;
  venue: string;
  capacity: number;
  max_score: string;
  seated: number;
};

/** Tests of an institution and their seat lists (exam controllers score here). */
export function TestsSection({ institution }: { institution: string }) {
  const t = useTranslations("admissions");
  const tests = useQuery({
    queryKey: [...ADMISSIONS_KEY, "tests", institution],
    queryFn: () =>
      unwrap(api().GET("/api/v1/admissions/tests/", { params: { query: { institution } } })),
  });
  const [open, setOpen] = useState<string | null>(null);
  if (tests.isError) return <Alert variant="destructive">{t("noAccess")}</Alert>;
  return (
    <div className="grid gap-3">
      {tests.data?.length ? (
        tests.data.map((test) => (
          <TestCard
            key={test.id}
            test={test}
            open={open === test.id}
            onToggle={() => setOpen(open === test.id ? null : test.id)}
          />
        ))
      ) : (
        <p className="text-muted-foreground text-sm">{t("tests.none")}</p>
      )}
    </div>
  );
}

export function TestCard({
  test,
  open,
  onToggle,
  seatFrom,
}: {
  test: TestRow;
  open: boolean;
  onToggle: () => void;
  /** Applications that may be seated (only for members who can see applications). */
  seatFrom?: { id: string; label: string }[];
}) {
  const t = useTranslations("admissions");
  const format = useFormatter();
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle className="text-base">{test.name}</CardTitle>
          <p className="text-muted-foreground text-xs">
            {format.dateTime(new Date(test.starts_at), { dateStyle: "medium", timeStyle: "short" })}
            {test.venue ? ` · ${test.venue}` : ""} ·{" "}
            {t("tests.seated", { seated: test.seated, capacity: test.capacity })} ·{" "}
            {t("tests.maxScore", { max: test.max_score })}
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={onToggle} aria-expanded={open}>
          {open ? t("hide") : t("tests.seatList")}
        </Button>
      </CardHeader>
      {open ? (
        <CardContent>
          <SeatList test={test} seatFrom={seatFrom} />
        </CardContent>
      ) : null}
    </Card>
  );
}

function SeatList({
  test,
  seatFrom,
}: {
  test: TestRow;
  seatFrom?: { id: string; label: string }[];
}) {
  const t = useTranslations("admissions");
  const refresh = useAdmissionsRefresh();
  const { run, failure } = useAction();
  const { data: context } = useTenantContext();
  // Entering scores is its own permission (ADR-067); the API checks it in the test's scope.
  const canScore = canAnywhere(context, "admissions.test.score");
  const seats = useQuery({
    queryKey: [...ADMISSIONS_KEY, "seats", test.id],
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/admissions/tests/{test_id}/assignments/", {
          params: { path: { test_id: test.id } },
        }),
      ),
  });
  const [scores, setScores] = useState<Record<string, string>>({});
  const [chosen, setChosen] = useState("");
  const seated = new Set((seats.data ?? []).map((s) => s.application));
  const candidates = (seatFrom ?? []).filter((a) => !seated.has(a.id));
  const save = (id: string, body: { score: string | null; absent: boolean }) =>
    run(async () => {
      await unwrap(
        api().PATCH("/api/v1/admissions/assignments/{assignment_id}/", {
          params: { path: { assignment_id: id } },
          body,
        }),
      );
      setScores((current) => ({ ...current, [id]: "" }));
      await refresh();
    });
  return (
    <div className="grid gap-3">
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      {seatFrom ? (
        <ActionDialog
          trigger={
            <Button size="sm" className="justify-self-start" disabled={!candidates.length}>
              {t("tests.seat")}
            </Button>
          }
          title={t("tests.seat")}
          submit={t("tests.seat")}
          disabled={!chosen}
          onSubmit={async () => {
            await unwrap(
              api().POST("/api/v1/admissions/tests/{test_id}/assignments/", {
                params: { path: { test_id: test.id } },
                body: { application: chosen },
              }),
            );
            setChosen("");
            await refresh();
          }}
        >
          <Field id="seat-application" label={t("applications.one")}>
            {(aria) => (
              <select
                className={SELECT_CLASS}
                value={chosen}
                onChange={(e) => setChosen(e.target.value)}
                {...aria}
              >
                <option value="" />
                {candidates.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </ActionDialog>
      ) : null}
      {seats.data?.length ? (
        <ul className="grid gap-2 text-sm" data-testid="seat-list">
          {seats.data.map((seat) => (
            <li key={seat.id} className="flex flex-wrap items-center gap-2">
              <span className="w-10 font-mono text-xs">#{seat.seat}</span>
              <span className="min-w-32 flex-1">
                {seat.applicant_name}{" "}
                <span className="text-muted-foreground text-xs">{seat.application_number}</span>
              </span>
              <span className="text-xs">
                {seat.absent
                  ? t("tests.absent")
                  : seat.score !== null
                    ? t("tests.score", { score: seat.score })
                    : t("tests.noScore")}
              </span>
              {canScore ? (
                <>
                  <Input
                    className="h-8 w-24"
                    inputMode="decimal"
                    aria-label={t("tests.enterScore", { seat: seat.seat })}
                    value={scores[seat.id] ?? ""}
                    onChange={(e) => setScores({ ...scores, [seat.id]: e.target.value.trim() })}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!/^\d+(\.\d{1,2})?$/.test(scores[seat.id] ?? "")}
                    onClick={() =>
                      void save(seat.id, { score: scores[seat.id] ?? "", absent: false })
                    }
                  >
                    {t("save")}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void save(seat.id, { score: null, absent: true })}
                  >
                    {t("tests.markAbsent")}
                  </Button>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-sm">{t("tests.noSeats")}</p>
      )}
    </div>
  );
}
