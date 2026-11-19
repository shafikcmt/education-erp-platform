"use client";

import type { Schemas } from "@erp/api-client";
import { createContext, type ReactNode, useContext } from "react";

export type HostInfo = { kind: "platform" } | { kind: "tenant"; tenant: Schemas["PublicTenant"] };

const HostContext = createContext<HostInfo>({ kind: "platform" });

/** The kind of host this page is served on (decided on the server, plan §13). */
export function HostProvider({ host, children }: { host: HostInfo; children: ReactNode }) {
  return <HostContext.Provider value={host}>{children}</HostContext.Provider>;
}

export function useHost(): HostInfo {
  return useContext(HostContext);
}
