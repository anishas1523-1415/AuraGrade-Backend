"use client";

import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "coe_portal_token";
const MEMBER_KEY = "coe_portal_member";

export type CoeMember = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  department?: string | null;
  is_active?: boolean;
};

type CoeLoginInput = {
  full_name: string;
  dob: string;
  email: string;
  password: string;
};

type CoeAuthContextValue = {
  token: string | null;
  member: CoeMember | null;
  loading: boolean;
  login: (input: CoeLoginInput) => Promise<{ ok: boolean; message?: string }>;
  logout: () => void;
  authFetch: (url: string, options?: RequestInit) => Promise<Response>;
};

const CoeAuthContext = createContext<CoeAuthContextValue | undefined>(undefined);

export function CoeAuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [member, setMember] = useState<CoeMember | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const savedToken = window.localStorage.getItem(TOKEN_KEY);
    const savedMember = window.localStorage.getItem(MEMBER_KEY);
    if (savedToken) setToken(savedToken);
    if (savedMember) {
      try {
        setMember(JSON.parse(savedMember) as CoeMember);
      } catch {
        window.localStorage.removeItem(MEMBER_KEY);
      }
    }

    const bootstrap = async () => {
      if (!savedToken) {
        setLoading(false);
        return;
      }

      try {
        const res = await fetch(`${API_URL}/api/coe/me`, {
          headers: { Authorization: `Bearer ${savedToken}` },
        });
        if (!res.ok) {
          window.localStorage.removeItem(TOKEN_KEY);
          window.localStorage.removeItem(MEMBER_KEY);
          setToken(null);
          setMember(null);
        } else {
          const data = (await res.json()) as { member?: CoeMember };
          if (data.member) {
            setMember(data.member);
            window.localStorage.setItem(MEMBER_KEY, JSON.stringify(data.member));
          }
        }
      } catch {
        window.localStorage.removeItem(TOKEN_KEY);
        window.localStorage.removeItem(MEMBER_KEY);
        setToken(null);
        setMember(null);
      } finally {
        setLoading(false);
      }
    };

    void bootstrap();
  }, []);

  const login = async (input: CoeLoginInput) => {
    try {
      const res = await fetch(`${API_URL}/api/coe/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        return { ok: false, message: data?.detail || data?.message || "Login failed" };
      }

      const accessToken = data?.access_token as string | undefined;
      const safeMember = data?.member as CoeMember | undefined;
      if (!accessToken || !safeMember) {
        return { ok: false, message: "Invalid login response from server" };
      }

      setToken(accessToken);
      setMember(safeMember);
      window.localStorage.setItem(TOKEN_KEY, accessToken);
      window.localStorage.setItem(MEMBER_KEY, JSON.stringify(safeMember));
      return { ok: true };
    } catch {
      return { ok: false, message: "Unable to reach the COE portal API" };
    }
  };

  const logout = () => {
    setToken(null);
    setMember(null);
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(MEMBER_KEY);
    router.push("/coe/login");
  };

  const authFetch = async (url: string, options: RequestInit = {}) => {
    const headers = new Headers(options.headers);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    return fetch(url, { ...options, headers });
  };

  const value = useMemo(
    () => ({ token, member, loading, login, logout, authFetch }),
    [token, member, loading],
  );

  return <CoeAuthContext.Provider value={value}>{children}</CoeAuthContext.Provider>;
}

export function useCoeAuth() {
  const context = useContext(CoeAuthContext);
  if (!context) {
    throw new Error("useCoeAuth must be used within CoeAuthProvider");
  }
  return context;
}
