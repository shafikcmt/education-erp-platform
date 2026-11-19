import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { getServerHost } from "@/lib/api/server";

/** Organisation screens exist only on a tenant host (the API serves their routes nowhere
 * else either; plan §12.1). */
export default async function TenantOnlyLayout({ children }: { children: ReactNode }) {
  const host = await getServerHost();
  if (host.kind !== "tenant") notFound();
  return children;
}
