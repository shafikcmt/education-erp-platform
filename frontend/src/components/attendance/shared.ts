/** Pure helpers of the attendance screens (Phase 8 M8), kept apart so they are unit-tested. */

export const STATUSES = ["present", "absent", "late", "excused", "leave"] as const;
export type Status = (typeof STATUSES)[number];

/** One tap on the quick-mark screen: present → absent → late → present. Excused and leave are
 * chosen from the row's menu, and a tap on them starts the cycle again. */
export function nextStatus(current: Status): Status {
  if (current === "present") return "absent";
  if (current === "absent") return "late";
  return "present";
}

export function countByStatus(statuses: Iterable<Status>): Record<Status, number> {
  const out: Record<Status, number> = { present: 0, absent: 0, late: 0, excused: 0, leave: 0 };
  for (const s of statuses) out[s] += 1;
  return out;
}

/** Only the rows whose status differs from what the server last returned (one save request). */
export function changedEntries(
  initial: Record<string, Status>,
  current: Record<string, Status>,
  unsaved: Set<string>,
): { student: string; status: Status }[] {
  return Object.entries(current)
    .filter(([id, status]) => unsaved.has(id) || initial[id] !== status)
    .map(([student, status]) => ({ student, status }));
}

export function todayIso(now: Date = new Date()): string {
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

export function monthIso(now: Date = new Date()): string {
  return todayIso(now).slice(0, 7);
}
