"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useAuthFetch } from "@/lib/use-auth-fetch";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronLeft,
  MessageSquareWarning,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  BookOpen,
  Clock,
  ShieldCheck,
  Scale,
  Gavel,
  Cpu,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  ChevronRight,
  Send,
  Sparkles,
  Eye,
} from "lucide-react";
import { useRouter } from "next/navigation";

import type { AuditNotes, AuditStep, GradeData } from "@/types/grading";

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function proficiencyLabel(pct: number): {
  text: string;
  color: string;
  ring: string;
  bg: string;
} {
  if (pct >= 85)
    return {
      text: "Exceptional",
      color: "text-emerald-400",
      ring: "text-emerald-500",
      bg: "shadow-emerald-500/30",
    };
  if (pct >= 70)
    return {
      text: "Proficient",
      color: "text-cyan-400",
      ring: "text-cyan-500",
      bg: "shadow-cyan-500/30",
    };
  if (pct >= 50)
    return {
      text: "Developing",
      color: "text-amber-400",
      ring: "text-amber-500",
      bg: "shadow-amber-500/30",
    };
  return {
    text: "Needs Support",
    color: "text-red-400",
    ring: "text-red-500",
    bg: "shadow-red-500/30",
  };
}

function sectionColor(pct: number): string {
  if (pct >= 80) return "text-emerald-400";
  if (pct >= 60) return "text-cyan-400";
  if (pct >= 40) return "text-amber-400";
  return "text-red-400";
}

function sectionBarColor(pct: number): string {
  if (pct >= 80) return "bg-emerald-500";
  if (pct >= 60) return "bg-cyan-500";
  if (pct >= 40) return "bg-amber-500";
  return "bg-red-500";
}

/** Build an AI diagnostic summary from feedback array */
function buildDiagnostic(feedback: string[]): string {
  if (!feedback || feedback.length === 0)
    return "No diagnostic information available for this submission.";
  const positives = feedback.filter(
    (f) =>
      f.toLowerCase().includes("correct") ||
      f.toLowerCase().includes("detected") ||
      f.includes("✅"),
  );
  const issues = feedback.filter(
    (f) =>
      f.toLowerCase().includes("missing") ||
      f.toLowerCase().includes("incorrect") ||
      f.includes("⚠"),
  );
  const parts: string[] = [];
  if (positives.length > 0)
    parts.push(`Strengths identified: ${positives[0].replace(/[✅⚠]/g, "").trim()}`);
  if (issues.length > 0)
    parts.push(`Area for improvement: ${issues[0].replace(/[✅⚠]/g, "").trim()}`);
  if (parts.length === 0) parts.push(feedback[0]);
  return `"${parts.join(". ")}."`;
}

/* ------------------------------------------------------------------ */
/*  SVG Circular Progress                                              */
/* ------------------------------------------------------------------ */

const RADIUS = 120;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

const CircularScore: React.FC<{
  score: number;
  total: number;
  proficiency: ReturnType<typeof proficiencyLabel>;
}> = ({ score, total, proficiency }) => {
  const pct = total > 0 ? (score / total) * 100 : 0;
  const offset = CIRCUMFERENCE - (CIRCUMFERENCE * pct) / 100;

  return (
    <motion.div
      initial={{ scale: 0.85, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", damping: 20, stiffness: 120 }}
      className="relative mx-auto w-[260px] h-[260px] flex items-center justify-center"
    >
      <svg
        className="w-full h-full -rotate-90"
        viewBox="0 0 280 280"
        fill="none"
      >
        {/* Track */}
        <circle
          cx="140"
          cy="140"
          r={RADIUS}
          stroke="currentColor"
          strokeWidth="12"
          className="text-white/[0.04]"
        />
        {/* Glow under ring */}
        <motion.circle
          cx="140"
          cy="140"
          r={RADIUS}
          stroke="currentColor"
          strokeWidth="18"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          initial={{ strokeDashoffset: CIRCUMFERENCE }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.6, ease: "easeOut", delay: 0.3 }}
          className={`${proficiency.ring} opacity-20 blur-sm`}
        />
        {/* Main ring */}
        <motion.circle
          cx="140"
          cy="140"
          r={RADIUS}
          stroke="currentColor"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          initial={{ strokeDashoffset: CIRCUMFERENCE }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.6, ease: "easeOut", delay: 0.3 }}
          className={proficiency.ring}
        />
      </svg>

      {/* Center label */}
      <div className="absolute flex flex-col items-center">
        <motion.span
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.8 }}
          className="text-6xl font-black italic text-white"
        >
          {score}
          <span className="text-xl text-slate-500 not-italic">/{total}</span>
        </motion.span>
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
          className={`text-[10px] font-bold ${proficiency.color} tracking-[0.3em] uppercase mt-2`}
        >
          {proficiency.text}
        </motion.span>
      </div>
    </motion.div>
  );
};

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

