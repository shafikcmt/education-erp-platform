import type * as React from "react";

import { Label } from "./label";

/** Label + control + hint/error, wired with ids and aria attributes for screen readers. */
export function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: (aria: {
    id: string;
    "aria-invalid": boolean;
    "aria-describedby"?: string;
  }) => React.ReactNode;
}) {
  const described = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean);
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      {children({
        id,
        "aria-invalid": Boolean(error),
        "aria-describedby": described.length ? described.join(" ") : undefined,
      })}
      {hint ? (
        <p id={`${id}-hint`} className="text-muted-foreground text-xs">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
    </div>
  );
}
