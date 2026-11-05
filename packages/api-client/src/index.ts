/**
 * Generated API contract (ADR-015). Regenerate with `pnpm api:generate` after changing the
 * backend schema; CI fails if the committed output drifts from the backend.
 */
export type { components, operations, paths } from "./schema";

export type Schemas = import("./schema").components["schemas"];
