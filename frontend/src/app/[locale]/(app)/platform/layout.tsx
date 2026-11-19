import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { getServerHost } from "@/lib/api/server";

/** Platform screens exist only on the platform host (plan §12.2). */
export default async function PlatformOnlyLayout({ children }: { children: ReactNode }) {
  const host = await getServerHost();
  if (host.kind === "tenant") notFound();
  return children;
}
