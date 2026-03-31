"use client";

import React, { useState, useRef, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { LogOut, Shield, User, ChevronDown } from "lucide-react";

/**
 * Glassmorphic user badge with role indicator and sign-out dropdown.
 * Place in the top bar of every dashboard.
 */
export function UserBadge() {
  const { user, profile, signOut, loading } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (loading || !user) return null;

  const initials = (profile?.full_name || user.email || "U")
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  const roleLabel: Record<string, string> = {
    ADMIN_COE: "Controller of Examinations",
    HOD_AUDITOR: "HOD / Auditor",
    EVALUATOR: "Evaluator",
    PROCTOR: "Proctor",
  };

  const roleBadgeColor: Record<string, string> = {
    ADMIN_COE: "border-red-500/30 bg-red-500/10 text-red-400",
    HOD_AUDITOR: "border-purple-500/30 bg-purple-500/10 text-purple-400",
    EVALUATOR: "border-blue-500/30 bg-blue-500/10 text-blue-400",
    PROCTOR: "border-teal-500/30 bg-teal-500/10 text-teal-400",
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl border border-white/10 bg-white/5 backdrop-blur-xl hover:bg-white/10 transition-colors"
      >
        {/* Avatar */}
        <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-blue-500/30 to-purple-500/30 border border-white/10 flex items-center justify-center text-[10px] font-bold text-white/70">
          {initials}
        </div>

        {/* Name + Role */}
        <div className="hidden sm:block text-left">
          <p className="text-xs text-white/70 font-medium leading-tight">
            {profile?.full_name || user.email?.split("@")[0]}
          </p>
          <p className="text-[9px] text-white/30 leading-tight">
            {roleLabel[profile?.role || "EVALUATOR"] || profile?.role}
          </p>
        </div>

        <ChevronDown className={`h-3 w-3 text-white/20 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 mt-2 w-56 rounded-xl border border-white/10 bg-slate-900/95 backdrop-blur-2xl shadow-2xl overflow-hidden z-50">
          <div className="px-4 py-3 border-b border-white/5">
            <p className="text-xs text-white/70 font-medium">{profile?.full_name || "User"}</p>
            <p className="text-[10px] text-white/30 mt-0.5">{user.email}</p>
            <div
              className={`inline-flex items-center gap-1 mt-2 px-2 py-0.5 rounded-md border text-[9px] font-medium ${
                roleBadgeColor[profile?.role || "EVALUATOR"] || roleBadgeColor.EVALUATOR
              }`}
            >
              <Shield className="h-2.5 w-2.5" />
              {roleLabel[profile?.role || "EVALUATOR"]}
            </div>
          </div>

          {profile?.department && (
            <div className="px-4 py-2 border-b border-white/5">
              <p className="text-[10px] text-white/20">Department</p>
              <p className="text-xs text-white/50">{profile.department || "—"}</p>
            </div>
          )}

          <button
            onClick={async () => {
              await signOut();
              window.location.href = "/login";
            }}
            className="w-full px-4 py-2.5 flex items-center gap-2 text-xs text-red-400 hover:bg-red-500/5 transition-colors"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sign Out
          </button>
        </div>
      )}
    </div>
  );
}
