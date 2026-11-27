"use client";

import type { Schemas } from "@erp/api-client";
import { useFormatter, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { api, ensureCsrf } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { postToSlot } from "@/lib/files/upload";
import { useErrorMessage } from "@/lib/auth/use-error-message";
import { useFragmentToken } from "@/lib/auth/fragment-token";

type Status = Schemas["PublicStatus"];
const ACCEPT = "application/pdf,image/jpeg,image/png";
const MAX_BYTES = 5 * 1024 * 1024;

/**
 * The applicant's own page (status link). The token lives only in memory for this visit (never
 * in storage or the URL); every call sends it in the request body.
 */
export function ApplyStatus() {
  const t = useTranslations();
  const format = useFormatter();
  const errorMessage = useErrorMessage();
  const { token, ready, version } = useFragmentToken();
  const [status, setStatus] = useState<Status | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      await ensureCsrf();
      setStatus(await unwrap(api().POST("/api/v1/public/admissions/status/", { body: { token } })));
      setState("ready");
    } catch {
      setState("failed");
    }
  }, [token]);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one load per opened link
    if (ready) void load();
  }, [ready, load, version]);

  if (!ready) return null;
  if (!token || state === "failed") {
    return <Alert variant="destructive">{t("errors.invalid_token")}</Alert>;
  }
  if (!status) return <p className="text-muted-foreground text-sm">{t("apply.loading")}</p>;

  const act = async (action: () => Promise<Status>) => {
    setFailure(null);
    setBusy(true);
    try {
      await ensureCsrf();
      setStatus(await action());
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };
  const respond = (accept: boolean) =>
    act(() =>
      unwrap(api().POST("/api/v1/public/admissions/status/respond/", { body: { token, accept } })),
    );
  const upload = (file: File) =>
    act(async () => {
      if (file.size > MAX_BYTES) throw new Error(t("apply.tooLarge"));
      const slot = await unwrap(
        api().POST("/api/v1/public/admissions/status/documents/", {
          body: { token, name: file.name, size: file.size, content_type: file.type },
        }),
      );
      try {
        await postToSlot(slot, file);
      } catch {
        throw new Error(t("apply.uploadFailed"));
      }
      return unwrap(
        api().POST("/api/v1/public/admissions/status/documents/confirm/", {
          body: { token, file: slot.id },
        }),
      );
    });

  return (
    <div className="grid gap-4" data-testid="application-status">
      {failure ? <Alert variant="destructive">{failure}</Alert> : null}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">{t("apply.applicant")}</dt>
        <dd>{status.applicant_name}</dd>
        <dt className="text-muted-foreground">{t("apply.number")}</dt>
        <dd>{status.number || "—"}</dd>
        <dt className="text-muted-foreground">{t("apply.cycle")}</dt>
        <dd>{status.cycle}</dd>
        <dt className="text-muted-foreground">{t("apply.status")}</dt>
        <dd className="font-medium" data-testid="status">
          {t.has(`admissions.statuses.${status.status}` as "admissions.statuses.submitted")
            ? t(`admissions.statuses.${status.status}` as "admissions.statuses.submitted")
            : status.status}
        </dd>
      </dl>
      {status.decision_note ? <Alert>{status.decision_note}</Alert> : null}
      {status.status === "offered" ? (
        <div className="grid gap-2">
          <p className="text-sm">{t("apply.offerIntro")}</p>
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => void respond(true)}>
              {t("apply.accept")}
            </Button>
            <Button variant="outline" disabled={busy} onClick={() => void respond(false)}>
              {t("apply.decline")}
            </Button>
          </div>
        </div>
      ) : null}
      {status.tests.length ? (
        <section className="grid gap-1">
          <h2 className="text-sm font-medium">{t("apply.tests")}</h2>
          <ul className="grid gap-1 text-sm">
            {status.tests.map((test, index) => (
              <li key={index}>
                {test.name} ·{" "}
                {format.dateTime(new Date(test.starts_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
                {test.venue ? ` · ${test.venue}` : ""} · {t("apply.seat", { seat: test.seat })}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section className="grid gap-2">
        <h2 className="text-sm font-medium">{t("apply.documents")}</h2>
        {status.documents.length ? (
          <ul className="grid gap-1 text-sm">
            {status.documents.map((d) => (
              <li key={d.id}>
                {d.name}{" "}
                <span className="text-muted-foreground text-xs">
                  {t(
                    `admissions.documents.states.${d.status}` as "admissions.documents.states.ready",
                  )}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{t("admissions.documents.none")}</p>
        )}
        {status.can_add_documents ? (
          <Field id="document-file" label={t("apply.addDocument")} hint={t("apply.documentHint")}>
            {(aria) => (
              <input
                type="file"
                accept={ACCEPT}
                disabled={busy}
                className="text-sm"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (file) void upload(file);
                }}
                {...aria}
              />
            )}
          </Field>
        ) : null}
      </section>
    </div>
  );
}
