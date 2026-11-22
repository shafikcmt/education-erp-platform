"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useAction } from "@/components/tenancy/simple-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

import { DynamicForm } from "./dynamic-form";
import {
  type Artefact,
  JsonEditor,
  latestByKey,
  parseJson,
  QuotaBadge,
  STUDIO_KEY,
  useStudioRefresh,
} from "./shared";

export type ArtefactKind = "rules" | "forms" | "workflows" | "templates";

/** Starter bodies: valid examples the editor opens with (edited as JSON in Studio v1). */
const STARTERS: Record<ArtefactKind, Record<string, unknown>> = {
  rules: {
    namespace: "customization.form_visibility",
    rule: { ">=": [{ var: "field.age" }, 18] },
    test_cases: [{ context: { "field.age": 20 }, expected: true }],
  },
  forms: {
    entity: "tenancy.institution",
    layout: {
      sections: [
        {
          key: "basic",
          labels: { en: "Basic" },
          fields: [{ source: "core", name: "name", required: true }],
        },
      ],
    },
  },
  workflows: {
    subject: "tenancy.member",
    spec: {
      states: [
        { key: "submitted", labels: { en: "Submitted" } },
        { key: "approved", labels: { en: "Approved" }, final: true },
      ],
      initial: "submitted",
      start_permission: "tenancy.member.view",
      transitions: [
        {
          key: "approve",
          from: ["submitted"],
          to: "approved",
          labels: { en: "Approve" },
          permission: "tenancy.member.update",
        },
      ],
      sla_hours: { submitted: 48 },
    },
  },
  templates: {
    kind: "customization.sms",
    content: { en: { body: "Dear {{ recipient }}, welcome to {{ organisation }}." } },
  },
};

const PATHS = {
  rules: "/api/v1/customization/rules/",
  forms: "/api/v1/customization/forms/",
  workflows: "/api/v1/customization/workflows/",
  templates: "/api/v1/customization/templates/",
} as const;

type Client = ReturnType<typeof api>;
// The list, draft and publish endpoints share one shape across the four kinds.
const list = (kind: ArtefactKind) =>
  unwrap((api() as Client).GET(PATHS[kind] as "/api/v1/customization/rules/")) as Promise<{
    items: Artefact[];
    quota: { used: number; limit: number };
  }>;

function publishPath(kind: ArtefactKind) {
  return `/api/v1/customization/${kind}/{key}/publish/` as "/api/v1/customization/rules/{key}/publish/";
}

export function ArtefactSection({ kind }: { kind: ArtefactKind }) {
  const t = useTranslations("studio");
  const refresh = useStudioRefresh();
  const { run, failure } = useAction();
  const query = useQuery({ queryKey: [...STUDIO_KEY, kind], queryFn: () => list(kind) });
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [body, setBody] = useState(() => JSON.stringify(STARTERS[kind], null, 2));
  const [output, setOutput] = useState<string | null>(null);
  const [previewForm, setPreviewForm] = useState<string | null>(null);
  const edit = (item: Artefact) => {
    setKey(item.key);
    setName(item.name);
    setBody(JSON.stringify(item.body, null, 2));
    setOutput(null);
  };
  const save = () =>
    run(async () => {
      const parsed = parseJson(body) as Record<string, unknown>;
      await unwrap(
        api().POST(PATHS[kind] as "/api/v1/customization/rules/", {
          body: { key, name, ...parsed } as never,
        }),
      );
      await refresh();
    });
  const publish = (k: string) =>
    run(async () => {
      await unwrap(api().POST(publishPath(kind), { params: { path: { key: k } } }));
      await refresh();
    });
  const test = () =>
    run(async () => {
      const parsed = parseJson(body) as { namespace: string; rule: unknown; test_cases: unknown[] };
      const result = await unwrap(
        api().POST("/api/v1/customization/rules/test/", {
          body: {
            namespace: parsed.namespace,
            rule: parsed.rule as never,
            test_cases: parsed.test_cases ?? [],
          },
        }),
      );
      setOutput(JSON.stringify(result.results, null, 2));
    });
  const preview = () =>
    run(async () => {
      const parsed = parseJson(body) as { kind: string; content: Record<string, unknown> };
      const locale = Object.keys(parsed.content ?? {})[0] ?? "en";
      const result = await unwrap(
        api().POST("/api/v1/customization/templates/preview/", {
          body: { kind: parsed.kind, content: parsed.content, locale },
        }),
      );
      setOutput([result.subject, result.body].filter(Boolean).join("\n\n"));
    });
  const items = latestByKey(query.data?.items ?? []);
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle>{t(`sections.${kind}` as "sections.rules")}</CardTitle>
          <QuotaBadge quota={query.data?.quota} />
        </CardHeader>
        <CardContent>
          {items.length ? (
            <ul className="grid gap-2 text-sm" data-testid={`${kind}-list`}>
              {items.map((item) => (
                <li key={item.key} className="flex flex-wrap items-center justify-between gap-2">
                  <button
                    type="button"
                    className="text-left underline-offset-2 hover:underline"
                    onClick={() => edit(item)}
                  >
                    {item.name} <code className="text-muted-foreground text-xs">{item.key}</code>
                    <span className="text-muted-foreground block text-xs">
                      {item.status === "draft"
                        ? t("draftVersion", { number: item.number })
                        : t("version", { number: item.number })}
                      {item.publishedNumber
                        ? ` · ${t("publishedVersion", { number: item.publishedNumber })}`
                        : ""}
                    </span>
                  </button>
                  <span className="flex gap-1">
                    {item.status === "draft" ? (
                      <Button size="sm" variant="outline" onClick={() => void publish(item.key)}>
                        {t("publish")}
                      </Button>
                    ) : null}
                    {kind === "forms" && item.publishedNumber ? (
                      <Button size="sm" variant="ghost" onClick={() => setPreviewForm(item.key)}>
                        {t("tryForm")}
                      </Button>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">{t("empty")}</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("editor")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          {failure ? <Alert variant="destructive">{failure}</Alert> : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id={`${kind}-key`} label={t("key")} hint={t("keyHint")}>
              {(aria) => (
                <Input value={key} onChange={(e) => setKey(e.target.value.trim())} {...aria} />
              )}
            </Field>
            <Field id={`${kind}-name`} label={t("name")}>
              {(aria) => <Input value={name} onChange={(e) => setName(e.target.value)} {...aria} />}
            </Field>
          </div>
          <JsonEditor
            id={`${kind}-body`}
            label={t("definition")}
            hint={t(`hints.${kind}` as "hints.rules")}
            value={body}
            onChange={setBody}
            rows={14}
          />
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void save()} disabled={!key || !name}>
              {t("saveDraft")}
            </Button>
            {kind === "rules" ? (
              <Button variant="outline" onClick={() => void test()}>
                {t("test")}
              </Button>
            ) : null}
            {kind === "templates" ? (
              <Button variant="outline" onClick={() => void preview()}>
                {t("preview")}
              </Button>
            ) : null}
          </div>
          {output !== null ? (
            <pre
              className="bg-muted max-h-64 overflow-auto rounded-md p-3 text-xs whitespace-pre-wrap"
              data-testid="output"
            >
              {output}
            </pre>
          ) : null}
        </CardContent>
      </Card>
      {previewForm ? (
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("formPreview", { key: previewForm })}</CardTitle>
          </CardHeader>
          <CardContent>
            <DynamicForm formKey={previewForm} />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
