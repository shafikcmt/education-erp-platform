import type * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      data-slot="input"
      className={cn(
        "bg-background placeholder:text-muted-foreground h-11 w-full min-w-0 rounded-md border px-3 text-base shadow-xs transition-[color,box-shadow] outline-none sm:h-10 sm:text-sm",
        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
        "aria-invalid:border-destructive aria-invalid:ring-destructive/20 disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
