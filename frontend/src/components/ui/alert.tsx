import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/utils";

const alertVariants = cva("rounded-lg border px-4 py-3 text-sm [&_p]:leading-relaxed", {
  variants: {
    variant: {
      default: "bg-card text-card-foreground",
      destructive: "border-destructive/50 text-destructive bg-destructive/5",
      warning: "border-warning/50 bg-warning/10 text-foreground",
      success: "border-success/50 bg-success/10 text-foreground",
    },
  },
  defaultVariants: { variant: "default" },
});

function Alert({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  const live = variant === "destructive" ? "alert" : "status";
  return (
    <div
      data-slot="alert"
      role={live}
      className={cn(alertVariants({ variant }), className)}
      {...props}
    />
  );
}

export { Alert };
