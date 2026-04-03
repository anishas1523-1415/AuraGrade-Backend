"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BarChart3, PieChart, Shield, Users, TrendingDown, ArrowLeft } from "lucide-react";
import {
  BarChart,
  Bar,
  PieChart as RePieChart,
  Pie,
  Cell,
  CartesianGrid,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { useAuthFetch } from "@/lib/use-auth-fetch";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const PIE_COLORS = ["#22c55e", "#ef4444", "#38bdf8", "#a855f7"];

type DepartmentStats = {
  total_assessments: number;
  total_students: number;
  allocation_count: number;
  subject_breakdown: Array<{
    subject: string;
    class_id: string;
    semester: string;
    staff_email: string;
    pass_count: number;
    fail_count: number;
    fail_rate: number;
    avg_score: number;
  }>;
  lagging_subjects: Array<{
    subject: string;
    class_id: string;
    semester: string;
    staff_email: string;
    pass_count: number;
    fail_count: number;
    fail_rate: number;
    avg_score: number;
  }>;
  staff_performance: Array<{
    staff_email: string;
    subject_count: number;
    student_count: number;
    pass_count: number;
    fail_count: number;
    avg_score: number;
  }>;
};

export default function HODPortalPage() {
  const router = useRouter();
  const { profile, loading } = useAuth();
  const authFetch = useAuthFetch();

  const [stats, setStats] = useState<DepartmentStats | null>(null);
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    if (loading) return;
    if (!profile || profile.role !== "HOD_AUDITOR") {
      router.replace("/");
      return;
    }

    const load = async () => {
      setBusy(true);
      try {
        const res = await authFetch(`${API_URL}/api/hod/department-stats`);
        if (res.ok) {
          const payload = await res.json();
          setStats(payload.data as DepartmentStats);
        }
      } finally {
        setBusy(false);
      }
    };

    load();
  }, [loading, profile, router, authFetch]);

  const subjectChartData = useMemo(() => {
    return (stats?.subject_breakdown || []).map((item) => ({
      name: item.subject,
      Pass: item.pass_count,
      Fail: item.fail_count,
    }));
  }, [stats]);

  const pieData = useMemo(() => {
    const lagging = stats?.lagging_subjects.length || 0;
    const healthy = Math.max((stats?.subject_breakdown.length || 0) - lagging, 0);
    return [
      { name: "Healthy", value: healthy },
      { name: "Lagging", value: lagging },
    ];
  }, [stats]);

  if (loading || busy) {
    return <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center">Loading HOD portal…</div>;
  }

  if (!profile || profile.role !== "HOD_AUDITOR") {
    return (
      <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-6">
        <Card className="max-w-lg border-white/10 bg-white/5">
          <CardContent className="p-8 text-center space-y-4">
            <Shield className="mx-auto h-12 w-12 text-amber-400" />
            <h1 className="text-2xl font-bold">Access Restricted</h1>
            <p className="text-white/60">This portal is reserved for HOD accounts only.</p>
            <Button asChild>
              <Link href="/">Return Home</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.16),transparent_30%),linear-gradient(180deg,#020617_0%,#0f172a_100%)] text-white">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <Badge className="border-cyan-400/30 bg-cyan-500/10 text-cyan-300">HOD Portal</Badge>
              <Badge className="border-white/10 bg-white/5 text-white/60">Department Scoped</Badge>
            </div>
            <h1 className="text-3xl font-black tracking-tight">Department Performance Control Room</h1>
            <p className="mt-2 text-sm text-white/55">Only your department&apos;s performance, staff workload, and lagging subjects are visible here.</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" className="border-white/10 bg-white/5 text-white" onClick={() => router.back()}>
              <ArrowLeft className="mr-2 h-4 w-4" /> Back
            </Button>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <div className="flex items-center gap-3 text-white/70"><Users className="h-4 w-4" /> Total Students</div>
              <div className="mt-3 text-3xl font-black">{stats?.total_students ?? 0}</div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <div className="flex items-center gap-3 text-white/70"><BarChart3 className="h-4 w-4" /> Subject Allocations</div>
              <div className="mt-3 text-3xl font-black">{stats?.allocation_count ?? 0}</div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <div className="flex items-center gap-3 text-white/70"><TrendingDown className="h-4 w-4" /> Lagging Subjects</div>
              <div className="mt-3 text-3xl font-black">{stats?.lagging_subjects.length ?? 0}</div>
            </CardContent>
          </Card>
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-2">
          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <div className="mb-4 flex items-center gap-2 text-white/80"><BarChart3 className="h-4 w-4" /> Subject-wise Pass / Fail</div>
              <div className="h-[360px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={subjectChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="name" stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="Pass" fill="#22c55e" radius={[6, 6, 0, 0]} />
                    <Bar dataKey="Fail" fill="#ef4444" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <div className="mb-4 flex items-center gap-2 text-white/80"><PieChart className="h-4 w-4" /> Subject Health</div>
              <div className="h-[360px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <RePieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={120} label>
                      {pieData.map((_, index) => (
                        <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </RePieChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-2">
          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <h2 className="mb-4 text-lg font-semibold">Lagging Subjects</h2>
              <div className="space-y-3">
                {(stats?.lagging_subjects || []).length === 0 ? (
                  <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-white/60">No lagging subjects detected.</div>
                ) : stats!.lagging_subjects.map((item) => (
                  <div key={`${item.subject}-${item.class_id}-${item.semester}`} className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-semibold text-white">{item.subject}</div>
                        <div className="text-xs text-white/50">Class {item.class_id || "-"} · Semester {item.semester || "-"} · {item.staff_email || "Unassigned"}</div>
                      </div>
                      <Badge className="border-red-400/20 bg-red-500/10 text-red-300">{Math.round(item.fail_rate * 100)}% fail</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <h2 className="mb-4 text-lg font-semibold">Staff Performance</h2>
              <div className="space-y-3">
                {(stats?.staff_performance || []).length === 0 ? (
                  <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-white/60">No staff performance data available.</div>
                ) : stats!.staff_performance.map((item) => (
                  <div key={item.staff_email} className="rounded-xl border border-white/10 bg-white/5 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-semibold text-white">{item.staff_email}</div>
                        <div className="text-xs text-white/50">{item.subject_count} allocations · {item.student_count} students</div>
                      </div>
                      <Badge className="border-emerald-400/20 bg-emerald-500/10 text-emerald-300">Avg {item.avg_score}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}