import { supabase } from "./supabase";

const API_BASE = process.env.EXPO_PUBLIC_API_URL;

if (!API_BASE) {
  throw new Error(
    "FATAL: EXPO_PUBLIC_API_URL environment variable is not set. " +
    "Configure it in app.json or .env file (e.g., EXPO_PUBLIC_API_URL=http://localhost:8000)"
  );
}

export { API_BASE };

export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await getAccessToken();
  const headers = new Headers(init.headers || {});

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const hasJsonBody = !!init.body && !(init.body instanceof FormData);
  if (hasJsonBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
}
