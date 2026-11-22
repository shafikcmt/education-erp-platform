"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

/** "Create an organisation" — only while self-service sign-up is open (platform host; the
 * endpoint does not exist on tenant hosts, so nothing is shown there). */
export function SignupLink() {
  const t = useTranslations("signup");
  const availability = useQuery({
    queryKey: ["signup", "availability"],
    queryFn: () => unwrap(api().GET("/api/v1/signup/")),
    retry: false,
  });
  if (!availability.data?.enabled) return null;
  return (
    <Link href="/signup" className="text-primary text-sm underline-offset-4 hover:underline">
      {t("create")}
    </Link>
  );
}
