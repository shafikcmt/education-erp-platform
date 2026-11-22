"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/errors";

const KEY = ["notifications"] as const;

/** In-app notifications of this member (tenant hosts). Polls once a minute while open in a tab. */
export function NotificationBell() {
  const t = useTranslations("notifications");
  const format = useFormatter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const inbox = useQuery({
    queryKey: KEY,
    queryFn: () => unwrap(api().GET("/api/v1/notifications/")),
    refetchInterval: 60_000,
    retry: false,
  });
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (
        e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)
      )
        setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  if (!inbox.data) return null;
  const unread = inbox.data.items.filter((n) => !n.read_at).map((n) => n.id);
  const markAll = async () => {
    const data = await unwrap(api().POST("/api/v1/notifications/read/", { body: { ids: unread } }));
    queryClient.setQueryData(KEY, data);
  };
  return (
    <div className="relative" ref={box}>
      <Button
        variant="ghost"
        size="sm"
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={t("open", { count: inbox.data.unread })}
        onClick={() => setOpen(!open)}
        data-testid="notification-bell"
      >
        <Bell aria-hidden="true" />
        {inbox.data.unread ? (
          <span
            className="bg-destructive text-destructive-foreground rounded-full px-1.5 text-xs"
            data-testid="unread-count"
          >
            {inbox.data.unread > 99 ? "99+" : inbox.data.unread}
          </span>
        ) : null}
      </Button>
      {open ? (
        <div className="bg-background absolute right-0 z-20 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-md border p-2 shadow-lg">
          <div className="flex items-center justify-between px-1 pb-2">
            <span className="text-sm font-medium">{t("title")}</span>
            {unread.length ? (
              <Button size="sm" variant="ghost" onClick={() => void markAll()}>
                {t("markAll")}
              </Button>
            ) : null}
          </div>
          {inbox.data.items.length ? (
            <ul className="grid max-h-80 gap-1 overflow-y-auto" data-testid="notifications">
              {inbox.data.items.map((n) => (
                <li
                  key={n.id}
                  className={n.read_at ? "rounded p-2 text-sm" : "bg-accent/60 rounded p-2 text-sm"}
                >
                  <p className="font-medium">{n.title}</p>
                  {n.body ? <p className="text-muted-foreground">{n.body}</p> : null}
                  <p className="text-muted-foreground text-xs">
                    {format.dateTime(new Date(n.created_at), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground p-2 text-sm">{t("empty")}</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
