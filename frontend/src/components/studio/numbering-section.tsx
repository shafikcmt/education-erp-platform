"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ActionDialog, SELECT_CLASS } from "@/components/tenancy/simple-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

import { STUDIO_KEY, useStudioRefresh } from "./shared";

export function NumberingSection() {
  const t = useTranslations("studio");
  const refresh = useStudioRefresh();
  const query = useQuery({
    queryKey: [...STUDIO_KEY, "numbering"],
    queryFn: () => unwrap(api().GET("/api/v1/customization/numbering/")),
  });
  const empty = {
    key: "",
    name: "",
    pattern: "RCP-{YYYY}-{SEQ:5}",
    scope: "tenant",
    reset: "yearly",
  };
  const [form, setForm] = useState(empty);
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("sections.numbering")}</CardTitle>
        <ActionDialog
          trigger={<Button size="sm">{t("numbering.add")}</Button>}
          title={t("numbering.add")}
          description={t("numbering.tokens")}
          submit={t("numbering.add")}
          disabled={!/^[a-z][a-z0-9_]{1,63}$/.test(form.key) || !form.name.trim()}
          onSubmit={async () => {
            await unwrap(api().POST("/api/v1/customization/numbering/", { body: form }));
            setForm(empty);
            await refresh();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="seq-key" label={t("key")} hint={t("keyHint")}>
              {(aria) => (
                <Input
                  value={form.key}
                  onChange={(e) => setForm({ ...form, key: e.target.value.trim() })}
                  {...aria}
                />
              )}
            </Field>
            <Field id="seq-name" label={t("name")}>
              {(aria) => (
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  {...aria}
                />
              )}
            </Field>
            <Field id="seq-pattern" label={t("numbering.pattern")}>
              {(aria) => (
                <Input
                  value={form.pattern}
                  onChange={(e) => setForm({ ...form, pattern: e.target.value.trim() })}
                  {...aria}
                />
              )}
            </Field>
            <Field id="seq-scope" label={t("scope")}>
              {(aria) => (
                <select
                  className={SELECT_CLASS}
                  value={form.scope}
                  onChange={(e) => setForm({ ...form, scope: e.target.value })}
                  {...aria}
                >
                  {(["tenant", "institution", "campus"] as const).map((s) => (
                    <option key={s} value={s}>
                      {t(`numbering.scopes.${s}`)}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field id="seq-reset" label={t("numbering.reset")}>
              {(aria) => (
                <select
                  className={SELECT_CLASS}
                  value={form.reset}
                  onChange={(e) => setForm({ ...form, reset: e.target.value })}
                  {...aria}
                >
                  {(["never", "yearly", "academic_year"] as const).map((r) => (
                    <option key={r} value={r}>
                      {t(`numbering.resets.${r}`)}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
        </ActionDialog>
      </CardHeader>
      <CardContent>
        {query.data?.length ? (
          <ul className="grid gap-2 text-sm" data-testid="numbering-list">
            {query.data.map((s) => (
              <li key={s.id}>
                {s.name} <code className="text-muted-foreground text-xs">{s.pattern}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{t("empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}
