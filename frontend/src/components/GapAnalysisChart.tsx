"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from "recharts";
import {
  BrainCircuit,
  Zap,
  Target,
  Loader2,
  AlertTriangle,
  TrendingDown,
  TrendingUp,
  RefreshCcw,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

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

interface GapAnalysisData {
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

interface RadarDataPoint {
  subject: string;
  standard: number;
  classAvg: number;
  gap: number;
}

interface GapAnalysisChartProps {
  assessmentId?: string;
  authFetch?: (url: string, init?: RequestInit) => Promise<Response>;
  /** Supply static data directly (bypasses API fetch) */
  data?: GapAnalysisData;
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

/* ------------------------------------------------------------------ */
/*  Custom Tooltip                                                     */
/* ------------------------------------------------------------------ */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const classVal = payload.find(
      (p: { dataKey: string }) => p.dataKey === "classAvg",
    )?.value as number | undefined;
    const stdVal = payload.find(
      (p: { dataKey: string }) => p.dataKey === "standard",
    )?.value as number | undefined;
    const gapVal =
      stdVal !== undefined && classVal !== undefined
        ? stdVal - classVal
        : null;

    return (
      <div className="bg-slate-950/95 backdrop-blur-xl p-4 rounded-xl border border-white/10 shadow-2xl min-w-[180px]">
        <p className="text-sm font-bold text-white mb-2">{label}</p>
        <div className="space-y-1">
          <p className="text-xs text-emerald-400">
            ✅ Standard: {stdVal ?? "—"}%
          </p>
          <p className="text-xs text-rose-400">
            ⚠️ Class Avg: {classVal ?? "—"}%
          </p>
        </div>
        {gapVal !== null && (
          <p className="text-[10px] mt-2 text-white/50 bg-rose-500/10 px-2 py-0.5 rounded-full inline-block">
            Delta (Gap): {gapVal}%
          </p>
        )}
      </div>
    );
  }
  return null;
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export const GapAnalysisChart: React.FC<GapAnalysisChartProps> = ({
  assessmentId,
  authFetch,
  data: externalData,
}) => {
  const [mapData, setMapData] = useState<GapAnalysisData | null>(
    externalData ?? null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* ---------- Fetch from backend ---------- */
  const fetchMap = useCallback(async () => {
    if (!assessmentId) return;
    setLoading(true);
    setError(null);
    try {
      const fetcher = authFetch ?? fetch;
      const res = await fetcher(
        `${API_URL}/api/knowledge-map/${assessmentId}`,
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: "Server error" }));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const json = await res.json();
      setMapData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [assessmentId, authFetch]);

  useEffect(() => {
    if (!externalData && assessmentId) fetchMap();
  }, [externalData, assessmentId, fetchMap]);

  useEffect(() => {
    if (externalData) setMapData(externalData);
  }, [externalData]);

  /* ---------- Transform proficiency → radar data ---------- */
  const radarData: RadarDataPoint[] = (mapData?.proficiency ?? []).map(
    (p) => ({
      subject:
        p.concept.length > 16 ? p.concept.slice(0, 14) + "…" : p.concept,
      standard: 90, // curriculum benchmark (could be dynamic per rubric)
      classAvg: p.value,
      gap: Math.max(90 - p.value, 0),
    }),
  );

  // Sort by biggest gap for priority insights
  const sortedByGap = [...radarData].sort((a, b) => b.gap - a.gap);
  const topGap = sortedByGap[0];

  // Severity-sorted gaps
  const sortedGaps = [...(mapData?.gaps ?? [])].sort((a, b) => {
    const order = { Critical: 0, Moderate: 1, Minor: 2 };
    return (order[a.severity] ?? 3) - (order[b.severity] ?? 3);
  });

  /* ---------- Loading / empty states ---------- */
  if (!assessmentId && !externalData) {
    return (
      <div className="bg-slate-900/50 border border-white/10 p-12 rounded-2xl flex flex-col items-center justify-center text-white/20">
        <BrainCircuit className="h-12 w-12 mb-4 opacity-30" />
        <p className="text-sm">Select an assessment to view the Semantic Knowledge Map</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="bg-slate-900/50 border border-white/10 p-12 rounded-2xl flex items-center justify-center">
        <Loader2 className="h-6 w-6 text-amber-400 animate-spin mr-3" />
        <span className="text-sm text-white/40">Generating semantic analysis…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-slate-900/50 border border-white/10 p-8 rounded-2xl flex flex-col items-center text-center gap-3">
        <AlertTriangle className="h-8 w-8 text-amber-400/50" />
        <p className="text-sm text-white/40">{error}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchMap}
          className="border-white/10 text-white/50 hover:bg-white/5 text-xs"
        >
          <RefreshCcw className="h-3 w-3 mr-1.5" /> Retry
        </Button>
      </div>
    );
  }

  if (!mapData || radarData.length === 0) {
    return (
      <div className="bg-slate-900/50 border border-white/10 p-12 rounded-2xl flex flex-col items-center justify-center text-white/20">
        <BrainCircuit className="h-10 w-10 mb-3 opacity-30" />
        <p className="text-sm">No proficiency data available yet</p>
        <p className="text-[10px] text-white/10 mt-1">
          Grade more scripts to generate the knowledge map
        </p>
      </div>
    );
  }

  /* ---------- Render ---------- */
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="bg-slate-900 border border-white/10 p-6 rounded-2xl shadow-xl flex flex-col"
    >
      {/* ── Chart Header ── */}
      <div className="flex flex-wrap items-center justify-between mb-6 gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl">
            <BrainCircuit className="w-6 h-6 text-amber-400" />
          </div>
          <div>
            <h3 className="text-lg font-extrabold text-white tracking-tight">
              Semantic Knowledge Map
            </h3>
            <p className="text-xs text-slate-400">
              {mapData.subject
                ? `${mapData.subject} · ${mapData.title ?? ""}`
                : "Class Proficiency vs. Curriculum Benchmarks"}
            </p>
          </div>
        </div>

        {/* Key Insights Badge */}
        <div className="flex flex-wrap gap-2">
          {topGap && topGap.gap > 0 && (
            <div className="flex items-center gap-1.5 text-rose-400 font-bold px-3 py-1.5 bg-rose-500/10 rounded-full text-xs border border-rose-500/20">
              <Zap className="w-3.5 h-3.5" />
              Gap: {topGap.subject} (−{topGap.gap}%)
            </div>
          )}
          <div className="flex items-center gap-1.5 text-emerald-400 font-semibold px-3 py-1.5 bg-emerald-500/10 rounded-full text-xs border border-emerald-500/20">
            <TrendingUp className="w-3.5 h-3.5" />
            Avg: {mapData.avg_score}/10
          </div>
          <Badge className="bg-white/5 border-white/10 text-white/40 text-[10px]">
            {mapData.total_scripts} scripts
          </Badge>
        </div>
      </div>

      {/* ── The Radar Chart (Delta Shadow) ── */}
      <div className="w-full h-[360px] mb-2">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
            <PolarGrid stroke="#FFFFFF15" />
            <PolarAngleAxis
              dataKey="subject"
              tick={{
                fill: "#94a3b8",
                fontSize: 11,
                fontWeight: "bold",
              }}
              tickLine={false}
            />
            <PolarRadiusAxis
              angle={30}
              domain={[0, 100]}
              tick={{ fill: "#475569", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />

            <Tooltip content={<CustomTooltip />} cursor={false} />

            {/* Layer 1: Standard Map (The Target — green dotted) */}
            <Radar
              name="Curriculum Standard"
              dataKey="standard"
              stroke="#10b981"
              fill="#10b981"
              fillOpacity={0.08}
              strokeWidth={1.5}
              strokeDasharray="4 4"
            />

            {/* Layer 2: Delta Shadow (gap fill — rose transparent) */}
            <Radar
              name="The Gap"
              dataKey="classAvg"
              stroke="transparent"
              fill="#ef4444"
              fillOpacity={0.15}
              legendType="none"
            />

            {/* Layer 3: Class Average (actual performance — rose solid) */}
            <Radar
              name="Class Avg Performance"
              dataKey="classAvg"
              stroke="#f43f5e"
              fill="#f43f5e"
              fillOpacity={0.4}
              strokeWidth={2}
              activeDot={{
                r: 6,
                stroke: "white",
                fill: "#f43f5e",
                strokeWidth: 3,
              }}
            />

            <Legend
              iconType="circle"
              wrapperStyle={{
                fontSize: "11px",
                color: "#cbd5e1",
                paddingTop: "20px",
              }}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* ── Knowledge Gaps List ── */}
      {sortedGaps.length > 0 && (
        <div className="mb-5">
          <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
            <TrendingDown className="h-3.5 w-3.5 text-rose-400" />
            Knowledge Gaps
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <AnimatePresence>
              {sortedGaps.map((gap, i) => (
                <motion.div
                  key={gap.concept}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.05 * i }}
                  className={`rounded-xl border px-4 py-3 ${severityColors[gap.severity] || severityColors.Minor}`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-bold">{gap.concept}</span>
                    <Badge
                      className={`text-[9px] ${severityColors[gap.severity]}`}
                    >
                      {gap.severity} · {gap.affected_pct}%
                    </Badge>
                  </div>
                  <p className="text-[11px] text-white/40 leading-relaxed">
                    {gap.reason}
                  </p>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* ── Strengths ── */}
      {mapData.strengths.length > 0 && (
        <div className="mb-5">
          <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
            <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
            Class Strengths
          </h4>
          <div className="flex flex-wrap gap-2">
            {mapData.strengths.map((s) => (
              <span
                key={s.concept}
                className="px-3 py-1.5 rounded-full text-xs font-semibold border border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
              >
                {s.concept}{" "}
                <span className="text-emerald-400/50">({s.mastery_pct}%)</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Actionable Insight Footer ── */}
      <div className="mt-auto flex items-start gap-4 p-4 bg-black/40 rounded-xl border border-white/5">
        <Target className="w-10 h-10 text-emerald-400 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-bold text-white">
            {topGap
              ? `Focus Area: ${topGap.subject}`
              : "All concepts within threshold"}
          </p>
          <p className="text-xs text-slate-300 mt-1 leading-relaxed">
            {mapData.remediation ||
              "No specific remediation needed — class performance is on track."}
          </p>
        </div>
      </div>
    </motion.div>
  );
};

export default GapAnalysisChart;
