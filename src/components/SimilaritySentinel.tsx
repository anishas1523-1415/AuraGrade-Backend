"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldAlert,
  Users,
  Loader2,
  RefreshCcw,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Eye,
  Cpu,
  Zap,
  ScanLine,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface CollusionFlag {
  studentA: string;
  studentA_id: string;
  studentB: string;
  studentB_id: string;
  similarity: number;
  status: "Critical" | "Warning";
  snippet_a?: string;
  snippet_b?: string;
  assessment_subject?: string;
  assessment_title?: string;
  graded_at?: string;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Severity helpers                                                   */
/* ------------------------------------------------------------------ */

function severityColors(status: string) {
  if (status === "Critical") {
    return {
      badge: "bg-rose-500 text-white",
      border: "border-rose-500/30 hover:border-rose-500/50",
      glow: "shadow-rose-500/10",
      bar: "bg-rose-500",
      text: "text-rose-500",
      avatarB: "bg-rose-900 border-rose-700 text-rose-200",
    };
  }
  return {
    badge: "bg-amber-500/20 text-amber-500",
    border: "border-amber-500/20 hover:border-amber-500/40",
    glow: "shadow-amber-500/5",
    bar: "bg-amber-500",
    text: "text-amber-400",
    avatarB: "bg-amber-900/60 border-amber-700 text-amber-200",
  };
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export const SimilaritySentinel: React.FC<{
  authFetch: (url: string, init?: RequestInit) => Promise<Response>;
  assessmentId?: string;
}> = ({ authFetch, assessmentId }) => {
  const [flags, setFlags] = useState<CollusionFlag[]>([]);
  const [totalFlags, setTotalFlags] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [threshold, setThreshold] = useState(90);

  /* ---------- Fetch collusion flags ---------- */
  const fetchFlags = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const thresholdDecimal = threshold / 100;
      const url = assessmentId
        ? `${API_URL}/api/sentinel/scan/${assessmentId}?threshold=${thresholdDecimal}`
        : `${API_URL}/api/sentinel/flags?threshold=${thresholdDecimal}&limit=20`;

      const res = await authFetch(url);
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: "Server error" }));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setFlags(data.flags || []);
      setTotalFlags(data.total_flags ?? data.flags?.length ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch");
    } finally {
      setLoading(false);
    }
  }, [authFetch, assessmentId, threshold]);

  useEffect(() => {
    fetchFlags();
  }, [fetchFlags]);

  /* ---------- Stats ---------- */
  const criticalCount = flags.filter((f) => f.status === "Critical").length;
  const warningCount = flags.filter((f) => f.status === "Warning").length;

  return (
    <div className="bg-slate-900/80 border border-rose-500/15 rounded-3xl p-6 overflow-hidden relative">
      {/* Ambient danger glow */}
      <div className="absolute -top-10 -right-10 w-40 h-40 bg-rose-500/8 rounded-full blur-[80px] animate-pulse pointer-events-none" />
      <div className="absolute -bottom-8 -left-8 w-32 h-32 bg-rose-600/5 rounded-full blur-[60px] pointer-events-none" />

      {/* ── Header ── */}
      <div className="flex items-start justify-between mb-6 relative z-10">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-rose-500/15 border border-rose-500/25 rounded-2xl">
            <ShieldAlert className="w-6 h-6 text-rose-500" />
          </div>
          <div>
            <h3 className="text-xl font-black italic text-white uppercase tracking-tighter">
              Similarity Sentinel
            </h3>
            <p className="text-[10px] text-slate-500 font-bold uppercase tracking-[0.2em]">
              Cross-Script Collusion Detection
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Threshold control */}
          <div className="flex items-center gap-2 bg-white/[0.03] border border-white/[0.06] rounded-xl px-3 py-1.5">
            <span className="text-[9px] text-white/30 uppercase tracking-wider font-bold">
              Threshold
            </span>
            <select
              value={threshold}
              onChange={(e) => setThreshold(parseInt(e.target.value))}
              className="bg-transparent text-xs text-white/70 font-mono font-bold outline-none cursor-pointer"
            >
              <option value={85} className="bg-slate-900">85%</option>
              <option value={88} className="bg-slate-900">88%</option>
              <option value={90} className="bg-slate-900">90%</option>
              <option value={92} className="bg-slate-900">92%</option>
              <option value={95} className="bg-slate-900">95%</option>
            </select>
          </div>

          <button
            onClick={fetchFlags}
            disabled={loading}
            className="p-2 rounded-xl bg-white/5 hover:bg-white/10 transition-colors disabled:opacity-40"
          >
            <RefreshCcw
              className={`h-4 w-4 text-white/40 ${loading ? "animate-spin" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* ── Stats Row ── */}
      <div className="grid grid-cols-3 gap-3 mb-6 relative z-10">
        <div className="bg-white/[0.03] border border-white/[0.05] rounded-xl px-4 py-3 text-center">
          <p className="text-[9px] text-white/25 uppercase tracking-wider font-bold mb-1">
            Total Flags
          </p>
          <p className="text-2xl font-black text-white/80 font-mono">
            {totalFlags}
          </p>
        </div>
        <div className="bg-rose-500/5 border border-rose-500/15 rounded-xl px-4 py-3 text-center">
          <p className="text-[9px] text-rose-400/50 uppercase tracking-wider font-bold mb-1">
            Critical
          </p>
          <p className="text-2xl font-black text-rose-500 font-mono">
            {criticalCount}
          </p>
        </div>
        <div className="bg-amber-500/5 border border-amber-500/15 rounded-xl px-4 py-3 text-center">
          <p className="text-[9px] text-amber-400/50 uppercase tracking-wider font-bold mb-1">
            Warning
          </p>
          <p className="text-2xl font-black text-amber-400 font-mono">
            {warningCount}
          </p>
        </div>
      </div>

      {/* ── Loading / Error ── */}
      {loading && flags.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 relative z-10">
          <div className="relative">
            <ScanLine className="h-10 w-10 text-rose-500/30 animate-pulse" />
            <Loader2 className="h-5 w-5 text-rose-400 animate-spin absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
          </div>
          <p className="text-[10px] text-white/20 uppercase tracking-[0.3em] font-bold mt-4">
            Scanning Vector Database…
          </p>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-300 mb-4 relative z-10">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* ── Collusion Flags ── */}
      {!loading && flags.length === 0 && !error && (
        <div className="flex flex-col items-center justify-center py-16 text-white/15 relative z-10">
          <ShieldAlert className="h-10 w-10 opacity-20 mb-3" />
          <p className="text-sm">No collusion flags detected</p>
          <p className="text-[10px] text-white/10 mt-1">
            All submissions appear to be original at {threshold}% threshold
          </p>
        </div>
      )}

      <div className="space-y-3 relative z-10">
        <AnimatePresence>
          {flags.map((flag, i) => {
            const c = severityColors(flag.status);
            const isExpanded = expandedIdx === i;

            return (
              <motion.div
                key={`${flag.studentA}-${flag.studentB}-${i}`}
                initial={{ x: -20, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                transition={{ delay: i * 0.06 }}
                className={`group relative bg-black/40 border ${c.border} p-5 rounded-2xl transition-all cursor-pointer shadow-lg ${c.glow}`}
                onClick={() => setExpandedIdx(isExpanded ? null : i)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    {/* Overlapping avatar pair */}
                    <div className="flex -space-x-3">
                      <div className="w-10 h-10 rounded-full bg-slate-800 border-2 border-slate-900 flex items-center justify-center text-[10px] font-bold text-white uppercase z-[1]">
                        {flag.studentA.slice(-3)}
                      </div>
                      <div
                        className={`w-10 h-10 rounded-full border-2 border-slate-900 flex items-center justify-center text-[10px] font-bold uppercase ${c.avatarB}`}
                      >
                        {flag.studentB.slice(-3)}
                      </div>
                    </div>

                    <div>
                      <p className="text-xs font-bold text-white flex items-center gap-1.5">
                        {flag.studentA}
                        <span className="text-white/20">↔</span>
                        {flag.studentB}
                      </p>
                      <p className="text-[10px] text-slate-500 font-mono">
                        {flag.assessment_subject
                          ? `${flag.assessment_subject} · ${flag.assessment_title || ""}`
                          : "Semantic Match Detected"}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className={`text-xl font-black italic ${c.text}`}>
                        {flag.similarity}%
                      </div>
                      <div
                        className={`text-[9px] font-bold px-2 py-0.5 rounded-full inline-block ${c.badge}`}
                      >
                        {flag.status.toUpperCase()}
                      </div>
                    </div>
                    {isExpanded ? (
                      <ChevronUp className="h-4 w-4 text-white/20" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-white/20" />
                    )}
                  </div>
                </div>

                {/* Similarity bar */}
                <div className="mt-3 h-1 rounded-full bg-white/[0.04] overflow-hidden">
                  <motion.div
                    className={`h-full rounded-full ${c.bar}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${flag.similarity}%` }}
                    transition={{ duration: 0.8, delay: 0.1 + i * 0.06 }}
                  />
                </div>

                {/* Expanded detail */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="mt-4 pt-4 border-t border-white/5 space-y-3">
                        {/* Snippet comparison */}
                        {(flag.snippet_a || flag.snippet_b) && (
                          <div className="grid grid-cols-2 gap-3">
                            <div className="bg-white/[0.02] rounded-xl p-3">
                              <p className="text-[9px] text-white/25 uppercase tracking-wider font-bold mb-1.5 flex items-center gap-1">
                                <Users className="h-2.5 w-2.5" />
                                {flag.studentA}
                              </p>
                              <p className="text-[11px] text-white/40 leading-relaxed font-mono">
                                {flag.snippet_a
                                  ? `"${flag.snippet_a}…"`
                                  : "No preview"}
                              </p>
                            </div>
                            <div className="bg-white/[0.02] rounded-xl p-3">
                              <p className="text-[9px] text-white/25 uppercase tracking-wider font-bold mb-1.5 flex items-center gap-1">
                                <Users className="h-2.5 w-2.5" />
                                {flag.studentB}
                              </p>
                              <p className="text-[11px] text-white/40 leading-relaxed font-mono">
                                {flag.snippet_b
                                  ? `"${flag.snippet_b}…"`
                                  : "No preview"}
                              </p>
                            </div>
                          </div>
                        )}

                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Zap className="h-3 w-3 text-white/15" />
                            <span className="text-[10px] text-white/20">
                              Cosine similarity via llama-text-embed-v2
                            </span>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              // Could link to grade detail
                            }}
                            className="flex items-center gap-1 text-[10px] text-cyan-400/60 hover:text-cyan-400 transition-colors font-bold uppercase tracking-wider"
                          >
                            <Eye className="h-3 w-3" /> Investigate
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Hover overlay */}
                <div className="absolute inset-0 bg-rose-500 opacity-0 group-hover:opacity-[0.03] transition-opacity rounded-2xl pointer-events-none" />
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* ── Footer ── */}
      <div className="mt-6 flex items-center justify-center gap-2 text-[10px] text-white/10 tracking-wide relative z-10">
        <Cpu className="h-3 w-3" />
        Pinecone Vector DB · Cosine Similarity · llama-text-embed-v2
      </div>
    </div>
  );
};

export default SimilaritySentinel;
