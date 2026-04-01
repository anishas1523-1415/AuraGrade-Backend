"use client";

import { createClient } from "@/lib/supabase/client";

/**
 * Returns an authenticated fetch function that injects the Supabase JWT
 * into the Authorization header for backend API calls.
 *
 * Usage:
 *   const authFetch = useAuthFetch();
 *   const res = await authFetch("/api/admin/stats");
 */
import { useCallback, useRef } from "react";

export function useAuthFetch() {
  const supabaseRef = useRef<ReturnType<typeof createClient> | null>(null);
  if (!supabaseRef.current) {
    supabaseRef.current = createClient();
  }

  return useCallback(
    async (url: string, options: RequestInit = {}): Promise<Response> => {
      const {
        data: { session },
      } = await supabaseRef.current.auth.getSession();

      const headers = new Headers(options.headers);
      if (session?.access_token) {
        headers.set("Authorization", `Bearer ${session.access_token}`);
      }

      return fetch(url, { ...options, headers });
    },
    []
  );
}
