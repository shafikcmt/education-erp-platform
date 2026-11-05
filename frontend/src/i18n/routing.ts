import { defineRouting } from "next-intl/routing";

/** ADR-021: English + Bengali at launch. Add "ar" here (RTL handled by `getDirection`). */
export const routing = defineRouting({
  locales: ["en", "bn"],
  defaultLocale: "en",
  localePrefix: "always",
});

export type Locale = (typeof routing.locales)[number];
