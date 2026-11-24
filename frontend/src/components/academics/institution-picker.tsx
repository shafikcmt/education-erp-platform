"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { SELECT_CLASS } from "@/components/tenancy/simple-form";
import { Field } from "@/components/ui/field";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { localName } from "@/lib/tenancy/context";

/** The institutions I can see, and the one chosen (the first by default). The API answers 404
 * for an institution outside my scope, whatever the browser sends. */
export function useInstitutionChoice(): {
  institution: string;
  picker: React.ReactNode;
} {
  const t = useTranslations("academics");
  const locale = useLocale();
  const list = useQuery({
    queryKey: ["tenant", "institutions"],
    queryFn: () => unwrap(api().GET("/api/v1/institutions/")),
  });
  const [chosen, setChosen] = useState("");
  const institution = chosen || list.data?.[0]?.id || "";
  const picker = (
    <Field id="institution-choice" label={t("institution")}>
      {(aria) => (
        <select
          className={SELECT_CLASS}
          value={institution}
          onChange={(e) => setChosen(e.target.value)}
          {...aria}
        >
          {(list.data ?? []).map((i) => (
            <option key={i.id} value={i.id}>
              {localName(i, locale)}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
  return { institution, picker };
}