export const StudentMobileView: React.FC<{ gradeId: string }> = ({
  gradeId,
}) => {
  const router = useRouter();

  const [grade, setGrade] = useState<GradeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Appeal
  const [showAppeal, setShowAppeal] = useState(false);
  const [appealReason, setAppealReason] = useState("");
  const [appealSubmitting, setAppealSubmitting] = useState(false);
  const [appealSuccess, setAppealSuccess] = useState(false);

  // Audit
  const [auditRunning, setAuditRunning] = useState(false);
  const [auditSteps, setAuditSteps] = useState<AuditStep[]>([]);

  // Feedback expand
  const [expandFeedback, setExpandFeedback] = useState(false);

  const authFetch = useAuthFetch();
  /* ---------- Fetch ---------- */
  useEffect(() => {
    if (!gradeId) return;
    (async () => {
      try {
        const res = await authFetch(`${API_URL}/api/grades/${gradeId}`);
        if (!res.ok) throw new Error("Grade not found");
        setGrade(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    })();
  }, [gradeId, authFetch]);

  /* ---------- Appeal ---------- */
  const handleAppeal = useCallback(async () => {
    if (!appealReason.trim() || !gradeId) return;
    setAppealSubmitting(true);
    try {
      const qp = new URLSearchParams({ reason: appealReason });
      const res = await authFetch(
        `${API_URL}/api/grades/${gradeId}/appeal?${qp}`,
        { method: "PUT" },
      );
      if (res.ok) {
        setGrade((prev) =>
          prev
            ? { ...prev, prof_status: "Flagged", appeal_reason: appealReason }
            : prev,
        );
        setAppealSuccess(true);
        setTimeout(() => {
          setShowAppeal(false);
          setAppealReason("");
          setAppealSuccess(false);
        }, 1800);
      }
    } catch {
      /* silent */
    } finally {
      setAppealSubmitting(false);
    }
  }, [appealReason, gradeId, authFetch]);

  /* ---------- Audit Stream ---------- */
  const handleAudit = useCallback(async () => {
    if (!gradeId || auditRunning) return;
    setAuditRunning(true);
    setAuditSteps([]);
    try {
      const res = await authFetch(
        `${API_URL}/api/audit-appeal/${gradeId}/stream`,
        { method: "POST" },
      );
      if (!res.ok) throw new Error("Audit failed");
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No stream");
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        let evt = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) evt = line.slice(7).trim();
          else if (line.startsWith("data: ") && evt) {
            try {
              const p = JSON.parse(line.slice(6));
              if (evt === "step") setAuditSteps((s) => [...s, p as AuditStep]);
              else if (evt === "db") {
                const fr = await authFetch(`${API_URL}/api/grades/${gradeId}`);
                if (fr.ok) setGrade(await fr.json());
              }
            } catch {
              /* skip */
            }
            evt = "";
          }
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setAuditRunning(false);
    }
  }, [gradeId, auditRunning, authFetch]);

  /* ---------- Derived ---------- */
  const rubric = grade?.assessments.rubric_json;
  const totalMax = rubric
    ? Object.values(rubric).reduce((s, c) => s + c.max_marks, 0)
    : 10;
  const displayScore = grade
    ? rubric
      ? Math.round(
          (grade.ai_score / 10) * totalMax * 10,
        ) / 10
      : grade.ai_score
    : 0;
  const displayTotal = totalMax;
  const pct = displayTotal > 0 ? (displayScore / displayTotal) * 100 : 0;
  const proficiency = proficiencyLabel(pct);
  const confidencePct = grade ? Math.round(grade.confidence * 100) : 0;

  // Build sections from rubric
  const sections = rubric
    ? Object.entries(rubric).map(([key, c]) => {
        const estimated =
          totalMax > 0
            ? Math.round(((grade!.ai_score / 10) * c.max_marks * 10) / 10 * 10) / 10
            : 0;
        return {
          label: key.replace(/_/g, " "),
          score: estimated,
          max: c.max_marks,
          pct: c.max_marks > 0 ? (estimated / c.max_marks) * 100 : 0,
        };
      })
    : [{ label: "Overall", score: displayScore, max: displayTotal, pct }];

  // Audit notes parsed
  let auditNotes: AuditNotes | null = null;
  if (grade?.audit_notes) {
    try {
      auditNotes = JSON.parse(grade.audit_notes);
    } catch {
      /* ignore */
    }
  }

  /* ---------- Loading / Error ---------- */
  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 text-cyan-500 animate-spin" />
          <p className="text-[10px] text-white/20 uppercase tracking-[0.3em] font-bold">
            Loading Results
          </p>
        </div>
      </div>
    );
  }

  if (error || !grade) {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center gap-4 px-6">
        <AlertTriangle className="h-12 w-12 text-amber-400/60" />
        <p className="text-white/50 text-center">{error || "Grade not found"}</p>
        <button
          onClick={() => router.push("/student")}
          className="mt-2 px-6 py-3 rounded-2xl bg-white/5 border border-white/10 text-white/60 font-semibold text-sm active:scale-95 transition-transform"
        >
          Back to Dashboard
        </button>
      </div>
    );
  }

  const statusConfig: Record<
    string,
    { label: string; color: string; icon: React.ReactNode }
  > = {
    Pending: {
      label: "Pending Review",
      color: "border-blue-500/20 bg-blue-500/10 text-blue-400",
      icon: <Clock className="h-3 w-3" />,
    },
    Approved: {
      label: "Verified",
      color: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
      icon: <ShieldCheck className="h-3 w-3" />,
    },
    Flagged: {
      label: "Under Review",
      color: "border-amber-500/20 bg-amber-500/10 text-amber-400",
      icon: <AlertTriangle className="h-3 w-3" />,
    },
    Audited: {
      label: "Audited",
      color: "border-teal-500/20 bg-teal-500/10 text-teal-400",
      icon: <Gavel className="h-3 w-3" />,
    },
    Overridden: {
      label: "Overridden",
      color: "border-purple-500/20 bg-purple-500/10 text-purple-400",
      icon: <Scale className="h-3 w-3" />,
    },
  };
  const badge = statusConfig[grade.prof_status] || statusConfig.Pending;

  return (
    <div className="min-h-screen bg-black text-white font-sans pb-24">
      {/* ── Sticky Header ── */}
      <div className="p-4 flex items-center justify-between border-b border-white/[0.06] bg-slate-950/80 backdrop-blur-xl sticky top-0 z-50">
        <button
          onClick={() => router.push("/student")}
          className="p-2.5 bg-white/5 rounded-full active:scale-90 transition-transform"
        >
          <ChevronLeft className="h-5 w-5 text-white/60" />
        </button>
        <h1 className="text-[11px] font-black uppercase tracking-[0.25em] text-white/40 italic">
          AuraGrade Results
        </h1>
        <div className="w-10" />
      </div>

      <div className="px-5 pt-6 space-y-6">
        {/* ── Student & Assessment Info ── */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-between"
        >
          <div>
            <p className="text-lg font-bold text-white tracking-tight">
              {grade.students.name}
            </p>
            <p className="text-[11px] text-white/30 font-mono mt-0.5">
              {grade.students.reg_no} · {grade.assessments.subject}
            </p>
          </div>
          <div
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[10px] font-bold uppercase tracking-wider ${badge.color}`}
          >
            {badge.icon}
            {badge.label}
          </div>
        </motion.div>

        {/* ── Hero Circular Progress ── */}
        <CircularScore
          score={Math.round(displayScore)}
          total={Math.round(displayTotal)}
          proficiency={proficiency}
        />

        {/* ── Assessment Title ── */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="text-center -mt-2"
        >
          <p className="text-sm text-white/40 flex items-center justify-center gap-2">
            <BookOpen className="h-3.5 w-3.5" />
            {grade.assessments.title}
          </p>
          <p className="text-[10px] text-white/15 mt-1 flex items-center justify-center gap-1.5">
            <Clock className="h-2.5 w-2.5" />
            {new Date(grade.graded_at).toLocaleDateString("en-IN", {
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
            {" · "}Confidence: {confidencePct}%
          </p>
        </motion.div>

        {/* ── AI Diagnostic Card ── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="bg-slate-900/50 border border-white/[0.06] rounded-3xl p-5"
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-purple-500/15 rounded-xl">
              <Sparkles className="w-5 h-5 text-purple-400" />
            </div>
            <h3 className="font-bold text-[15px] text-white/90">
              AI Diagnostic
            </h3>
          </div>
          <p className="text-sm text-slate-300/80 leading-relaxed italic">
            {buildDiagnostic(grade.feedback)}
          </p>

          {/* Expandable full feedback */}
          {grade.feedback && grade.feedback.length > 1 && (
            <>
              <button
                onClick={() => setExpandFeedback(!expandFeedback)}
                className="mt-3 text-[10px] text-cyan-400/60 uppercase tracking-wider font-bold flex items-center gap-1"
              >
                <Eye className="h-3 w-3" />
                {expandFeedback
                  ? "Collapse Details"
                  : `View All ${grade.feedback.length} Points`}
              </button>
              <AnimatePresence>
                {expandFeedback && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-3 space-y-2 overflow-hidden"
                  >
                    {grade.feedback.map((point, i) => {
                      const isWarn =
                        point.toLowerCase().includes("missing") ||
                        point.toLowerCase().includes("incorrect") ||
                        point.includes("⚠");
                      const isPos =
                        point.toLowerCase().includes("correct") ||
                        point.toLowerCase().includes("detected") ||
                        point.includes("✅");
                      return (
                        <motion.div
                          key={i}
                          initial={{ opacity: 0, x: 8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.05 * i }}
                          className={`rounded-xl border px-3.5 py-2.5 text-[13px] leading-relaxed ${
                            isWarn
                              ? "border-amber-500/15 bg-amber-500/5 text-amber-200/80"
                              : isPos
                                ? "border-emerald-500/15 bg-emerald-500/5 text-emerald-200/80"
                                : "border-blue-500/10 bg-blue-500/5 text-blue-200/80"
                          }`}
                        >
                          {point}
                        </motion.div>
                      );
                    })}
                  </motion.div>
                )}
              </AnimatePresence>
            </>
          )}
        </motion.div>

        {/* ── Section Breakdown ── */}
        <div className="space-y-2.5">
          <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] ml-1">
            Section Breakdown
          </h4>
          {sections.map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.6 + 0.08 * i }}
              className="p-4 bg-white/[0.03] border border-white/[0.05] rounded-2xl"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-slate-200 capitalize">
                  {s.label}
                </span>
                <span className={`font-mono font-bold text-sm ${sectionColor(s.pct)}`}>
                  {s.score}/{s.max}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${sectionBarColor(s.pct)}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(100, s.pct)}%` }}
                  transition={{ duration: 0.8, delay: 0.7 + 0.08 * i }}
                />
              </div>
            </motion.div>
          ))}
        </div>

        {/* ── Confidence Meter ── */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.9 }}
          className="bg-white/[0.03] border border-white/[0.05] rounded-2xl p-4"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] text-white/30 uppercase tracking-wider font-bold">
              AI Confidence
            </span>
            <span
              className={`text-sm font-bold ${confidencePct >= 80 ? "text-emerald-400" : confidencePct >= 50 ? "text-amber-400" : "text-red-400"}`}
            >
              {confidencePct}%
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
            <motion.div
              className={`h-full rounded-full ${confidencePct >= 80 ? "bg-emerald-500" : confidencePct >= 50 ? "bg-amber-500" : "bg-red-500"}`}
              initial={{ width: 0 }}
              animate={{ width: `${confidencePct}%` }}
              transition={{ duration: 1, delay: 0.5 }}
            />
          </div>
          <p className="text-[10px] text-white/15 mt-2">
            {confidencePct >= 80
              ? "High confidence — AI is very certain about this evaluation"
              : confidencePct >= 50
                ? "Moderate confidence — some areas had ambiguity"
                : "Low confidence — manual review recommended"}
          </p>
        </motion.div>

        {/* ── Audit Verdict (if audited) ── */}
        {grade.prof_status === "Audited" && auditNotes && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-teal-500/5 border border-teal-500/15 rounded-3xl overflow-hidden"
          >
            <div className="px-5 py-4 border-b border-teal-500/10 flex items-center justify-between">
              <h3 className="text-sm font-bold text-teal-300/80 flex items-center gap-2">
                <Gavel className="h-4 w-4" /> Audit Verdict
              </h3>
              <span
                className={`text-[10px] font-bold uppercase px-2.5 py-1 rounded-full flex items-center gap-1 ${
                  auditNotes.verdict === "Upheld"
                    ? "bg-blue-500/15 text-blue-400"
                    : auditNotes.verdict === "Adjusted Up"
                      ? "bg-emerald-500/15 text-emerald-400"
                      : "bg-red-500/15 text-red-400"
                }`}
              >
                {auditNotes.verdict === "Upheld" ? (
                  <Minus className="h-3 w-3" />
                ) : auditNotes.verdict === "Adjusted Up" ? (
                  <ArrowUpRight className="h-3 w-3" />
                ) : (
                  <ArrowDownRight className="h-3 w-3" />
                )}
                {auditNotes.verdict}
              </span>
            </div>

            <div className="p-5 space-y-4">
              {/* Score comparison */}
              {auditNotes.original_score !== undefined &&
                grade.audit_score !== null && (
                  <div className="flex items-center gap-3">
                    <div className="flex-1 rounded-xl border border-white/5 bg-white/[0.02] px-4 py-2.5 text-center">
                      <p className="text-[9px] uppercase tracking-wider text-white/25 mb-0.5">
                        Original
                      </p>
                      <p className="text-lg font-bold text-white/40">
                        {auditNotes.original_score}
                      </p>
                    </div>
                    <ChevronRight className="h-4 w-4 text-white/15 shrink-0" />
                    <div className="flex-1 rounded-xl border border-teal-500/15 bg-teal-500/5 px-4 py-2.5 text-center">
                      <p className="text-[9px] uppercase tracking-wider text-white/25 mb-0.5">
                        Audited
                      </p>
                      <p className="text-lg font-bold text-teal-400">
                        {grade.audit_score}
                      </p>
                    </div>
                  </div>
                )}

              {/* Audit feedback */}
              {grade.audit_feedback && grade.audit_feedback.length > 0 && (
                <div className="space-y-1.5">
                  {grade.audit_feedback.map((s, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2.5 text-[12px] text-teal-200/60 leading-relaxed"
                    >
                      <span className="text-teal-400/40 font-mono text-[10px] mt-0.5 shrink-0">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      {s}
                    </div>
                  ))}
                </div>
              )}

              {auditNotes.recommendation && (
                <p className="text-[11px] text-white/25 italic leading-relaxed border-t border-white/5 pt-3">
                  {auditNotes.recommendation}
                </p>
              )}
            </div>
          </motion.div>
        )}

        {/* ── Live Audit Steps ── */}
        {auditSteps.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="bg-teal-500/5 border border-teal-500/10 rounded-2xl p-4"
          >
            <h4 className="text-[10px] text-teal-300/60 uppercase tracking-wider font-bold mb-3 flex items-center gap-2">
              <Gavel className="h-3 w-3" /> Audit Deliberation
              {auditRunning && (
                <Loader2 className="h-3 w-3 animate-spin ml-auto text-teal-400/40" />
              )}
            </h4>
            <div className="space-y-1.5">
              {auditSteps.map((step, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: 6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.04 * i }}
                  className="flex items-start gap-2 text-[11px] text-teal-200/50"
                >
                  <span className="shrink-0">{step.icon}</span>
                  <span className="leading-relaxed">{step.text}</span>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}

        {/* ── Action Buttons ── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1 }}
          className="grid grid-cols-2 gap-3"
        >
          <button
            onClick={() => router.push("/student")}
            className="flex items-center justify-center gap-2 py-4 bg-white text-black rounded-2xl font-black text-[13px] uppercase italic active:scale-95 transition-transform"
          >
            <CheckCircle2 className="w-4 h-4" /> All Results
          </button>

          {grade.prof_status === "Pending" ||
          grade.prof_status === "Approved" ? (
            <button
              onClick={() => setShowAppeal(true)}
              className="flex items-center justify-center gap-2 py-4 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-2xl font-black text-[13px] uppercase italic active:scale-95 transition-transform"
            >
              <MessageSquareWarning className="w-4 h-4" /> Appeal
            </button>
          ) : grade.prof_status === "Flagged" ? (
            <button
              onClick={handleAudit}
              disabled={auditRunning}
              className="flex items-center justify-center gap-2 py-4 bg-teal-500/10 border border-teal-500/20 text-teal-400 rounded-2xl font-black text-[13px] uppercase italic active:scale-95 transition-transform disabled:opacity-50"
            >
              {auditRunning ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Scale className="w-4 h-4" />
              )}
              {auditRunning ? "Auditing…" : "AI Audit"}
            </button>
          ) : (
            <button
              onClick={() => router.push("/student")}
              className="flex items-center justify-center gap-2 py-4 bg-white/5 border border-white/10 text-white/50 rounded-2xl font-bold text-[13px] uppercase active:scale-95 transition-transform"
            >
              <TrendingUp className="w-4 h-4" /> Dashboard
            </button>
          )}
        </motion.div>

        {/* ── Footer ── */}
        <div className="flex items-center justify-center gap-2 text-[10px] text-white/10 tracking-wide pt-4 pb-2">
          <Cpu className="h-3 w-3" />
          AuraGrade XAI · Three-Pass Evaluation · Gemini 3 Flash
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════ */}
      {/*  Appeal Bottom Sheet                                       */}
      {/* ══════════════════════════════════════════════════════════ */}
      <AnimatePresence>
        {showAppeal && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => {
                if (!appealSubmitting) setShowAppeal(false);
              }}
              className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[60]"
            />

            {/* Sheet */}
            <motion.div
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", damping: 30, stiffness: 300 }}
              className="fixed bottom-0 left-0 right-0 bg-slate-900 border-t border-white/[0.08] rounded-t-[2.5rem] p-7 pb-10 z-[70]"
            >
              {/* Drag handle */}
              <div className="w-12 h-1.5 bg-white/10 rounded-full mx-auto mb-7" />

              {appealSuccess ? (
                <motion.div
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  className="flex flex-col items-center py-6"
                >
                  <CheckCircle2 className="h-14 w-14 text-emerald-400 mb-4" />
                  <h3 className="text-xl font-black italic uppercase text-emerald-400">
                    Appeal Submitted
                  </h3>
                  <p className="text-xs text-white/30 mt-2">
                    The Supreme Court Audit Agent will review your case.
                  </p>
                </motion.div>
              ) : (
                <>
                  <h3 className="text-xl font-black italic uppercase mb-1.5 text-white">
                    Request Re-evaluation
                  </h3>
                  <p className="text-[11px] text-slate-400 mb-5 leading-relaxed">
                    Explain why you believe the AI missed a valid point. The
                    &ldquo;Supreme Court&rdquo; Audit Agent will review it
                    independently.
                  </p>

                  <textarea
                    value={appealReason}
                    onChange={(e) => setAppealReason(e.target.value)}
                    className="w-full bg-black/80 border border-white/[0.08] rounded-2xl p-4 text-sm text-white/80 placeholder:text-white/15 focus:border-cyan-500/40 outline-none mb-5 h-32 resize-none"
                    placeholder="e.g. My diagram for Q3 uses standard IEEE symbols which the AI might have misinterpreted..."
                  />

                  <button
                    onClick={handleAppeal}
                    disabled={!appealReason.trim() || appealSubmitting}
                    className="w-full py-5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-2xl font-black uppercase italic shadow-lg shadow-cyan-900/40 flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98] transition-all"
                  >
                    {appealSubmitting ? (
                      <Loader2 className="h-5 w-5 animate-spin" />
                    ) : (
                      <Send className="h-5 w-5" />
                    )}
                    {appealSubmitting ? "Submitting…" : "Submit Appeal"}
                  </button>
                </>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};

export default StudentMobileView;
