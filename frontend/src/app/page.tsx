"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import LandingPage from "@/components/LandingPage";
import { useAuth } from "@/lib/auth-context";

export default function Home() {
  const router = useRouter();
  const { user, profile, loading } = useAuth();

  useEffect(() => {
    if (loading || !user || !profile) return;

    const role = (profile.role || "").toUpperCase();
    if (role === "ADMIN_COE") router.replace("/admin/dashboard");
    else if (role === "HOD_AUDITOR") router.replace("/hod");
    else if (role === "EVALUATOR") router.replace("/grading");
    else if (role === "PROCTOR") router.replace("/proctor");
    else router.replace("/student");
  }, [loading, user, profile, router]);

  return <LandingPage />;
}
