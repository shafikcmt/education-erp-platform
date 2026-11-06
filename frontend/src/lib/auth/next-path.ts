/** Only same-site relative paths are accepted as post-login destinations (open-redirect guard). */
export function safeNextPath(value: string | null | undefined, fallback = "/dashboard"): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return fallback;
  }
  // Locale prefix is added by the localized router; strip it if present.
  return value.replace(/^\/(en|bn)(?=\/|$)/, "") || fallback;
}
