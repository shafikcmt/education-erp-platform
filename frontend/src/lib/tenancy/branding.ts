/** Tenant colours as CSS variables (plan §13.1). Only `#rrggbb` values are used, so branding
 * data can never inject CSS. */
const HEX = /^#[0-9a-fA-F]{6}$/;

export function brandStyle(
  branding: Record<string, unknown> | null | undefined,
): Record<string, string> {
  const primary = branding?.primary_color;
  if (typeof primary !== "string" || !HEX.test(primary)) return {};
  return { "--primary": primary, "--ring": primary };
}
