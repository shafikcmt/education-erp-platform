"use client";

import { useEffect, useState } from "react";

/**
 * Read `#token=...` from the URL fragment once, then remove it from the address bar and history
 * (plan §6.4): the token never reaches server logs, Referer headers or browser storage.
 */
export function useFragmentToken(): { token: string | null; ready: boolean } {
  const [state, setState] = useState<{ token: string | null; ready: boolean }>({
    token: null,
    ready: false,
  });
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const token = params.get("token");
    if (window.location.hash) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time read of the URL fragment
    setState({ token: token && /^[\w-]{20,256}$/.test(token) ? token : null, ready: true });
  }, []);
  return state;
}
