export type Step = { key: string; href: string; done: boolean };

/** Steps of the first-day setup, computed from server state (plan §13.7: the onboarding wizard is
 * this checklist, not a separate flow). */
export function onboardingSteps(state: {
  institutions: number;
  members: number;
  settingsPublished: boolean;
  customFields: number;
}): Step[] {
  return [
    { key: "institution", href: "/institutions", done: state.institutions > 0 },
    { key: "settings", href: "/studio", done: state.settingsPublished },
    { key: "fields", href: "/studio", done: state.customFields > 0 },
    { key: "members", href: "/members", done: state.members > 1 },
  ];
}
