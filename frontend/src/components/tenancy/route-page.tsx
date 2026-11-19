import { setRequestLocale } from "next-intl/server";
import type { ComponentType } from "react";

/** Server page wrapper: sets the request locale and renders a client screen (with the route
 * `id` when there is one). */
export function routePage(Screen: ComponentType<{ id?: string }>) {
  return async function Page({ params }: { params: Promise<{ locale: string; id?: string }> }) {
    const { locale, id } = await params;
    setRequestLocale(locale);
    return <Screen id={id} />;
  };
}
