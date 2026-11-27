"use client";

import type { Schemas } from "@erp/api-client";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import {
  DynamicForm,
  type FormSource,
  type RenderedSection,
} from "@/components/studio/dynamic-form";
import { SELECT_CLASS } from "@/components/tenancy/simple-form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

/** Staff enter an application on an applicant's behalf (Phase 7 M9; the Phase 6 gap): the
 * cycle's Studio form rendered for staff, validated and submitted by the server
 * (``admissions.application.review`` in the cycle's institution). */
export function StaffEntry({ cycle, onDone }: { cycle: Schemas["Cycle"]; onDone: () => void }) {
  const t = useTranslations("admissions");
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState("");
  const chosen = target || cycle.targets[0]?.id || "";
  const source = useMemo<FormSource>(
    () => ({
      cacheKey: ["admissions", "staff-form", cycle.id],
      render: () =>
        unwrap(
          api().GET("/api/v1/admissions/cycles/{cycle_id}/form/", {
            params: { path: { cycle_id: cycle.id } },
          }),
        ) as Promise<{ sections: RenderedSection[] }>,
      visibility: async (values) => {
        const result = (await unwrap(
          api().POST("/api/v1/admissions/cycles/{cycle_id}/visibility/", {
            params: { path: { cycle_id: cycle.id } },
            body: { values },
          }),
        )) as { sections?: string[] };
        return result.sections ?? [];
      },
      submit: async (values) => {
        await unwrap(
          api().POST("/api/v1/admissions/applications/", {
            body: { cycle: cycle.id, target: chosen, values },
          }),
        );
        setOpen(false);
        onDone();
      },
      submitLabel: t("entry.submit"),
    }),
    [cycle.id, chosen, onDone, t],
  );
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">{t("entry.open")}</Button>
      </DialogTrigger>
      <DialogContent closeLabel={t("entry.close")}>
        <DialogTitle>{t("entry.open")}</DialogTitle>
        <DialogDescription>{t("entry.hint")}</DialogDescription>
        <Field id="entry-target" label={t("entry.target")}>
          {(aria) => (
            <select
              className={SELECT_CLASS}
              value={chosen}
              onChange={(e) => setTarget(e.target.value)}
              {...aria}
            >
              {cycle.targets.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.unit_name}
                </option>
              ))}
            </select>
          )}
        </Field>
        {open ? <DynamicForm formKey={cycle.id} source={source} /> : null}
      </DialogContent>
    </Dialog>
  );
}
