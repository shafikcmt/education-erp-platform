import type { TenantContext } from "@/lib/tenancy/context";

/** Whether the organisation's plan includes a module (from `/me/context/`). Navigation only:
 * the API refuses every request of a module the organisation lacks (`module_not_entitled`). */
export function isEntitled(context: TenantContext | undefined, module: string): boolean {
  return Boolean(context?.entitlements?.modules.includes(module));
}

/** Share of a limit in use, clamped to 0-100 (for progress bars). */
export function usagePercent(usage: { limit: number; used: number }): number {
  if (usage.limit <= 0) return 100;
  return Math.min(100, Math.max(0, Math.round((usage.used / usage.limit) * 100)));
}
