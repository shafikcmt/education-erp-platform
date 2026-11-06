"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { PageHeader } from "@/components/app/page-header";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";
import { can, useMe } from "@/lib/auth/me";
import { emailSchema } from "@/lib/auth/schemas";
import { useErrorMessage } from "@/lib/auth/use-error-message";

function CreateUserDialog({ onCreated }: { onCreated: () => void }) {
  const t = useTranslations();
  const errorMessage = useErrorMessage();
  const [open, setOpen] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const schema = z.object({
    email: emailSchema(t),
    display_name: z.string().max(150),
    locale: z.enum(["en", "bn"]),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", display_name: "", locale: "en" },
  });
  const submit = form.handleSubmit(async (values) => {
    setFailure(null);
    try {
      await unwrap(api().POST("/api/v1/platform/users/", { body: values }));
      form.reset();
      setOpen(false);
      onCreated();
    } catch (error) {
      setFailure(errorMessage(error));
    }
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>{t("users.create")}</Button>
      </DialogTrigger>
      <DialogContent closeLabel={t("common.close")}>
        <DialogTitle>{t("users.create")}</DialogTitle>
        <DialogDescription>{t("users.createHint")}</DialogDescription>
        <form onSubmit={submit} className="grid gap-4" noValidate>
          {failure ? <Alert variant="destructive">{failure}</Alert> : null}
          <Field
            id="new-user-email"
            label={t("auth.email")}
            error={form.formState.errors.email?.message}
          >
            {(aria) => (
              <Input type="email" autoComplete="off" {...aria} {...form.register("email")} />
            )}
          </Field>
          <Field id="new-user-name" label={t("account.displayName")}>
            {(aria) => <Input autoComplete="off" {...aria} {...form.register("display_name")} />}
          </Field>
          <Field id="new-user-locale" label={t("account.emailLanguage")}>
            {(aria) => (
              <select
                className="bg-background h-10 rounded-md border px-3 text-sm"
                {...aria}
                {...form.register("locale")}
              >
                <option value="en">English</option>
                <option value="bn">বাংলা</option>
              </select>
            )}
          </Field>
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {t("users.sendInvite")}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function UsersPage() {
  const t = useTranslations();
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const users = useQuery({
    queryKey: ["platform", "users", search, page],
    queryFn: () =>
      unwrap(api().GET("/api/v1/platform/users/", { params: { query: { search, page } } })),
  });
  const data = users.data;
  return (
    <>
      <PageHeader
        title={t("users.title")}
        description={t("users.subtitle")}
        actions={
          can(me, "identity.user.create") ? (
            <CreateUserDialog
              onCreated={() =>
                void queryClient.invalidateQueries({ queryKey: ["platform", "users"] })
              }
            />
          ) : null
        }
      />
      <div className="mb-4 max-w-sm">
        <Field id="user-search" label={t("users.search")}>
          {(aria) => (
            <Input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              {...aria}
            />
          )}
        </Field>
      </div>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted text-start">
            <tr>
              <th scope="col" className="p-3 text-start">
                {t("auth.email")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("users.status")}
              </th>
              <th scope="col" className="p-3 text-start">
                {t("users.roles")}
              </th>
            </tr>
          </thead>
          <tbody>
            {(data?.results ?? []).map((u) => (
              <tr key={u.id} className="border-t">
                <td className="p-3">
                  <Link
                    href={`/platform/users/${u.id}`}
                    className="text-primary font-medium hover:underline"
                  >
                    {u.email}
                  </Link>
                  {u.display_name ? (
                    <div className="text-muted-foreground text-xs">{u.display_name}</div>
                  ) : null}
                </td>
                <td className="p-3">
                  {!u.is_active
                    ? t("users.deactivated")
                    : u.activated_at
                      ? t("users.active")
                      : t("users.pending")}
                </td>
                <td className="p-3">{u.platform_roles.join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!data?.previous}
          onClick={() => setPage((p) => p - 1)}
        >
          {t("common.previous")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!data?.next}
          onClick={() => setPage((p) => p + 1)}
        >
          {t("common.next")}
        </Button>
      </div>
    </>
  );
}
