"use client";

import React, { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Search,
  ArrowRight,
  GraduationCap,
  Cpu,
  Trophy,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  LayoutDashboard,
  LogIn,
} from "lucide-react";
import Link from "next/link";
import { UserBadge } from "@/components/UserBadge";
import { useAuth } from "@/lib/auth-context";
import { StudentLogin } from "@/components/StudentLogin";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface StudentInfo {
  id: string;
  reg_no: string;
  name: string;
  email: string;
}

interface GradeEntry {
  id: string;
  ai_score: number;
  confidence: number;
  is_flagged: boolean;
  prof_status: string;
  graded_at: string;
  assessments: {
    subject: string;
    title: string;
  };
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Auth Button (Sign In / User Badge)                                 */
/* ------------------------------------------------------------------ */

function AuthButton() {
  const { user, loading } = useAuth();
  if (loading) return <div className="h-9 w-9 rounded-xl bg-white/5 animate-pulse" />;
  if (user) return <UserBadge />;
  return (
    <Link href="/login">
      <Button variant="outline" size="sm" className="border-white/10 bg-white/5 hover:bg-white/10 text-white/60 backdrop-blur-md text-xs">
        <LogIn className="mr-1.5 h-3.5 w-3.5" /> Sign In
      </Button>
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function StudentDashboard() {
  const router = useRouter();

  const [regNo, setRegNo] = useState("");
  const [student, setStudent] = useState<StudentInfo | null>(null);
  const [grades, setGrades] = useState<GradeEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* ---------- Fetch student grades (re-search) ---------- */
  const handleSearch = useCallback(async () => {
    if (!regNo.trim()) return;
    setLoading(true);
    setError(null);
    setSearched(false);

    try {
      const res = await fetch(`${API_URL}/api/students/${encodeURIComponent(regNo.trim())}/grades`);
      if (!res.ok) {
        throw new Error(res.status === 404 ? "Student not found" : "Failed to fetch grades");
      }
      const data = await res.json();
      setStudent(data.student);
      setGrades(data.grades || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setStudent(null);
      setGrades([]);
    } finally {
      setLoading(false);
      setSearched(true);
    }
  }, [regNo]);

  /* ---------- Helpers ---------- */
  const statusBadge: Record<string, { color: string; label: string }> = {
    Pending: { color: "border-blue-500/30 bg-blue-500/10 text-blue-400", label: "Pending" },
    Approved: { color: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400", label: "Approved" },
    Flagged: { color: "border-amber-500/30 bg-amber-500/10 text-amber-400", label: "Under Review" },
    Overridden: { color: "border-purple-500/30 bg-purple-500/10 text-purple-400", label: "Overridden" },
  };

  const getScoreColor = (score: number) =>
    score >= 7 ? "text-emerald-400" : score >= 4 ? "text-amber-400" : "text-red-400";

  const avgScore =
    grades.length > 0
      ? Math.round((grades.reduce((sum, g) => sum + g.ai_score, 0) / grades.length) * 10) / 10
      : 0;

  /* ── Show StudentLogin gateway until student is identified ── */
  if (!student) {
    return (
      <StudentLogin
        onAuthenticated={(s, g) => {
          setStudent(s);
          setGrades(g);
          setSearched(true);
        }}
      />
    );
  }
  const approvedCount = grades.filter((g) => g.prof_status === "Approved").length;
  const flaggedCount = grades.filter((g) => g.is_flagged).length;

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0b1120] to-black text-white font-sans">
      <div className="mx-auto max-w-5xl px-6 py-8">
        {/* ========== TOP BAR ========== */}
        <div className="flex items-center justify-between mb-12">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
              <GraduationCap className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-white/90">AuraGrade</h1>
              <p className="text-[10px] uppercase tracking-[0.15em] text-white/30">Student Portal · {student.reg_no}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setStudent(null);
                setGrades([]);
                setSearched(false);
              }}
              className="border-white/10 bg-white/5 text-white/40 hover:bg-white/10 backdrop-blur-md text-xs"
            >
              <LogIn className="mr-1.5 h-3.5 w-3.5" /> Switch Student
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/")}
              className="border-white/10 bg-white/5 text-white/40 hover:bg-white/10 backdrop-blur-md text-xs"
            >
              <LayoutDashboard className="mr-1.5 h-3.5 w-3.5" /> Staff View
            </Button>
            <AuthButton />
          </div>
        </div>

        {/* ========== HERO / SEARCH ========== */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-10"
        >
          <h2 className="text-4xl font-black bg-gradient-to-r from-blue-400 via-cyan-300 to-indigo-400 bg-clip-text text-transparent mb-3">
            View Your Results
          </h2>
          <p className="text-white/30 text-sm max-w-md mx-auto">
            Enter your registration number to view AI-graded assessments, diagnostic feedback, and submit appeals.
          </p>
        </motion.div>

        <div className="flex items-center gap-3 max-w-md mx-auto mb-12">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-white/20" />
            <input
              type="text"
              value={regNo}
              onChange={(e) => setRegNo(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="e.g. 21CSE001"
              className="w-full rounded-xl border border-white/10 bg-white/5 backdrop-blur-md pl-10 pr-4 py-3 text-sm text-white/80 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-blue-500/40"
            />
          </div>
          <Button
            onClick={handleSearch}
            disabled={loading || !regNo.trim()}
            className="bg-blue-600 hover:bg-blue-500 text-white rounded-xl px-5 py-3 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Search"}
          </Button>
        </div>

        {/* ========== RESULTS ========== */}
        <AnimatePresence mode="wait">
          {searched && student && (
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
            >
              {/* Student info */}
              <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl mb-6">
                <CardContent className="py-5 px-6 flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <p className="text-lg font-bold text-white/90">{student.name}</p>
                    <p className="text-xs text-white/30">
                      {student.reg_no} · {student.email}
                    </p>
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="text-center">
                      <p className="text-[10px] uppercase tracking-wider text-white/30">Avg Score</p>
                      <p className={`text-2xl font-black ${getScoreColor(avgScore)}`}>{avgScore}</p>
                    </div>
                    <div className="h-8 w-px bg-white/10" />
                    <div className="text-center">
                      <p className="text-[10px] uppercase tracking-wider text-white/30">Assessments</p>
                      <p className="text-2xl font-black text-white/80">{grades.length}</p>
                    </div>
                    <div className="h-8 w-px bg-white/10" />
                    <div className="text-center">
                      <p className="text-[10px] uppercase tracking-wider text-white/30">Approved</p>
                      <p className="text-2xl font-black text-emerald-400">{approvedCount}</p>
                    </div>
                    {flaggedCount > 0 && (
                      <>
                        <div className="h-8 w-px bg-white/10" />
                        <div className="text-center">
                          <p className="text-[10px] uppercase tracking-wider text-white/30">Flagged</p>
                          <p className="text-2xl font-black text-amber-400">{flaggedCount}</p>
                        </div>
                      </>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Grade list */}
              {grades.length === 0 ? (
                <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
                  <CardContent className="py-16 flex flex-col items-center text-white/20">
                    <Trophy className="h-10 w-10 opacity-30 mb-3" />
                    <p className="text-sm">No graded assessments yet</p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-3">
                  {grades.map((g, idx) => {
                    const badge = statusBadge[g.prof_status] || statusBadge.Pending;
                    return (
                      <motion.div
                        key={g.id}
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.06 * idx }}
                      >
                        <Card
                          className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl hover:border-blue-500/20 hover:bg-white/[0.07] transition-colors cursor-pointer group"
                          onClick={() => router.push(`/student/results/${g.id}`)}
                        >
                          <CardContent className="py-4 px-6 flex items-center justify-between gap-4">
                            <div className="flex items-center gap-4 flex-1">
                              {/* Score circle */}
                              <div className="relative h-12 w-12 shrink-0">
                                <svg className="h-12 w-12 -rotate-90" viewBox="0 0 36 36">
                                  <circle
                                    cx="18"
                                    cy="18"
                                    r="16"
                                    fill="none"
                                    stroke="rgba(255,255,255,0.05)"
                                    strokeWidth="2.5"
                                  />
                                  <circle
                                    cx="18"
                                    cy="18"
                                    r="16"
                                    fill="none"
                                    stroke={g.ai_score >= 7 ? "#34d399" : g.ai_score >= 4 ? "#fbbf24" : "#f87171"}
                                    strokeWidth="2.5"
                                    strokeLinecap="round"
                                    strokeDasharray={`${(g.ai_score / 10) * 100.5} 100.5`}
                                  />
                                </svg>
                                <span className={`absolute inset-0 flex items-center justify-center text-sm font-bold ${getScoreColor(g.ai_score)}`}>
                                  {g.ai_score}
                                </span>
                              </div>

                              <div>
                                <p className="text-sm font-semibold text-white/80 group-hover:text-white/90">
                                  {g.assessments.subject}
                                </p>
                                <p className="text-xs text-white/30">{g.assessments.title}</p>
                              </div>
                            </div>

                            <div className="flex items-center gap-3">
                              <Badge className={`${badge.color} text-[10px]`}>{badge.label}</Badge>
                              {g.is_flagged && (
                                <AlertTriangle className="h-3.5 w-3.5 text-amber-400/60" />
                              )}
                              <span className="text-[10px] text-white/20 flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {new Date(g.graded_at).toLocaleDateString("en-IN", {
                                  day: "numeric",
                                  month: "short",
                                })}
                              </span>
                              <ArrowRight className="h-4 w-4 text-white/20 group-hover:text-blue-400 transition-colors" />
                            </div>
                          </CardContent>
                        </Card>
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </motion.div>
          )}

          {searched && error && grades.length === 0 && (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              className="text-center"
            >
              <Card className="rounded-2xl border border-red-500/20 bg-red-500/5 backdrop-blur-2xl inline-block">
                <CardContent className="py-6 px-8 flex items-center gap-3 text-red-300">
                  <AlertTriangle className="h-5 w-5 shrink-0" />
                  <p className="text-sm">{error}</p>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ========== FOOTER ========== */}
        <footer className="mt-16 flex items-center justify-center gap-2 text-[11px] text-white/15 tracking-wide">
          <Cpu className="h-3 w-3" />
          AuraGrade XAI · Student Portal · Gemini 3 Flash
        </footer>
      </div>
    </div>
  );
}
