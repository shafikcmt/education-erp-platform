import { z } from "zod";

import type en from "@/messages/en.json";

type ValidationKey = `validation.${keyof (typeof en)["validation"]}`;
type T = (key: ValidationKey, values?: Record<string, number>) => string;

export const PASSWORD_MIN = 10;
export const PASSWORD_MAX = 128;

/** Client-side checks mirror the server's Django validators; the server stays authoritative. */
export function newPasswordSchema(t: T) {
  return z
    .object({
      password: z
        .string()
        .min(PASSWORD_MIN, { error: t("validation.passwordMin", { min: PASSWORD_MIN }) })
        .max(PASSWORD_MAX, { error: t("validation.passwordMax", { max: PASSWORD_MAX }) })
        .refine((v) => !/^\d+$/.test(v), { error: t("validation.passwordNumeric") }),
      confirm: z.string(),
    })
    .refine((v) => v.password === v.confirm, {
      error: t("validation.passwordsMatch"),
      path: ["confirm"],
    });
}

export function emailSchema(t: T) {
  return z
    .string()
    .trim()
    .min(1, { error: t("validation.required") })
    .max(254)
    .pipe(z.email({ error: t("validation.email") }));
}

export function otpSchema(t: T) {
  return z
    .string()
    .trim()
    .regex(/^\d{6}$/, { error: t("validation.codeFormat") });
}
