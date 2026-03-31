import { supabase } from "./supabase";

/**
 * AuraGrade Mobile — API client
 *
 * API_BASE is read exclusively from EXPO_PUBLIC_API_URL.
 * The previous fallback to a hardcoded LAN IP (192.168.x.x) caused silent
 * failures on any network other than the developer's home network.
 *
 * Set EXPO_PUBLIC_API_URL in your .env file:
 *   EXPO_PUBLIC_API_URL=https://your-backend-domain.com      (production)
 *   EXPO_PUBLIC_API_URL=http://192.168.x.x:8000              (local dev)
 */

const _apiUrl = process.env.EXPO_PUBLIC_API_URL;

if (!_apiUrl) {
  throw new Error(
    "[AuraGrade] EXPO_PUBLIC_API_URL is not set.\n" +
    "Add it to your .env file:\n" +
    "  EXPO_PUBLIC_API_URL=https://your-backend-domain.com\n" +
    "  EXPO_PUBLIC_API_URL=http://YOUR_LOCAL_IP:8000  (local dev)\n"
  );
}

export const API_BASE = _apiUrl;

export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

/**
 * Authenticated fetch wrapper — injects Supabase JWT as Bearer token.
 * Propagates X-Request-ID from response for backend log correlation.
 */
export async function authFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const token = await getAccessToken();
  const headers = new Headers(init.headers || {});

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const hasJsonBody = !!init.body && !(init.body instanceof FormData);
  if (hasJsonBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (__DEV__) {
    const requestId = response.headers.get("X-Request-ID");
    if (requestId) {
      console.debug(
        `[AuraGrade] ${init.method || "GET"} ${path} → ${response.status} [req:${requestId}]`
      );
    }
  }

  return response;
}
