import { describe, expect, it } from "vitest";

import { weekLayout } from "@/components/timetable/timetable-page";

import { csvHeader } from "./import-page";

describe("import mapping", () => {
  it("reads the CSV header (BOM, quotes, CRLF) to suggest the mapping", async () => {
    const file = new File(['﻿Name,"Guardian phone",Class\r\nAna,017,6A\r\n'], "s.csv", {
      type: "text/csv",
    });
    expect(await csvHeader(file)).toEqual(["Name", "Guardian phone", "Class"]);
  });
});

describe("week grid", () => {
  it("shows only days with lessons, Monday first, and sorted start times", () => {
    const lessons = [
      { weekday: 3, start_time: "09:00:00" },
      { weekday: 1, start_time: "08:00:00" },
      { weekday: 3, start_time: "08:00:00" },
    ];
    expect(weekLayout(lessons)).toEqual({ days: [1, 3], times: ["08:00:00", "09:00:00"] });
  });
});
