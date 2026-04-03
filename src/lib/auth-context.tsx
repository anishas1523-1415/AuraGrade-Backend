"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import { createClient } from "@/lib/supabase/client";
import type { User, Session } from "@supabase/supabase-js";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type UserRole = "ADMIN_COE" | "HOD_AUDITOR" | "EVALUATOR" | "PROCTOR";

export interface Profile {
  id: string;
  full_name: string;
  email: string;
  department: string;
  role: UserRole;
}

interface AuthContextType {
  user: User | null;
  session: Session | null;
  profile: Profile | null;
  loading: boolean;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  isAdmin: boolean;
  isHOD: boolean;
  isEvaluator: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/* ------------------------------------------------------------------ */
/*  Provider                                                           */
/* ------------------------------------------------------------------ */

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const supabase = useMemo(() => createClient(), []);

  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const buildFallbackProfile = useCallback((currentUser: User): Profile => {
    const email = currentUser.email || "";
    const fullName =
      currentUser.user_metadata?.full_name ||
      currentUser.user_metadata?.name ||
      email.split("@")[0] ||
      "Evaluator";

    return {
      id: currentUser.id,
      full_name: fullName,
      email,
      department: "",
      role: "EVALUATOR",
    };
  }, []);

  /* ---------- Fetch profile from profiles table ---------- */
  const fetchProfile = useCallback(
    async (currentUser: User) => {
      try {
        const { data } = await supabase
          .from("profiles")
          .select("*")
          .eq("id", currentUser.id)
          .single();

        const baseProfile = data ? (data as Profile) : buildFallbackProfile(currentUser);

        try {
          const { data: staffData } = await supabase
            .from("coe_staff_profiles")
            .select("role, is_active")
            .eq("email", currentUser.email || "")
            .maybeSingle();

          if (
            staffData &&
            String(staffData.role || "").toUpperCase() === "EVALUATOR" &&
            staffData.is_active !== false
          ) {
            setProfile({
              ...baseProfile,
              role: "EVALUATOR",
              email: currentUser.email || baseProfile.email,
              full_name:
                baseProfile.full_name ||
                currentUser.user_metadata?.full_name ||
                currentUser.user_metadata?.name ||
                baseProfile.email.split("@")[0] ||
                "Evaluator",
            });
            return;
          }
        } catch {
          // Fall back to the main profiles table if COE staff lookup is unavailable.
        }

        setProfile(baseProfile);
      } catch {
        setProfile(buildFallbackProfile(currentUser));
      }
    },
    [supabase, buildFallbackProfile],
  );

  /* ---------- Initialize session ---------- */
  useEffect(() => {
    const init = async () => {
      try {
        const {
          data: { session: currentSession },
        } = await supabase.auth.getSession();

        setSession(currentSession);
        setUser(currentSession?.user ?? null);

        if (currentSession?.user) {
          await fetchProfile(currentSession.user);
        }
      } catch (err) {
        void err;
        setSession(null);
        setUser(null);
        setProfile(null);
      } finally {
        setLoading(false);
      }
    };

    init();

    // Listen for auth state changes (login, logout, token refresh)
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, newSession) => {
      try {
        setSession(newSession);
        setUser(newSession?.user ?? null);

        if (newSession?.user) {
          await fetchProfile(newSession.user);
        } else {
          setProfile(null);
        }
      } catch (err) {
        void err;
      } finally {
        setLoading(false);
      }
    });

    return () => subscription.unsubscribe();
  }, [supabase, fetchProfile]);

  /* ---------- Actions ---------- */
  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
    setUser(null);
    setSession(null);
    setProfile(null);
  }, [supabase]);

  const refreshProfile = useCallback(async () => {
    if (user) await fetchProfile(user);
  }, [user, fetchProfile]);

  /* ---------- Role helpers ---------- */
  const isAdmin = profile?.role === "ADMIN_COE";
  const isHOD = profile?.role === "HOD_AUDITOR";
  const isEvaluator = profile?.role === "EVALUATOR";

  const value = useMemo(
    () => ({
      user,
      session,
      profile,
      loading,
      signOut,
      refreshProfile,
      isAdmin,
      isHOD,
      isEvaluator,
    }),
    [user, session, profile, loading, signOut, refreshProfile, isAdmin, isHOD, isEvaluator],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/* ------------------------------------------------------------------ */
/*  Hook                                                               */
/* ------------------------------------------------------------------ */

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
