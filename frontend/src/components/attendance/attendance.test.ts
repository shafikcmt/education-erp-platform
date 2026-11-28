import { describe, expect, it } from "vitest";

import { changedEntries, countByStatus, monthIso, nextStatus, todayIso } from "./shared";

describe("attendance quick-mark helpers", () => {
  it("cycles present → absent → late → present, and restarts from excused or leave", () => {
    expect(nextStatus("present")).toBe("absent");
    expect(nextStatus("absent")).toBe("late");
    expect(nextStatus("late")).toBe("present");
    expect(nextStatus("excused")).toBe("present");
    expect(nextStatus("leave")).toBe("present");
  });

  it("counts statuses", () => {
    expect(countByStatus(["present", "absent", "present", "leave"])).toEqual({
      present: 2,
      absent: 1,
      late: 0,
      excused: 0,
      leave: 1,
    });
  });

  it("sends changed rows and rows never saved, nothing else", () => {
    const initial = { a: "present", b: "absent", c: "present" } as const;
    const current = { a: "present", b: "present", c: "present" } as const;
    expect(changedEntries(initial, current, new Set(["c"]))).toEqual([
      { student: "b", status: "present" },
      { student: "c", status: "present" },
    ]);
  });

  it("formats local dates", () => {
    const day = new Date(2027, 2, 9, 23, 30);
    expect(todayIso(day)).toBe("2027-03-09");
    expect(monthIso(day)).toBe("2027-03");
  });
});
