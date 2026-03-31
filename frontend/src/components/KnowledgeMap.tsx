"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  Brain,
  AlertTriangle,
  Trophy,
  BookOpen,
  Loader2,
  TrendingDown,
  TrendingUp,
  Lightbulb,
  BarChart3,
  RefreshCcw,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface GapItem {
  concept: string;
  reason: string;
  affected_pct: number;
  severity: "Critical" | "Moderate" | "Minor";
  example_mistake: string;
}

interface StrengthItem {
  concept: string;
  mastery_pct: number;
  evidence: string;
}

interface ProficiencyItem {
  concept: string;
  value: number;
}

interface KnowledgeMapData {
  gaps: GapItem[];
  strengths: StrengthItem[];
  proficiency: ProficiencyItem[];
  remediation: string;
  summary: string;
  total_scripts: number;
  avg_score: number;
  subject?: string;
  title?: string;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const severityColors: Record<string, string> = {
  Critical: "border-red-500/30 bg-red-500/10 text-red-400",
  Moderate: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  Minor: "border-blue-500/30 bg-blue-500/10 text-blue-400",
};

const severityIcons: Record<string, string> = {
  Critical: "🔴",
  Moderate: "🟡",
  Minor: "🟢",
};

/* ------------------------------------------------------------------ */
/*  Custom Tooltip                                                     */
/* ------------------------------------------------------------------ */

const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: Array<{ payload: ProficiencyItem }> }) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="rounded-lg border border-white/10 bg-slate-900/95 backdrop-blur-xl px-3 py-2 shadow-xl">
        <p className="text-xs font-medium text-white/80">{data.concept}</p>
        <p className={`text-sm font-bold ${data.value >= 70 ? "text-emerald-400" : data.value >= 40 ? "text-amber-400" : "text-red-400"}`}>
          {data.value}% Proficiency
        </p>
      </div>
    );
  }
  return null;
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

interface KnowledgeMapProps {
  assessmentId: string;
  authFetch: (url: string, options?: RequestInit) => Promise<Response>;
}

