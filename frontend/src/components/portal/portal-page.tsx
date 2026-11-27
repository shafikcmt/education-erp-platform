"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { useStudentStatus } from "@/components/students/shared";
import { WeekGrid } from "@/components/timetable/timetable-page";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

/** The guardian and student portal (Phase 7 M9): a switcher over my children (or myself), then
 * the chosen child's enrollment and week. Read-only; the server shows only my children. */
export function PortalPage() {
  const t = useTranslations("portal");
  const status = useStudentStatus();
  const children = useQuery({
    queryKey: ["portal", "children"],
    queryFn: () => unwrap(api().GET("/api/v1/portal/children/")),
  });
  const [chosen, setChosen] = useState("");
  const current = chosen || children.data?.[0]?.id || "";
  const detail = useQuery({
    queryKey: ["portal", "child", current],
    enabled: Boolean(current),
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/portal/children/{student_id}/", {
          params: { path: { student_id: current } },
        }),
      ),
  });
  const child = detail.data;
  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      {children.data && !children.data.length ? (
        <p className="text-muted-foreground text-sm">{t("none")}</p>
      ) : null}
      {children.data && children.data.length > 1 ? (
        <div role="tablist" aria-label={t("switcher")} className="mb-4 flex gap-2 overflow-x-auto">
          {children.data.map((c) => (
            <button
              key={c.id}
              role="tab"
              type="button"
              aria-selected={c.id === current}
              onClick={() => setChosen(c.id)}
              className={cn(
                "shrink-0 rounded-full border px-4 py-2 text-sm",
                c.id === current ? "bg-primary text-primary-foreground" : "hover:bg-accent",
              )}
            >
              {c.name}
            </button>
          ))}
        </div>
      ) : null}
      {child ? (
        <div className="grid gap-4">
          <Card>
            <CardHeader>
              <CardTitle>{child.name}</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm" data-testid="child">
                <dt className="text-muted-foreground">{t("number")}</dt>
                <dd>{child.number}</dd>
                <dt className="text-muted-foreground">{t("status")}</dt>
                <dd>{status(child.status)}</dd>
                <dt className="text-muted-foreground">{t("class")}</dt>
                <dd>
                  {child.current
                    ? `${child.current.unit_name} · ${child.current.year_name}${
                        child.current.roll_number
                          ? ` · ${t("roll")} ${child.current.roll_number}`
                          : ""
                      }`
                    : "—"}
                </dd>
              </dl>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t("timetable")}</CardTitle>
            </CardHeader>
            <CardContent>
              <WeekGrid lessons={child.timetable} />
            </CardContent>
          </Card>
          <p className="text-muted-foreground text-xs">{t("comingSoon")}</p>
        </div>
      ) : null}
    </>
  );
}
