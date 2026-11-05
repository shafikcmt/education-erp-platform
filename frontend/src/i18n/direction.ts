const RTL_LANGUAGES = new Set(["ar", "fa", "he", "ur"]);

/** Text direction for a locale; layouts use logical CSS (ms-/me-/start/end) so RTL just works. */
export function getDirection(locale: string): "ltr" | "rtl" {
  const language = locale.split("-")[0]?.toLowerCase() ?? "";
  return RTL_LANGUAGES.has(language) ? "rtl" : "ltr";
}
