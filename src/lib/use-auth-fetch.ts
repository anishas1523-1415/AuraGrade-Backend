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
    try {
      supabaseRef.current = createClient();
    } catch {
      supabaseRef.current = null;
    }
  }

  return useCallback(
    async (url: string, options: RequestInit = {}): Promise<Response> => {
      let session = null;
      if (supabaseRef.current) {
        try {
          const result = await supabaseRef.current.auth.getSession();
          session = result.data.session;
        } catch {
          session = null;
        }
      }

      const headers = new Headers(options.headers);
      if (session?.access_token) {
        headers.set("Authorization", `Bearer ${session.access_token}`);
      }

      try {
        return await fetch(url, { ...options, headers });
      } catch {
        return new Response(JSON.stringify({ error: "Backend unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        });
      }
    },
    []
  );
}
