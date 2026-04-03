"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import GradingDashboard from "@/components/GradingDashboard";
import { useAuth } from "@/lib/auth-context";

export default function GradingPage() {
  const router = useRouter();
  const { user, profile, loading } = useAuth();
  const role = (profile?.role || "").trim().toUpperCase();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }

    if (role === "ADMIN_COE") router.replace("/admin/dashboard");
    else if (role === "HOD_AUDITOR") router.replace("/hod");
    else if (role === "PROCTOR") router.replace("/proctor");
  }, [loading, user, profile, router]);

  if (loading) return <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center">Loading grading portal...</div>;
  if (!user || role !== "EVALUATOR") {
    return (
      <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-6">
        <div className="max-w-md rounded-2xl border border-white/10 bg-white/5 px-6 py-8 text-center backdrop-blur-xl">
          <p className="text-sm font-semibold">
            {user ? "This account does not have evaluator access." : "Sign in to access the grading portal."}
          </p>
          <p className="mt-2 text-xs text-white/40">
            Evaluator access is required for Staff Grading.
          </p>
        </div>
      </div>
    );
  }

  return <GradingDashboard />;
}
