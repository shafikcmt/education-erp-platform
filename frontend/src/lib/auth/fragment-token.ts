"use client";

import { useEffect, useState } from "react";

type FragmentToken = { token: string | null; ready: boolean; version: number };

/**
 * Read `#token=...` from the URL fragment, then remove it from the address bar and history
 * (plan §6.4): the token never reaches server logs, Referer headers or browser storage.
 *
 * The fragment is read on load and again whenever a new one arrives without a reload (the same
 * emailed link opened in a tab that already shows the page); `version` counts the reads so a
 * page can refresh its data.
 */
export function useFragmentToken(): FragmentToken {
  const [state, setState] = useState<FragmentToken>({ token: null, ready: false, version: 0 });
  useEffect(() => {
    const read = (initial: boolean) => {
      const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
      if (!initial && !token) return; // our own clean-up below changes the hash too
      if (window.location.hash) {
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
      setState((previous) => ({
        token: token && /^[\w-]{20,256}$/.test(token) ? token : null,
        ready: true,
        version: previous.version + 1,
      }));
    };
    read(true);
    const onHashChange = () => read(false);
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  return state;
}
