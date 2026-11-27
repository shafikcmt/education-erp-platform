"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

export const STUDENTS_KEY = ["students"] as const;

export function useStudentsRefresh() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: STUDENTS_KEY });
}

/** Open academic years and the units a student can sit in (no units below them). */
export function useEnrollmentChoices(institution: string | undefined) {
  const years = useQuery({
    queryKey: ["academics", "years", institution],
    enabled: Boolean(institution),
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/academics/years/", { params: { query: { institution: institution! } } }),
      ),
  });
  const units = useQuery({
    queryKey: ["academics", "units", institution],
    enabled: Boolean(institution),
    queryFn: () =>
      unwrap(
        api().GET("/api/v1/academics/units/", { params: { query: { institution: institution! } } }),
      ),
  });
  const parents = new Set((units.data ?? []).map((u) => u.parent).filter(Boolean));
  return {
    years: (years.data ?? []).filter((y) => y.status !== "closed"),
    leafUnits: (units.data ?? []).filter((u) => !parents.has(u.id)),
  };
}

/** The localised name of a server status; an unknown one is shown as it is. */
export function useStudentStatus() {
  const t = useTranslations("students.statuses");
  return (status: string) => {
    const key = status as "active";
    return t.has(key) ? t(key) : status;
  };
}

/** Printable HTML from a Studio template, shown in a sandboxed frame (no scripts, no forms). */
export function PrintPreview({ html, title }: { html: string; title: string }) {
  return (
    <iframe
      title={title}
      sandbox=""
      srcDoc={html}
      className="h-96 w-full rounded-md border bg-white"
      data-testid="print-preview"
    />
  );
}