export default function KnowledgeMap({ assessmentId, authFetch }: KnowledgeMapProps) {
  const [data, setData] = useState<KnowledgeMapData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedGap, setExpandedGap] = useState<number | null>(null);

  const fetchKnowledgeMap = useCallback(async () => {
    if (!assessmentId) return;
    setLoading(true);
    setError(null);

    try {
      const res = await authFetch(`${API_URL}/api/knowledge-map/${assessmentId}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed to load" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const result = await res.json();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [assessmentId, authFetch]);

  useEffect(() => {
    if (assessmentId) {
      fetchKnowledgeMap();
    }
  }, [assessmentId, fetchKnowledgeMap]);

  /* ---------- Loading state ---------- */
  if (loading) {
    return (
      <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
        <CardContent className="flex flex-col items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-blue-400 animate-spin mb-4" />
          <p className="text-sm text-white/40">Generating Semantic Gap Analysis…</p>
          <p className="text-[10px] text-white/20 mt-1">Analyzing {assessmentId ? "all student feedback" : "…"} with Gemini</p>
        </CardContent>
      </Card>
    );
  }

  /* ---------- Error state ---------- */
  if (error) {
    return (
      <Card className="rounded-2xl border border-red-500/20 bg-red-500/5 backdrop-blur-2xl">
        <CardContent className="flex flex-col items-center justify-center py-12">
          <AlertTriangle className="h-8 w-8 text-red-400 mb-3" />
          <p className="text-sm text-red-400">{error}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchKnowledgeMap}
            className="mt-4 border-red-500/20 text-red-400 hover:bg-red-500/10"
          >
            <RefreshCcw className="mr-1.5 h-3.5 w-3.5" /> Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  /* ---------- Empty / no assessment selected ---------- */
  if (!data || !assessmentId) {
    return (
      <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
        <CardContent className="flex flex-col items-center justify-center py-16 text-white/20">
          <Brain className="h-12 w-12 mb-4 opacity-30" />
          <p className="text-sm">Select an assessment to generate the Knowledge Map</p>
        </CardContent>
      </Card>
    );
  }

  /* ---------- No data ---------- */
  if (data.total_scripts === 0) {
    return (
      <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
        <CardContent className="flex flex-col items-center justify-center py-16 text-white/20">
          <BarChart3 className="h-12 w-12 mb-4 opacity-30" />
          <p className="text-sm">No graded scripts found for this assessment</p>
          <p className="text-[10px] mt-1">Grade some scripts first to generate analysis</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* ========== HEADER CARD ========== */}
      <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-hidden">
        <div className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
            <Brain className="h-4 w-4 text-purple-400" />
            Class Semantic Gap Analysis
          </h3>
          <div className="flex items-center gap-3">
            <Badge className="text-[10px] border-purple-500/30 bg-purple-500/10 text-purple-400">
              {data.total_scripts} scripts analyzed
            </Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchKnowledgeMap}
              disabled={loading}
              className="h-7 text-[10px] border-white/10 text-white/40 hover:bg-white/5"
            >
              <RefreshCcw className="h-3 w-3 mr-1" /> Refresh
            </Button>
          </div>
        </div>

        <CardContent className="p-6">
          {/* Summary */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 p-4 rounded-xl border border-blue-500/20 bg-blue-500/5"
          >
            <p className="text-xs text-blue-400 uppercase font-bold tracking-wider mb-1 flex items-center gap-1.5">
              <Lightbulb className="h-3.5 w-3.5" /> Executive Summary
            </p>
            <p className="text-sm text-white/70 leading-relaxed">{data.summary}</p>
          </motion.div>

          {/* Radar Chart */}
          {data.proficiency.length > 0 && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.2 }}
              className="mb-6"
            >
              <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-4 flex items-center gap-2">
                <BarChart3 className="h-3.5 w-3.5 text-cyan-400" />
                Concept Proficiency Radar
              </h4>
              <div className="h-[320px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="75%" data={data.proficiency}>
                    <PolarGrid stroke="#334155" strokeDasharray="3 3" />
                    <PolarAngleAxis
                      dataKey="concept"
                      tick={{ fill: "#94a3b8", fontSize: 11 }}
                      tickLine={false}
                    />
                    <PolarRadiusAxis
                      angle={30}
                      domain={[0, 100]}
                      tick={{ fill: "#475569", fontSize: 9 }}
                      tickCount={5}
                    />
                    <Radar
                      name="Class Proficiency"
                      dataKey="value"
                      stroke="#3b82f6"
                      fill="#3b82f6"
                      fillOpacity={0.25}
                      strokeWidth={2}
                    />
                    <Tooltip content={<CustomTooltip />} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>
          )}
        </CardContent>
      </Card>

      {/* ========== GAPS & STRENGTHS GRID ========== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Knowledge Gaps */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
        >
          <Card className="rounded-2xl border border-red-500/10 bg-white/5 backdrop-blur-2xl overflow-hidden h-full">
            <div className="border-b border-white/10 px-6 py-4">
              <h3 className="text-sm font-semibold text-red-400 flex items-center gap-2">
                <TrendingDown className="h-4 w-4" />
                Knowledge Gaps
              </h3>
              <p className="text-[10px] text-white/30 mt-0.5">Concepts requiring remediation</p>
            </div>
            <ScrollArea className="max-h-[400px]">
              <div className="p-4 space-y-3">
                {data.gaps.length === 0 ? (
                  <p className="text-xs text-white/20 text-center py-8">No significant gaps detected</p>
                ) : (
                  <AnimatePresence>
                    {data.gaps.map((gap, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.05 * i }}
                        className="rounded-xl border border-white/5 bg-white/[0.02] overflow-hidden"
                      >
                        <button
                          onClick={() => setExpandedGap(expandedGap === i ? null : i)}
                          className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-white/[0.02] transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            <span className="text-sm">{severityIcons[gap.severity] || "⚪"}</span>
                            <div>
                              <p className="text-sm text-white/70 font-medium">{gap.concept}</p>
                              <p className="text-[10px] text-white/30">{gap.affected_pct}% of students affected</p>
                            </div>
                          </div>
                          <Badge className={`text-[9px] ${severityColors[gap.severity] || severityColors.Minor}`}>
                            {gap.severity}
                          </Badge>
                        </button>
                        <AnimatePresence>
                          {expandedGap === i && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              className="border-t border-white/5"
                            >
                              <div className="px-4 py-3 space-y-2">
                                <div>
                                  <p className="text-[10px] text-white/30 uppercase">Why Students Struggled</p>
                                  <p className="text-xs text-white/50">{gap.reason}</p>
                                </div>
                                <div>
                                  <p className="text-[10px] text-white/30 uppercase">Example Mistake</p>
                                  <p className="text-xs text-amber-400/80 italic">&ldquo;{gap.example_mistake}&rdquo;</p>
                                </div>
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                )}
              </div>
            </ScrollArea>
          </Card>
        </motion.div>

        {/* Strengths */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
        >
          <Card className="rounded-2xl border border-emerald-500/10 bg-white/5 backdrop-blur-2xl overflow-hidden h-full">
            <div className="border-b border-white/10 px-6 py-4">
              <h3 className="text-sm font-semibold text-emerald-400 flex items-center gap-2">
                <TrendingUp className="h-4 w-4" />
                Class Strengths
              </h3>
              <p className="text-[10px] text-white/30 mt-0.5">Concepts the class has mastered</p>
            </div>
            <ScrollArea className="max-h-[400px]">
              <div className="p-4 space-y-3">
                {data.strengths.length === 0 ? (
                  <p className="text-xs text-white/20 text-center py-8">No clear strengths identified yet</p>
                ) : (
                  data.strengths.map((str, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.05 * i }}
                      className="rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3"
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <p className="text-sm text-white/70 font-medium flex items-center gap-2">
                          <Trophy className="h-3.5 w-3.5 text-emerald-400" />
                          {str.concept}
                        </p>
                        <span className="text-sm font-bold text-emerald-400">{str.mastery_pct}%</span>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-white/5 overflow-hidden mb-2">
                        <motion.div
                          className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full"
                          initial={{ width: 0 }}
                          animate={{ width: `${str.mastery_pct}%` }}
                          transition={{ duration: 0.8, delay: 0.1 * i }}
                        />
                      </div>
                      <p className="text-[10px] text-white/30">{str.evidence}</p>
                    </motion.div>
                  ))
                )}
              </div>
            </ScrollArea>
          </Card>
        </motion.div>
      </div>

      {/* ========== REMEDIATION PLAN ========== */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
      >
        <Card className="rounded-2xl border border-amber-500/10 bg-white/5 backdrop-blur-2xl overflow-hidden">
          <CardContent className="p-6">
            <div className="flex items-start gap-3">
              <div className="h-10 w-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
                <BookOpen className="h-5 w-5 text-amber-400" />
              </div>
              <div>
                <p className="text-xs text-amber-400 uppercase font-bold tracking-wider mb-1">
                  Recommended Remediation Plan
                </p>
                <p className="text-sm text-white/60 leading-relaxed">{data.remediation}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
