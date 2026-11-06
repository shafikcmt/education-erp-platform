"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api/browser";
import { ME_KEY } from "@/lib/auth/me";

const WARN_BEFORE_SECONDS = 120;

/**
 * Warns before the 30-minute idle timeout (plan §6.7). The server enforces the timeout; this
 * only tracks API activity in this tab: the timer restarts after each successful API call.
 */
export function IdleWarning({ idleTimeoutSeconds }: { idleTimeoutSeconds: number }) {
  const t = useTranslations("idle");
  const tc = useTranslations("common");
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const lastActivity = useRef(0);

  useEffect(() => {
    lastActivity.current = Date.now();
    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      if (event.type === "updated" && event.action.type === "success") {
        lastActivity.current = Date.now();
      }
    });
    const unsubscribeMutations = queryClient.getMutationCache().subscribe((event) => {
      if (event.type === "updated" && event.action.type === "success") {
        lastActivity.current = Date.now();
      }
    });
    const timer = window.setInterval(() => {
      const idle = (Date.now() - lastActivity.current) / 1000;
      if (idle >= idleTimeoutSeconds) {
        window.clearInterval(timer);
        router.replace("/login?expired=1");
      } else {
        setOpen(idle >= idleTimeoutSeconds - WARN_BEFORE_SECONDS);
      }
    }, 5_000);
    return () => {
      unsubscribe();
      unsubscribeMutations();
      window.clearInterval(timer);
    };
  }, [idleTimeoutSeconds, queryClient, router]);

  const stay = async () => {
    await queryClient.refetchQueries({ queryKey: ME_KEY });
    setOpen(false);
  };
  const signOut = async () => {
    await api().POST("/api/v1/auth/logout/");
    queryClient.clear();
    router.replace("/login");
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : void stay())}>
      <DialogContent closeLabel={tc("close")} data-testid="idle-warning">
        <DialogTitle>{t("title")}</DialogTitle>
        <DialogDescription>{t("body", { minutes: WARN_BEFORE_SECONDS / 60 })}</DialogDescription>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => void signOut()}>
            {t("signOut")}
          </Button>
          <Button onClick={() => void stay()}>{t("stay")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
