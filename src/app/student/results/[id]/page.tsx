"use client";

import React, { useState, useEffect } from "react";
import { useAuthFetch } from "@/lib/use-auth-fetch";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StudentMobileView } from "@/components/StudentMobileView";
import {
  MessageSquareQuote,
  RotateCcw,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  Cpu,
  TrendingUp,
  BookOpen,
  Clock,
  Loader2,
  Scale,
  Gavel,
  ChevronRight,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from "lucide-react";

import type { AuditNotes, AuditStep, GradeData } from "@/types/grading";

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */


export default function StudentResultPage() {
  const authFetch = useAuthFetch();
  const params = useParams();
  const router = useRouter();
  const gradeId = params.id as string;

  // All hooks must be declared before any conditional returns
  const [isMobile, setIsMobile] = useState(false);
  const [grade, setGrade] = useState<GradeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Appeal state
  const [appealReason, setAppealReason] = useState("");
  const [showAppeal, setShowAppeal] = useState(false);
  const [appealSubmitting, setAppealSubmitting] = useState(false);
  // Audit state
  const [auditRunning, setAuditRunning] = useState(false);
  const [auditSteps, setAuditSteps] = useState<AuditStep[]>([]);
  const [auditComplete, setAuditComplete] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // On mobile → render the full-screen StudentMobileView
  if (isMobile) return <StudentMobileView gradeId={gradeId} />;

  /* ---------- Fetch grade data ---------- */
  useEffect(() => {
    if (!gradeId) return;

    const fetchGrade = async () => {
      try {
        const res = await authFetch(`${API_URL}/api/grades/${gradeId}`);
        if (!res.ok) throw new Error("Grade not found");
        const data = await res.json();
        setGrade(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load grade");
      } finally {
        setLoading(false);
      }
    };
    fetchGrade();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gradeId]);

  /* ---------- Appeal handler ---------- */
  const handleAppeal = async () => {
    if (!appealReason.trim() || !gradeId) return;
    setAppealSubmitting(true);
    try {
      const qp = new URLSearchParams({ reason: appealReason });
      const res = await authFetch(`${API_URL}/api/grades/${gradeId}/appeal?${qp}`, {
        method: "PUT",
      });
      if (res.ok) {
        setGrade((prev) =>
          prev ? { ...prev, prof_status: "Flagged", appeal_reason: appealReason } : prev
        );
        setShowAppeal(false);
        setAppealReason("");
      }
    } catch {
      // silently fail
    } finally {
      setAppealSubmitting(false);
    }
  };

  /* ---------- Trigger Audit ---------- */
  const handleAuditRequest = async () => {
    if (!gradeId || auditRunning) return;
    setAuditRunning(true);
    setAuditSteps([]);
    setAuditComplete(false);

    try {
      const res = await authFetch(`${API_URL}/api/audit-appeal/${gradeId}/stream`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Audit request failed");

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No stream reader");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ") && currentEvent) {
            try {
              const payload = JSON.parse(line.slice(6));
              if (currentEvent === "step") {
                setAuditSteps((prev) => [...prev, payload as AuditStep]);
              } else if (currentEvent === "audit_result") {
                // Refresh grade data to get persisted audit
                setAuditComplete(true);
              } else if (currentEvent === "db") {
                // DB persisted — refresh grade data
                const freshRes = await authFetch(`${API_URL}/api/grades/${gradeId}`);
                if (freshRes.ok) {
                  const freshData = await freshRes.json();
                  setGrade(freshData);
                }
              }
            } catch {
              // skip malformed data
            }
            currentEvent = "";
          }
        }
      }
    } catch (err) {
      console.error("Audit stream error:", err);
    } finally {
      setAuditRunning(false);
    }
  };

  /* ---------- Derived ---------- */
  const confidencePct = grade ? Math.round(grade.confidence * 100) : 0;
  const scoreColor =
    grade && grade.ai_score >= 7
      ? "text-emerald-400"
      : grade && grade.ai_score >= 4
        ? "text-amber-400"
        : "text-red-400";
  const statusBadge: Record<string, { color: string; label: string }> = {
    Pending: { color: "border-blue-500/30 bg-blue-500/10 text-blue-400", label: "Pending Review" },
    Approved: { color: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400", label: "Approved" },
    Flagged: { color: "border-amber-500/30 bg-amber-500/10 text-amber-400", label: "Under Review" },
    Overridden: { color: "border-purple-500/30 bg-purple-500/10 text-purple-400", label: "Overridden" },
    Audited: { color: "border-teal-500/30 bg-teal-500/10 text-teal-400", label: "Audited" },
  };

  /* ---------- Loading / Error ---------- */
  if (loading) {
    return (
      <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0b1120] to-black flex items-center justify-center">
        <Loader2 className="h-8 w-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  if (error || !grade) {
    return (
      <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0b1120] to-black flex flex-col items-center justify-center text-white/60 gap-4">
        <AlertTriangle className="h-12 w-12 text-amber-400/60" />
        <p className="text-lg">{error || "Grade not found"}</p>
        <Button
          variant="outline"
          onClick={() => router.push("/student")}
          className="border-white/10 text-white/60 hover:bg-white/5"
        >
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Dashboard
        </Button>
      </div>
    );
  }

  const badge = statusBadge[grade.prof_status] || statusBadge.Pending;
  const rubric = grade.assessments.rubric_json;

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0b1120] to-black text-white font-sans">
      <div className="mx-auto max-w-[1440px] px-6 py-6">
        {/* ========== TOP BAR ========== */}
        <div className="flex items-center gap-3 mb-8">
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push("/student")}
            className="border-white/10 bg-white/5 text-white/60 hover:bg-white/10 backdrop-blur-md"
          >
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Back
          </Button>
          <div className="h-5 w-px bg-white/10" />
          <span className="text-xs text-white/30">
            {grade.students.reg_no} · {grade.assessments.subject}
          </span>
        </div>

        {/* ========== HEADER ========== */}
        <header className="flex flex-wrap items-end justify-between gap-6 mb-10">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <h1 className="text-4xl font-black tracking-tight bg-gradient-to-r from-blue-400 via-cyan-300 to-indigo-400 bg-clip-text text-transparent">
              Performance Insights
            </h1>
            <p className="text-white/40 mt-2 flex items-center gap-2">
              <BookOpen className="h-4 w-4" />
              {grade.assessments.subject} — {grade.assessments.title}
            </p>
            <div className="flex items-center gap-3 mt-3">
              <Badge className={`${badge.color} text-xs`}>
                {badge.label}
              </Badge>
              <span className="text-xs text-white/30 flex items-center gap-1">
                <Clock className="h-3 w-3" />
                Graded {new Date(grade.graded_at).toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </span>
              {grade.reviewed_at && (
                <span className="text-xs text-white/30">
                  · Reviewed {new Date(grade.reviewed_at).toLocaleDateString("en-IN", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </span>
              )}
            </div>
          </motion.div>

          {/* Score display */}
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="text-right"
          >
            <p className="text-[10px] uppercase tracking-[0.2em] text-white/30 font-bold mb-1">
              Final Score
            </p>
            <p className={`text-6xl font-black ${scoreColor}`}>
              {grade.ai_score}
              <span className="text-xl text-white/20 font-normal"> / 10</span>
            </p>
            <p className="text-xs text-white/30 mt-1">
              Confidence: <span className={scoreColor}>{confidencePct}%</span>
            </p>
          </motion.div>
        </header>

        {/* ========== MAIN GRID ========== */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* ─── LEFT: Rubric Breakdown + Score Ring ─── */}
          <Card className="lg:col-span-2 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-hidden">
            <div className="border-b border-white/10 px-6 py-4">
              <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-cyan-400" />
                Rubric Breakdown
              </h3>
            </div>
            <CardContent className="p-6">
              {rubric ? (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {Object.entries(rubric).map(([key, criterion], idx) => {
                    // Estimate per-criterion score from total (proportional)
                    const maxTotal = Object.values(rubric).reduce(
                      (sum, c) => sum + c.max_marks,
                      0
                    );
                    const estimated = maxTotal > 0
                      ? Math.round((grade.ai_score / maxTotal) * criterion.max_marks * 10) / 10
                      : 0;
                    const pct = criterion.max_marks > 0
                      ? Math.min(100, Math.round((estimated / criterion.max_marks) * 100))
                      : 0;

                    return (
                      <motion.div
                        key={key}
                        initial={{ opacity: 0, y: 16 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.15 * idx }}
                        className="rounded-xl border border-white/5 bg-white/[0.03] p-5"
                      >
                        <p className="text-[10px] uppercase tracking-wider text-white/30 mb-3">
                          {key.replace(/_/g, " ")}
                        </p>

                        {/* Score ring */}
                        <div className="flex items-center justify-center mb-3">
                          <svg className="h-20 w-20 -rotate-90" viewBox="0 0 36 36">
                            <path
                              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                              fill="none"
                              stroke="rgba(255,255,255,0.05)"
                              strokeWidth="3"
                            />
                            <motion.path
                              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                              fill="none"
                              stroke={pct >= 70 ? "#34d399" : pct >= 40 ? "#fbbf24" : "#f87171"}
                              strokeWidth="3"
                              strokeLinecap="round"
                              initial={{ strokeDasharray: "0, 100" }}
                              animate={{ strokeDasharray: `${pct}, 100` }}
                              transition={{ duration: 1, delay: 0.3 + 0.15 * idx }}
                            />
                          </svg>
                          <span className="absolute text-lg font-bold text-white/80">
                            {estimated}
                          </span>
                        </div>

                        <p className="text-center text-xs text-white/40">
                          out of {criterion.max_marks}
                        </p>
                        <p className="text-center text-[10px] text-white/20 mt-1">
                          {criterion.description}
                        </p>
                      </motion.div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 text-white/20">
                  <BookOpen className="h-10 w-10 opacity-30 mb-3" />
                  <p className="text-sm">No rubric data available for this assessment</p>
                </div>
              )}

              {/* Flagged warning */}
              {grade.is_flagged && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="mt-6 flex items-center gap-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-300"
                >
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  This submission was flagged by AI for manual review. A professor will verify the grade.
                </motion.div>
              )}
            </CardContent>
          </Card>

          {/* ─── RIGHT: AI Diagnostic Feedback ─── */}
          <div className="space-y-6">
            <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-hidden">
              <div className="border-b border-white/10 px-5 py-4">
                <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                  <MessageSquareQuote className="h-4 w-4 text-blue-400" />
                  AI Diagnostic
                </h3>
              </div>

              <ScrollArea className="max-h-[420px]">
                <div className="p-5 space-y-3">
                  <AnimatePresence>
                    {(grade.feedback || []).map((point, i) => {
                      const isWarning =
                        point.toLowerCase().includes("missing") ||
                        point.toLowerCase().includes("incorrect") ||
                        point.includes("⚠");
                      const isPositive =
                        point.toLowerCase().includes("correct") ||
                        point.toLowerCase().includes("detected") ||
                        point.includes("✅");

                      return (
                        <motion.div
                          key={i}
                          initial={{ opacity: 0, x: 12 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.08 * i }}
                          className={`rounded-xl border px-4 py-3 text-sm leading-relaxed ${
                            isWarning
                              ? "border-amber-500/20 bg-amber-500/10 text-amber-200"
                              : isPositive
                                ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-200"
                                : "border-blue-500/15 bg-blue-500/10 text-blue-200"
                          }`}
                        >
                          {point}
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>

                  {(!grade.feedback || grade.feedback.length === 0) && (
                    <p className="text-center text-white/20 text-sm py-8">
                      No feedback available
                    </p>
                  )}
                </div>
              </ScrollArea>
            </Card>

            {/* ─── Confidence Meter ─── */}
            <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-white/40 uppercase tracking-wider">AI Confidence</span>
                <span className={`text-sm font-bold ${scoreColor}`}>{confidencePct}%</span>
              </div>
              <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    confidencePct >= 80
                      ? "bg-gradient-to-r from-emerald-500 to-emerald-400"
                      : confidencePct >= 50
                        ? "bg-gradient-to-r from-amber-500 to-amber-400"
                        : "bg-gradient-to-r from-red-500 to-red-400"
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${confidencePct}%` }}
                  transition={{ duration: 1, delay: 0.3, ease: "easeOut" }}
                />
              </div>
              <p className="text-[10px] text-white/20 mt-2">
                {confidencePct >= 80
                  ? "High confidence — AI is very certain about this grade"
                  : confidencePct >= 50
                    ? "Moderate confidence — some uncertainties detected"
                    : "Low confidence — manual review recommended"}
              </p>
            </Card>

            {/* ─── Appeal & Audit System ─── */}
            {grade.prof_status === "Pending" || grade.prof_status === "Approved" ? (
              <div className="space-y-3">
                {!showAppeal ? (
                  <Button
                    variant="outline"
                    className="w-full border-red-500/20 text-red-400 hover:bg-red-500/10 backdrop-blur-md"
                    onClick={() => setShowAppeal(true)}
                  >
                    <RotateCcw className="mr-2 h-4 w-4" />
                    Request Manual Review
                  </Button>
                ) : (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    className="space-y-3"
                  >
                    <textarea
                      value={appealReason}
                      onChange={(e) => setAppealReason(e.target.value)}
                      placeholder="Describe why you believe this grade needs review…"
                      rows={3}
                      className="w-full rounded-xl border border-red-500/20 bg-white/5 px-4 py-3 text-sm text-white/80 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-red-500/40 resize-none"
                    />
                    <div className="flex gap-2">
                      <Button
                        onClick={handleAppeal}
                        disabled={!appealReason.trim() || appealSubmitting}
                        className="flex-1 bg-red-600 hover:bg-red-500 text-white text-xs disabled:opacity-50"
                      >
                        {appealSubmitting ? (
                          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <RotateCcw className="mr-2 h-3.5 w-3.5" />
                        )}
                        Submit Appeal
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => {
                          setShowAppeal(false);
                          setAppealReason("");
                        }}
                        className="border-white/10 text-white/40 hover:bg-white/5 text-xs"
                      >
                        Cancel
                      </Button>
                    </div>
                  </motion.div>
                )}
              </div>
            ) : grade.prof_status === "Flagged" ? (
              <div className="space-y-3">
                <Card className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5">
                  <div className="flex items-center gap-2 text-amber-400 text-sm font-medium mb-2">
                    <AlertTriangle className="h-4 w-4" />
                    Appeal Submitted
                  </div>
                  <p className="text-xs text-amber-200/60 mb-3">
                    {grade.appeal_reason || "Awaiting professor review."}
                  </p>
                  <Button
                    onClick={handleAuditRequest}
                    disabled={auditRunning}
                    className="w-full bg-teal-600 hover:bg-teal-500 text-white text-xs disabled:opacity-50"
                  >
                    {auditRunning ? (
                      <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Scale className="mr-2 h-3.5 w-3.5" />
                    )}
                    {auditRunning ? "Audit in Progress…" : "Request AI Audit"}
                  </Button>
                </Card>

                {/* Live audit deliberation steps */}
                {auditSteps.length > 0 && (
                  <Card className="rounded-2xl border border-teal-500/20 bg-teal-500/5 overflow-hidden">
                    <div className="border-b border-teal-500/10 px-4 py-3">
                      <h4 className="text-xs font-semibold text-teal-300/80 flex items-center gap-2">
                        <Gavel className="h-3.5 w-3.5" />
                        Audit Deliberation
                        {auditRunning && (
                          <Loader2 className="h-3 w-3 animate-spin ml-auto text-teal-400/50" />
                        )}
                      </h4>
                    </div>
                    <ScrollArea className="max-h-[260px]">
                      <div className="p-3 space-y-1.5">
                        {auditSteps.map((step, i) => (
                          <motion.div
                            key={i}
                            initial={{ opacity: 0, x: 8 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 0.05 * i }}
                            className="flex items-start gap-2 text-xs text-teal-200/70 py-1"
                          >
                            <span className="shrink-0 text-sm">{step.icon}</span>
                            <span className="leading-relaxed">{step.text}</span>
                          </motion.div>
                        ))}
                      </div>
                    </ScrollArea>
                  </Card>
                )}
              </div>
            ) : grade.prof_status === "Audited" ? (
              <Card className="rounded-2xl border border-teal-500/20 bg-teal-500/5 p-5">
                <div className="flex items-center gap-2 text-teal-400 text-sm font-medium mb-1">
                  <Gavel className="h-4 w-4" />
                  Audit Complete
                </div>
                <p className="text-xs text-teal-200/60">
                  This grade has been re-evaluated by the AI Audit Agent. See the full verdict below.
                </p>
              </Card>
            ) : (
              <Card className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5">
                <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium">
                  <ShieldCheck className="h-4 w-4" />
                  Grade has been verified by professor
                </div>
              </Card>
            )}
          </div>
        </div>

        {/* ========== AUDIT VERDICT PANEL (full-width) ========== */}
        {grade.prof_status === "Audited" && grade.audit_notes && (() => {
          let notes: AuditNotes | null = null;
          try { notes = JSON.parse(grade.audit_notes); } catch { /* ignore */ }
          if (!notes) return null;

          const verdictConfig = {
            "Upheld": { icon: <Minus className="h-5 w-5" />, color: "text-blue-400", bg: "bg-blue-500/10 border-blue-500/20", label: "Original Grade Upheld" },
            "Adjusted Up": { icon: <ArrowUpRight className="h-5 w-5" />, color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20", label: "Score Adjusted Upward" },
            "Adjusted Down": { icon: <ArrowDownRight className="h-5 w-5" />, color: "text-red-400", bg: "bg-red-500/10 border-red-500/20", label: "Score Adjusted Downward" },
          };
          const v = verdictConfig[notes.verdict] || verdictConfig["Upheld"];
          const rubricKeys = Object.keys(notes.rubric_breakdown || {});

          return (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="mt-8"
            >
              <Card className="rounded-2xl border border-teal-500/15 bg-white/[0.03] backdrop-blur-2xl overflow-hidden">
                <div className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                    <Scale className="h-4 w-4 text-teal-400" />
                    Audit Verdict — Head of Department Review
                  </h3>
                  <Badge className={`${v.bg} border text-xs flex items-center gap-1 ${v.color}`}>
                    {v.icon}
                    {v.label}
                  </Badge>
                </div>

                <div className="p-6 space-y-6">
                  {/* Score comparison */}
                  {notes.original_score !== undefined && grade.audit_score !== null && (
                    <div className="flex items-center gap-4">
                      <div className="rounded-xl border border-white/5 bg-white/[0.02] px-5 py-3 text-center">
                        <p className="text-[10px] uppercase tracking-wider text-white/30 mb-1">Original</p>
                        <p className="text-2xl font-bold text-white/50">{notes.original_score}<span className="text-sm text-white/20">/10</span></p>
                      </div>
                      <ChevronRight className="h-5 w-5 text-white/20" />
                      <div className={`rounded-xl border px-5 py-3 text-center ${v.bg}`}>
                        <p className="text-[10px] uppercase tracking-wider text-white/30 mb-1">Audited</p>
                        <p className={`text-2xl font-bold ${v.color}`}>{grade.audit_score}<span className="text-sm text-white/20">/10</span></p>
                      </div>
                      {notes.original_score !== grade.audit_score && (
                        <div className="ml-2">
                          <span className={`text-sm font-semibold ${v.color}`}>
                            {(grade.audit_score - notes.original_score) > 0 ? "+" : ""}{(grade.audit_score - notes.original_score).toFixed(1)}
                          </span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Justification steps */}
                  {grade.audit_feedback && grade.audit_feedback.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
                        <Gavel className="h-3.5 w-3.5 text-teal-400" />
                        Audit Justification
                      </h4>
                      <div className="space-y-2">
                        {grade.audit_feedback.map((step: string, i: number) => (
                          <motion.div
                            key={i}
                            initial={{ opacity: 0, x: 12 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 0.1 * i }}
                            className="flex items-start gap-3 rounded-xl border border-teal-500/10 bg-teal-500/5 px-4 py-3 text-sm text-teal-100/80 leading-relaxed"
                          >
                            <span className="shrink-0 text-teal-400/60 font-mono text-xs mt-0.5">{String(i + 1).padStart(2, "0")}</span>
                            {step}
                          </motion.div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Rubric breakdown comparison */}
                  {rubricKeys.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3">
                        Per-Criterion Audit
                      </h4>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {rubricKeys.map((key) => {
                          const item = notes!.rubric_breakdown[key];
                          const delta = item.audited - item.original;
                          return (
                            <div key={key} className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                              <p className="text-[10px] uppercase tracking-wider text-white/30 mb-2">
                                {key.replace(/_/g, " ")}
                              </p>
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-sm text-white/40">{item.original}</span>
                                <ChevronRight className="h-3 w-3 text-white/15" />
                                <span className={`text-sm font-semibold ${delta > 0 ? "text-emerald-400" : delta < 0 ? "text-red-400" : "text-white/60"}`}>
                                  {item.audited}
                                </span>
                                {delta !== 0 && (
                                  <span className={`text-xs ${delta > 0 ? "text-emerald-400/60" : "text-red-400/60"}`}>
                                    ({delta > 0 ? "+" : ""}{delta.toFixed(1)})
                                  </span>
                                )}
                              </div>
                              <p className="text-[11px] text-white/30 leading-relaxed">{item.note}</p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Recommendation */}
                  {notes.recommendation && (
                    <div className="rounded-xl border border-white/5 bg-white/[0.02] px-5 py-4">
                      <p className="text-[10px] uppercase tracking-wider text-white/30 mb-2">Professor Recommendation</p>
                      <p className="text-sm text-white/60 leading-relaxed">{notes.recommendation}</p>
                    </div>
                  )}
                </div>
              </Card>
            </motion.div>
          );
        })()}

        {/* ========== XAI Attribution ========== */}
        <footer className="mt-10 flex items-center justify-center gap-2 text-[11px] text-white/15 tracking-wide">
          <Cpu className="h-3 w-3" />
          AuraGrade XAI · Three-Pass Agentic Evaluation · Gemini 3 Flash · Supabase
        </footer>
      </div>
    </div>
  );
}
