"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import GradingDashboard from "@/components/GradingDashboard";
import { useAuth } from "@/lib/auth-context";

export default function GradingPage() {
  const router = useRouter();
  const { user, profile, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
      return;
    }

    const role = (profile?.role || "").toUpperCase();
    if (role === "ADMIN_COE") router.replace("/admin/dashboard");
    else if (role === "HOD_AUDITOR") router.replace("/hod");
    else if (role === "PROCTOR") router.replace("/proctor");
    else if (role !== "EVALUATOR") router.replace("/student");
  }, [loading, user, profile, router]);

  if (loading) return <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center">Loading grading portal...</div>;
  if (!user || (profile?.role || "").toUpperCase() !== "EVALUATOR") return null;

  return <GradingDashboard />;
}
