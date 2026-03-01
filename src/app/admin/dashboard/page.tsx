"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Shield,
  FileText,
  AlertTriangle,
  TrendingUp,
  Users,
  Activity,
  RotateCcw,
  Loader2,
  Gavel,
  ArrowLeft,
  Eye,
  Clock,
  CheckCircle2,
  Scale,
  ScanLine,
  BarChart3,
  Lock,
  FileSpreadsheet,
  ShieldCheck,
  Download,
  Hash,
  ChevronDown,
  AlertCircle,
  LogIn,
  ShieldAlert,
} from "lucide-react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { UserBadge } from "@/components/UserBadge";
import { useAuth } from "@/lib/auth-context";
import { useAuthFetch } from "@/lib/use-auth-fetch";
import KnowledgeMap from "@/components/KnowledgeMap";
import DiagramValidator from "@/components/DiagramValidator";
import { GapAnalysisChart } from "@/components/GapAnalysisChart";
import { FinalizeGrades } from "@/components/FinalizeGrades";
import { SimilaritySentinel } from "@/components/SimilaritySentinel";
import { InstitutionalLedger } from "@/components/InstitutionalLedger";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface AdminStats {
  total_scripts: number;
  total_students: number;
  status_breakdown: Record<string, number>;
  pending_appeals: number;
  flagged_count: number;
  avg_score: number;
  avg_confidence: number;
  audited_count: number;
  audit_overturn_rate: number;
}

interface AuditLog {
  id: string;
  grade_id: string;
  action: string;
  changed_by: string;
  old_score: number | null;
  new_score: number | null;
  reason: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

interface RecentGrade {
  id: string;
  ai_score: number;
  confidence: number;
  prof_status: string;
  is_flagged: boolean;
  graded_at: string;
  reviewed_at: string | null;
  students: { reg_no: string; name: string };
  assessments: { subject: string; title: string };
}

interface Assessment {
  id: string;
  subject: string;
  title: string;
  is_locked?: boolean;
  locked_at?: string;
  locked_by?: string;
}

interface LockStatus {
  id: string;
  subject: string;
  title: string;
  is_locked: boolean;
  locked_at: string | null;
  locked_by: string | null;
  ledger_hashes: {
    filename: string;
    sha256_hash: string;
    record_count: number;
    format: string;
    created_at: string;
  }[];
}

interface LedgerPreviewRow {
  Sl_No: number;
  Register_Number: string;
  Student_Name: string;
  Subject: string;
  Internal_Marks: number;
  Confidence: number;
  Verification_Status: string;
  Flagged: boolean;
}

interface LedgerPreview {
  total_records: number;
  preview_count?: number;
  columns: string[];
  preview: LedgerPreviewRow[];
  rows?: LedgerPreviewRow[];
  assessment?: Assessment | null;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const actionColors: Record<string, string> = {
  APPROVE: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  OVERRIDE: "text-purple-400 bg-purple-500/10 border-purple-500/20",
  APPEAL_SUBMIT: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  AUDIT_ADJUST: "text-teal-400 bg-teal-500/10 border-teal-500/20",
  AUDIT_UPHELD: "text-blue-400 bg-blue-500/10 border-blue-500/20",
  FINALIZE_LOCK: "text-red-400 bg-red-500/10 border-red-500/20",
  LEDGER_EXPORT: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
};

const statusColors: Record<string, string> = {
  Pending: "border-blue-500/30 bg-blue-500/10 text-blue-400",
  Approved: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  Flagged: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  Overridden: "border-purple-500/30 bg-purple-500/10 text-purple-400",
  Audited: "border-teal-500/30 bg-teal-500/10 text-teal-400",
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function AdminDashboard() {
  const router = useRouter();
  const { user } = useAuth();
  const authFetch = useAuthFetch();

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [recentGrades, setRecentGrades] = useState<RecentGrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "logs" | "activity" | "finalize" | "intelligence" | "diagram" | "seal" | "sentinel" | "ledger">("overview");

  // Finalize & Lock state
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<string>("");
  const [lockStatus, setLockStatus] = useState<LockStatus | null>(null);
  const [ledgerPreview, setLedgerPreview] = useState<LedgerPreview | null>(null);
  const [locking, setLocking] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [showAssessmentDropdown, setShowAssessmentDropdown] = useState(false);

  // Integrity verification state
  const [verifyFile, setVerifyFile] = useState<File | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{
    status: "AUTHENTIC" | "TAMPERED" | "ERROR";
    message: string;
    computed_hash: string;
    original_filename?: string;
    generated_at?: string;
  } | null>(null);
  const verifyInputRef = React.useRef<HTMLInputElement>(null);

  /* ---------- Fetch all data ---------- */
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, activityRes, assessmentsRes] = await Promise.all([
        authFetch(`${API_URL}/api/admin/stats`),
        authFetch(`${API_URL}/api/admin/recent-activity?limit=30`),
        authFetch(`${API_URL}/api/assessments`),
      ]);

      if (statsRes.ok) setStats(await statsRes.json());
      if (activityRes.ok) setRecentGrades(await activityRes.json());
      if (assessmentsRes.ok) setAssessments(await assessmentsRes.json());
    } catch (err) {
      console.error("Failed to fetch admin data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Lazy load audit logs only when logs tab is active
  const fetchAuditLogs = useCallback(async () => {
    setLoading(true);
    try {
      const logsRes = await authFetch(`${API_URL}/api/audit-logs?limit=50`);
      if (logsRes.ok) setAuditLogs(await logsRes.json());
    } catch (err) {
      console.error("Failed to fetch audit logs:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  useEffect(() => {
    if (activeTab === "logs") {
      fetchAuditLogs();
    }
  }, [activeTab, fetchAuditLogs]);

  /* ---------- Finalize & Lock Helpers ---------- */
  const fetchLockStatus = useCallback(async (assessmentId: string) => {
    if (!assessmentId) return;
    try {
      const res = await authFetch(`${API_URL}/api/assessments/${assessmentId}/lock-status`);
      if (res.ok) setLockStatus(await res.json());
    } catch (err) {
      console.error("Failed to fetch lock status:", err);
    }
  }, []);

  const fetchLedgerPreview = useCallback(async (assessmentId: string) => {
    if (!assessmentId) return;
    setPreviewLoading(true);
    try {
      const res = await authFetch(`${API_URL}/api/ledger/${assessmentId}/preview`);
      if (res.ok) setLedgerPreview(await res.json());
    } catch (err) {
      console.error("Failed to fetch ledger preview:", err);
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedAssessmentId) {
      fetchLockStatus(selectedAssessmentId);
      fetchLedgerPreview(selectedAssessmentId);
    } else {
      setLockStatus(null);
      setLedgerPreview(null);
    }
  }, [selectedAssessmentId, fetchLockStatus, fetchLedgerPreview]);

  const handleFinalizeLock = async () => {
    if (!selectedAssessmentId || locking) return;
    if (!confirm("⚠️ This will PERMANENTLY LOCK all marks for this assessment. Grades cannot be edited after this. Continue?")) return;
    setLocking(true);
    try {
      const res = await authFetch(`${API_URL}/api/assessments/${selectedAssessmentId}/lock?fmt=csv`, { method: "POST" });
      if (res.ok) {
        await fetchLockStatus(selectedAssessmentId);
        await fetchAll();
      }
    } catch (err) {
      console.error("Lock failed:", err);
    } finally {
      setLocking(false);
    }
  };

  const handleDownloadLedger = async (fmt: "csv" | "xlsx") => {
    if (!selectedAssessmentId) return;
    setDownloading(true);
    try {
      const res = await authFetch(`${API_URL}/api/ledger/${selectedAssessmentId}/download?fmt=${fmt}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `ledger_${selectedAssessmentId.slice(0, 8)}.${fmt}`;
        a.click();
        URL.revokeObjectURL(url);
        await fetchLockStatus(selectedAssessmentId);
      }
    } catch (err) {
      console.error("Download failed:", err);
    } finally {
      setDownloading(false);
    }
  };

  /* ---------- Integrity Verify ---------- */
  const handleVerifyUpload = async () => {
    if (!selectedAssessmentId || !verifyFile) return;
    setVerifying(true);
    setVerifyResult(null);
    try {
      const formData = new FormData();
      formData.append("file", verifyFile);
      const res = await authFetch(
        `${API_URL}/api/ledger/${selectedAssessmentId}/verify`,
        { method: "POST", body: formData },
      );
      if (res.ok) {
        setVerifyResult(await res.json());
      } else {
        const body = await res.json().catch(() => ({ detail: "Verification failed" }));
        setVerifyResult({
          status: "ERROR",
          message: body.detail || "Server error",
          computed_hash: "—",
        });
      }
    } catch {
      setVerifyResult({
        status: "ERROR",
        message: "Network error — could not reach server.",
        computed_hash: "—",
      });
    } finally {
      setVerifying(false);
    }
  };

  /* ---------- Loading ---------- */
  if (loading && !stats) {
    return (
      <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0b1120] to-black flex items-center justify-center">
        <Loader2 className="h-8 w-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  const s = stats || {
    total_scripts: 0,
    total_students: 0,
    status_breakdown: {},
    pending_appeals: 0,
    flagged_count: 0,
    avg_score: 0,
    avg_confidence: 0,
    audited_count: 0,
    audit_overturn_rate: 0,
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0b1120] to-black text-white font-sans">
      <div className="mx-auto max-w-[1440px] px-6 py-6">
        {/* ========== TOP BAR ========== */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/")}
              className="border-white/10 bg-white/5 text-white/60 hover:bg-white/10 backdrop-blur-md"
            >
              <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Staff Dashboard
            </Button>
            <div className="h-5 w-px bg-white/10" />
            <span className="text-xs text-white/30 flex items-center gap-1.5">
              <Shield className="h-3.5 w-3.5 text-red-400" />
              Controller of Examinations Portal
            </span>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={fetchAll}
            disabled={loading}
            className="border-white/10 bg-white/5 text-white/60 hover:bg-white/10 backdrop-blur-md"
          >
            {loading ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            )}
            Refresh
          </Button>
          {user ? (
            <UserBadge />
          ) : (
            <Link href="/login">
              <Button variant="outline" size="sm" className="border-white/10 bg-white/5 hover:bg-white/10 text-white/60 backdrop-blur-md text-xs">
                <LogIn className="mr-1.5 h-3.5 w-3.5" /> Sign In
              </Button>
            </Link>
          )}
        </div>

        {/* ========== HEADER ========== */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-10"
        >
          <h1 className="text-4xl font-black tracking-tight bg-gradient-to-r from-red-400 via-orange-300 to-amber-400 bg-clip-text text-transparent">
            Control Tower
          </h1>
          <p className="text-white/40 mt-2">
            Institutional oversight · Tamper-proof audit trail · Real-time analytics
          </p>
        </motion.div>

        {/* ========== STAT CARDS ========== */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
          {[
            {
              label: "Total Scripts",
              value: s.total_scripts.toLocaleString(),
              icon: <FileText className="h-4 w-4 text-blue-400" />,
              color: "border-blue-500/20",
            },
            {
              label: "Students",
              value: s.total_students.toLocaleString(),
              icon: <Users className="h-4 w-4 text-indigo-400" />,
              color: "border-indigo-500/20",
            },
            {
              label: "Avg Score",
              value: `${s.avg_score}/10`,
              icon: <TrendingUp className="h-4 w-4 text-emerald-400" />,
              color: "border-emerald-500/20",
            },
            {
              label: "Avg Confidence",
              value: `${Math.round(s.avg_confidence * 100)}%`,
              icon: <BarChart3 className="h-4 w-4 text-cyan-400" />,
              color: "border-cyan-500/20",
            },
            {
              label: "Pending Appeals",
              value: s.pending_appeals.toString(),
              icon: <AlertTriangle className="h-4 w-4 text-amber-400" />,
              color: "border-amber-500/20",
            },
            {
              label: "Audit Overturn",
              value: `${Math.round(s.audit_overturn_rate * 100)}%`,
              icon: <Scale className="h-4 w-4 text-teal-400" />,
              color: "border-teal-500/20",
            },
          ].map((stat, i) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 * i }}
            >
              <Card className={`rounded-xl border ${stat.color} bg-white/5 backdrop-blur-2xl overflow-hidden`}>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    {stat.icon}
                    <span className="text-[10px] uppercase tracking-wider text-white/30">{stat.label}</span>
                  </div>
                  <p className="text-2xl font-black text-white/90">{stat.value}</p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>

        {/* ========== STATUS BREAKDOWN BAR ========== */}
        {s.total_scripts > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="mb-8"
          >
            <Card className="rounded-xl border border-white/10 bg-white/5 backdrop-blur-2xl p-5">
              <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-4 flex items-center gap-2">
                <Activity className="h-3.5 w-3.5 text-blue-400" />
                Grading Pipeline Status
              </h3>
              <div className="flex h-4 rounded-full overflow-hidden bg-white/5">
                {Object.entries(s.status_breakdown).map(([status, count]) => {
                  const pct = (count / s.total_scripts) * 100;
                  const colorMap: Record<string, string> = {
                    Pending: "bg-blue-500",
                    Approved: "bg-emerald-500",
                    Flagged: "bg-amber-500",
                    Overridden: "bg-purple-500",
                    Audited: "bg-teal-500",
                  };
                  return (
                    <motion.div
                      key={status}
                      className={`${colorMap[status] || "bg-gray-500"} relative group`}
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 0.8, delay: 0.4 }}
                      title={`${status}: ${count} (${pct.toFixed(1)}%)`}
                    />
                  );
                })}
              </div>
              <div className="flex flex-wrap gap-4 mt-3">
                {Object.entries(s.status_breakdown).map(([status, count]) => (
                  <span key={status} className="text-xs text-white/40 flex items-center gap-1.5">
                    <span className={`h-2 w-2 rounded-full ${
                      status === "Pending" ? "bg-blue-500" :
                      status === "Approved" ? "bg-emerald-500" :
                      status === "Flagged" ? "bg-amber-500" :
                      status === "Overridden" ? "bg-purple-500" :
                      status === "Audited" ? "bg-teal-500" : "bg-gray-500"
                    }`} />
                    {status}: {count}
                  </span>
                ))}
              </div>
            </Card>
          </motion.div>
        )}

        {/* ========== TAB NAVIGATION ========== */}
        <div className="flex items-center gap-1 mb-6 border-b border-white/5 pb-px">
          {[
            { key: "overview" as const, label: "Recent Activity", icon: <Activity className="h-3.5 w-3.5" /> },
            { key: "intelligence" as const, label: "Intelligence Map", icon: <BarChart3 className="h-3.5 w-3.5" /> },
            { key: "diagram" as const, label: "Diagram Lab", icon: <ScanLine className="h-3.5 w-3.5" /> },
            { key: "logs" as const, label: "Audit Logs", icon: <Gavel className="h-3.5 w-3.5" /> },
            { key: "finalize" as const, label: "Finalize & Lock", icon: <Lock className="h-3.5 w-3.5" /> },
            { key: "seal" as const, label: "Digital Seal", icon: <Hash className="h-3.5 w-3.5" /> },
            { key: "sentinel" as const, label: "Sentinel", icon: <ShieldAlert className="h-3.5 w-3.5" /> },
            { key: "ledger" as const, label: "Export Ledger", icon: <FileSpreadsheet className="h-3.5 w-3.5" /> },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium rounded-t-lg transition-colors ${
                activeTab === tab.key
                  ? "bg-white/5 text-white/80 border-b-2 border-blue-400"
                  : "text-white/30 hover:text-white/50 hover:bg-white/[0.02]"
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* ========== TAB CONTENT ========== */}
        <AnimatePresence mode="wait">
          {activeTab === "overview" && (
            <motion.div
              key="overview"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-hidden">
                <div className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                    <ScanLine className="h-4 w-4 text-blue-400" />
                    Recent Grading Activity
                  </h3>
                  <span className="text-[10px] text-white/20">{recentGrades.length} records</span>
                </div>
                <ScrollArea className="max-h-[600px]">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/5 hover:bg-transparent">
                        <TableHead className="text-white/30">Student</TableHead>
                        <TableHead className="text-white/30">Subject</TableHead>
                        <TableHead className="text-white/30">Score</TableHead>
                        <TableHead className="text-white/30">Confidence</TableHead>
                        <TableHead className="text-white/30">Status</TableHead>
                        <TableHead className="text-white/30">Date</TableHead>
                        <TableHead className="text-white/30 text-right">Action</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {recentGrades.length === 0 ? (
                        <TableRow className="border-white/5">
                          <TableCell colSpan={7} className="text-center text-white/20 py-12">
                            No grading activity yet
                          </TableCell>
                        </TableRow>
                      ) : (
                        recentGrades.map((g, i) => (
                          <motion.tr
                            key={g.id}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.02 * i }}
                            className="border-white/5 hover:bg-white/[0.02] transition-colors"
                          >
                            <TableCell>
                              <div>
                                <p className="text-sm text-white/70 font-medium">{g.students?.name || "—"}</p>
                                <p className="text-[10px] text-white/30">{g.students?.reg_no}</p>
                              </div>
                            </TableCell>
                            <TableCell>
                              <p className="text-xs text-white/50">{g.assessments?.subject || "—"}</p>
                              <p className="text-[10px] text-white/20">{g.assessments?.title}</p>
                            </TableCell>
                            <TableCell>
                              <span className={`text-sm font-bold ${
                                g.ai_score >= 7 ? "text-emerald-400" : g.ai_score >= 4 ? "text-amber-400" : "text-red-400"
                              }`}>
                                {g.ai_score}<span className="text-white/20 font-normal">/10</span>
                              </span>
                            </TableCell>
                            <TableCell>
                              <span className="text-xs text-white/40">{Math.round(g.confidence * 100)}%</span>
                            </TableCell>
                            <TableCell>
                              <Badge className={`text-[10px] ${statusColors[g.prof_status] || statusColors.Pending}`}>
                                {g.prof_status}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <span className="text-[10px] text-white/30 flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {new Date(g.graded_at).toLocaleDateString("en-IN", {
                                  day: "numeric",
                                  month: "short",
                                })}
                              </span>
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => router.push(`/student/results/${g.id}`)}
                                className="h-7 text-[10px] border-white/10 text-white/40 hover:bg-white/5"
                              >
                                <Eye className="h-3 w-3 mr-1" />
                                View
                              </Button>
                            </TableCell>
                          </motion.tr>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </ScrollArea>
              </Card>
            </motion.div>
          )}

          {activeTab === "logs" && (
            <motion.div
              key="logs"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-hidden">
                <div className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                    <Gavel className="h-4 w-4 text-amber-400" />
                    System Change Logs (Tamper-Proof)
                  </h3>
                  <span className="text-[10px] text-white/20">{auditLogs.length} entries</span>
                </div>
                <ScrollArea className="max-h-[600px]">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-white/5 hover:bg-transparent">
                        <TableHead className="text-white/30">Timestamp</TableHead>
                        <TableHead className="text-white/30">User</TableHead>
                        <TableHead className="text-white/30">Action</TableHead>
                        <TableHead className="text-white/30">Old Mark</TableHead>
                        <TableHead className="text-white/30">New Mark</TableHead>
                        <TableHead className="text-white/30">Justification</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {auditLogs.length === 0 ? (
                        <TableRow className="border-white/5">
                          <TableCell colSpan={6} className="text-center text-white/20 py-12">
                            <div className="flex flex-col items-center gap-2">
                              <CheckCircle2 className="h-8 w-8 text-emerald-400/30" />
                              <p>No change logs recorded yet</p>
                              <p className="text-[10px] text-white/10">Logs appear when grades are approved, overridden, or audited</p>
                            </div>
                          </TableCell>
                        </TableRow>
                      ) : (
                        auditLogs.map((log, i) => (
                          <motion.tr
                            key={log.id}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.02 * i }}
                            className="border-white/5 hover:bg-white/[0.02] transition-colors"
                          >
                            <TableCell>
                              <span className="text-[10px] text-white/30 flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {new Date(log.created_at).toLocaleString("en-IN", {
                                  day: "numeric",
                                  month: "short",
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })}
                              </span>
                            </TableCell>
                            <TableCell>
                              <span className="text-xs text-white/50">{log.changed_by}</span>
                            </TableCell>
                            <TableCell>
                              <Badge className={`text-[10px] border ${actionColors[log.action] || "text-white/40 bg-white/5 border-white/10"}`}>
                                {log.action.replace(/_/g, " ")}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <span className="text-sm text-white/40 font-mono">
                                {log.old_score !== null ? log.old_score.toFixed(1) : "—"}
                              </span>
                            </TableCell>
                            <TableCell>
                              <span className={`text-sm font-mono font-semibold ${
                                log.new_score !== null && log.old_score !== null
                                  ? log.new_score > log.old_score
                                    ? "text-emerald-400"
                                    : log.new_score < log.old_score
                                      ? "text-red-400"
                                      : "text-white/50"
                                  : "text-white/40"
                              }`}>
                                {log.new_score !== null ? log.new_score.toFixed(1) : "—"}
                              </span>
                            </TableCell>
                            <TableCell>
                              <p className="text-xs text-white/40 max-w-[300px] truncate" title={log.reason}>
                                {log.reason}
                              </p>
                            </TableCell>
                          </motion.tr>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </ScrollArea>
              </Card>
            </motion.div>
          )}
          {activeTab === "intelligence" && (
            <motion.div
              key="intelligence"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-6"
            >
              {/* Assessment Selector for Intelligence Map */}
              <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-visible">
                <CardContent className="p-6">
                  <div className="relative">
                    <label className="text-[10px] uppercase tracking-wider text-white/30 mb-2 block">Select Assessment for Analysis</label>
                    <button
                      onClick={() => setShowAssessmentDropdown(!showAssessmentDropdown)}
                      className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-white/10 bg-white/5 text-sm text-white/70 hover:border-white/20 transition-colors"
                    >
                      <span>
                        {selectedAssessmentId
                          ? (() => {
                              const a = assessments.find((x) => x.id === selectedAssessmentId);
                              return a ? `${a.subject} — ${a.title}` : selectedAssessmentId;
                            })()
                          : "Select an assessment…"}
                      </span>
                      <ChevronDown className={`h-4 w-4 text-white/30 transition-transform ${showAssessmentDropdown ? "rotate-180" : ""}`} />
                    </button>
                    {showAssessmentDropdown && (
                      <div className="absolute z-50 mt-2 w-full rounded-xl border border-white/10 bg-slate-900/95 backdrop-blur-2xl shadow-2xl max-h-60 overflow-y-auto">
                        {assessments.length === 0 ? (
                          <div className="px-4 py-3 text-xs text-white/30">No assessments found</div>
                        ) : (
                          assessments.map((a) => (
                            <button
                              key={a.id}
                              onClick={() => {
                                setSelectedAssessmentId(a.id);
                                setShowAssessmentDropdown(false);
                              }}
                              className={`w-full text-left px-4 py-3 text-sm hover:bg-white/5 transition-colors ${selectedAssessmentId === a.id ? "bg-white/5 text-purple-400" : "text-white/60"}`}
                            >
                              <p className="font-medium">{a.subject}</p>
                              <p className="text-[10px] text-white/30">{a.title}</p>
                            </button>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Knowledge Map Component */}
              <KnowledgeMap assessmentId={selectedAssessmentId} authFetch={authFetch} />

              {/* Gap Analysis Radar Chart — Delta Shadow */}
              <GapAnalysisChart assessmentId={selectedAssessmentId} authFetch={authFetch} />
            </motion.div>
          )}

          {activeTab === "diagram" && (
            <motion.div
              key="diagram"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              <DiagramValidator />
            </motion.div>
          )}

          {activeTab === "finalize" && (
            <motion.div
              key="finalize"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-6"
            >
              {/* Assessment Selector */}
              <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-visible">
                <div className="border-b border-white/10 px-6 py-4">
                  <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                    <FileSpreadsheet className="h-4 w-4 text-cyan-400" />
                    ERP Export · Digital Seal · Finalize Marks
                  </h3>
                  <p className="text-[10px] text-white/30 mt-1">Select an assessment to preview, export, and lock the official marks ledger</p>
                </div>
                <CardContent className="p-6">
                  {/* Custom Dropdown */}
                  <div className="relative mb-6">
                    <label className="text-[10px] uppercase tracking-wider text-white/30 mb-2 block">Assessment</label>
                    <button
                      onClick={() => setShowAssessmentDropdown(!showAssessmentDropdown)}
                      className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-white/10 bg-white/5 text-sm text-white/70 hover:border-white/20 transition-colors"
                    >
                      <span>
                        {selectedAssessmentId
                          ? (() => {
                              const a = assessments.find((x) => x.id === selectedAssessmentId);
                              return a ? `${a.subject} — ${a.title}` : selectedAssessmentId;
                            })()
                          : "Select an assessment…"}
                      </span>
                      <ChevronDown className={`h-4 w-4 text-white/30 transition-transform ${showAssessmentDropdown ? "rotate-180" : ""}`} />
                    </button>
                    {showAssessmentDropdown && (
                      <div className="absolute z-50 mt-2 w-full rounded-xl border border-white/10 bg-slate-900/95 backdrop-blur-2xl shadow-2xl max-h-60 overflow-y-auto">
                        {assessments.length === 0 ? (
                          <div className="px-4 py-3 text-xs text-white/30">No assessments found</div>
                        ) : (
                          assessments.map((a) => (
                            <button
                              key={a.id}
                              onClick={() => {
                                setSelectedAssessmentId(a.id);
                                setShowAssessmentDropdown(false);
                              }}
                              className={`w-full text-left px-4 py-3 text-sm hover:bg-white/5 transition-colors flex items-center justify-between ${
                                selectedAssessmentId === a.id ? "bg-white/5 text-cyan-400" : "text-white/60"
                              }`}
                            >
                              <div>
                                <p className="font-medium">{a.subject}</p>
                                <p className="text-[10px] text-white/30">{a.title} · {a.id.slice(0, 8)}</p>
                              </div>
                              {a.is_locked && (
                                <Badge className="text-[9px] border-red-500/30 bg-red-500/10 text-red-400 ml-2">
                                  <Lock className="h-2.5 w-2.5 mr-0.5" /> Locked
                                </Badge>
                              )}
                            </button>
                          ))
                        )}
                      </div>
                    )}
                  </div>

                  {/* Lock Status Banner */}
                  {lockStatus && lockStatus.is_locked && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="mb-6 p-5 rounded-xl border border-red-500/20 bg-red-500/5"
                    >
                      <div className="flex items-start gap-3">
                        <ShieldCheck className="h-6 w-6 text-red-400 mt-0.5 shrink-0" />
                        <div>
                          <h4 className="text-sm font-bold text-red-400 flex items-center gap-2">
                            ASSESSMENT LOCKED
                            <Badge className="text-[9px] border-red-500/30 bg-red-500/10 text-red-400">Immutable</Badge>
                          </h4>
                          <p className="text-xs text-white/40 mt-1">
                            Locked by <span className="text-white/60">{lockStatus.locked_by}</span> on{" "}
                            {lockStatus.locked_at
                              ? new Date(lockStatus.locked_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })
                              : "—"}
                          </p>
                          {lockStatus.ledger_hashes.length > 0 && (
                            <div className="mt-3 space-y-2">
                              {lockStatus.ledger_hashes.map((h, i) => (
                                <div key={i} className="flex items-center gap-2 text-[10px]">
                                  <Hash className="h-3 w-3 text-cyan-400 shrink-0" />
                                  <code className="font-mono text-cyan-400/70 break-all">{h.sha256_hash}</code>
                                  <span className="text-white/20 shrink-0">{h.record_count} records · {h.format.toUpperCase()}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </motion.div>
                  )}

                  {/* Ledger Preview Table */}
                  {selectedAssessmentId && (
                    <div className="mb-6">
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider flex items-center gap-2">
                          <Eye className="h-3.5 w-3.5 text-blue-400" />
                          Ledger Preview
                        </h4>
                        {ledgerPreview && (
                          <span className="text-[10px] text-white/20">
                            Showing {ledgerPreview.preview.length} of {ledgerPreview.total_records} approved records
                          </span>
                        )}
                      </div>

                      {previewLoading ? (
                        <div className="flex items-center justify-center py-12">
                          <Loader2 className="h-5 w-5 text-cyan-400 animate-spin" />
                        </div>
                      ) : ledgerPreview && ledgerPreview.preview.length > 0 ? (
                        <div className="rounded-xl border border-white/10 overflow-hidden">
                          <ScrollArea className="max-h-[400px]">
                            <Table>
                              <TableHeader>
                                <TableRow className="border-white/5 hover:bg-transparent bg-white/[0.02]">
                                  <TableHead className="text-white/30 text-[10px]">#</TableHead>
                                  <TableHead className="text-white/30 text-[10px]">Reg No</TableHead>
                                  <TableHead className="text-white/30 text-[10px]">Student Name</TableHead>
                                  <TableHead className="text-white/30 text-[10px]">Subject</TableHead>
                                  <TableHead className="text-white/30 text-[10px]">Marks</TableHead>
                                  <TableHead className="text-white/30 text-[10px]">Confidence</TableHead>
                                  <TableHead className="text-white/30 text-[10px]">Status</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {ledgerPreview.preview.map((row, i) => (
                                  <TableRow key={i} className="border-white/5 hover:bg-white/[0.02]">
                                    <TableCell className="text-[10px] text-white/30 font-mono">{row.Sl_No}</TableCell>
                                    <TableCell className="text-xs text-white/60 font-mono">{row.Register_Number}</TableCell>
                                    <TableCell className="text-xs text-white/60">{row.Student_Name}</TableCell>
                                    <TableCell className="text-[10px] text-white/40">{row.Subject}</TableCell>
                                    <TableCell>
                                      <span className={`text-sm font-bold ${
                                        row.Internal_Marks >= 7 ? "text-emerald-400" : row.Internal_Marks >= 4 ? "text-amber-400" : "text-red-400"
                                      }`}>
                                        {row.Internal_Marks}<span className="text-white/20 font-normal text-[10px]">/10</span>
                                      </span>
                                    </TableCell>
                                    <TableCell className="text-xs text-white/40">{Math.round(row.Confidence * 100)}%</TableCell>
                                    <TableCell>
                                      <Badge className={`text-[9px] ${statusColors[row.Verification_Status] || statusColors.Pending}`}>
                                        {row.Verification_Status}
                                      </Badge>
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </ScrollArea>
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center py-12 text-white/20">
                          <AlertCircle className="h-8 w-8 mb-2 text-amber-400/30" />
                          <p className="text-xs">No approved/audited grades found for this assessment</p>
                          <p className="text-[10px] text-white/10 mt-1">Approve grades from the Staff Dashboard first</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Action Buttons */}
                  {selectedAssessmentId && (
                    <div className="flex flex-wrap items-center gap-3 pt-4 border-t border-white/5">
                      {/* Download Buttons */}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDownloadLedger("csv")}
                        disabled={downloading || !ledgerPreview?.total_records}
                        className="border-cyan-500/20 bg-cyan-500/5 text-cyan-400 hover:bg-cyan-500/10"
                      >
                        {downloading ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1.5 h-3.5 w-3.5" />}
                        Export CSV
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDownloadLedger("xlsx")}
                        disabled={downloading || !ledgerPreview?.total_records}
                        className="border-cyan-500/20 bg-cyan-500/5 text-cyan-400 hover:bg-cyan-500/10"
                      >
                        {downloading ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <FileSpreadsheet className="mr-1.5 h-3.5 w-3.5" />}
                        Export XLSX
                      </Button>

                      <div className="flex-1" />
                    </div>
                  )}

                  {/* Institutional Lock — Hold-to-Seal */}
                  {selectedAssessmentId && (
                    <div className="mt-6">
                      <FinalizeGrades
                        assessmentId={selectedAssessmentId}
                        assessmentLabel={
                          (() => {
                            const a = assessments.find((x) => x.id === selectedAssessmentId);
                            return a ? `${a.subject} — ${a.title}` : undefined;
                          })()
                        }
                        totalScripts={ledgerPreview?.total_records ?? 0}
                        isAlreadyLocked={lockStatus?.is_locked ?? false}
                        lockedBy={lockStatus?.locked_by}
                        lockedAt={lockStatus?.locked_at}
                        ledgerHashes={lockStatus?.ledger_hashes ?? []}
                        onLock={async () => {
                          await fetchLockStatus(selectedAssessmentId);
                          await fetchAll();
                        }}
                        doLock={async () => {
                          const res = await authFetch(
                            `${API_URL}/api/assessments/${selectedAssessmentId}/lock?fmt=csv`,
                            { method: "POST" },
                          );
                          if (res.ok) {
                            const data = await res.json();
                            return { sha256: data.sha256, status: data.status };
                          }
                          const err = await res.json().catch(() => ({ detail: "Lock failed" }));
                          throw new Error(err.detail || `HTTP ${res.status}`);
                        }}
                      />
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          )}
          {activeTab === "seal" && (
            <motion.div
              key="seal"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-6"
            >
              {/* Assessment Selector (reused) */}
              <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-visible">
                <div className="border-b border-white/10 px-6 py-4">
                  <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-cyan-400" />
                    SHA-256 Digital Seal · Integrity Verification
                  </h3>
                  <p className="text-[10px] text-white/30 mt-1">
                    Upload a previously exported ledger file to verify it has not been tampered with
                  </p>
                </div>
                <CardContent className="p-6">
                  {/* Assessment dropdown */}
                  <div className="relative mb-6">
                    <label className="text-[10px] uppercase tracking-wider text-white/30 mb-2 block">
                      Assessment
                    </label>
                    <button
                      onClick={() => setShowAssessmentDropdown(!showAssessmentDropdown)}
                      className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-white/10 bg-white/5 text-sm text-white/70 hover:border-white/20 transition-colors"
                    >
                      <span>
                        {selectedAssessmentId
                          ? (() => {
                              const a = assessments.find((x) => x.id === selectedAssessmentId);
                              return a ? `${a.subject} — ${a.title}` : selectedAssessmentId;
                            })()
                          : "Select an assessment…"}
                      </span>
                      <ChevronDown
                        className={`h-4 w-4 text-white/30 transition-transform ${
                          showAssessmentDropdown ? "rotate-180" : ""
                        }`}
                      />
                    </button>
                    {showAssessmentDropdown && (
                      <div className="absolute z-50 mt-2 w-full rounded-xl border border-white/10 bg-slate-900/95 backdrop-blur-2xl shadow-2xl max-h-60 overflow-y-auto">
                        {assessments.map((a) => (
                          <button
                            key={a.id}
                            onClick={() => {
                              setSelectedAssessmentId(a.id);
                              setShowAssessmentDropdown(false);
                              setVerifyResult(null);
                              setVerifyFile(null);
                            }}
                            className={`w-full text-left px-4 py-3 text-sm hover:bg-white/5 transition-colors flex items-center justify-between ${
                              selectedAssessmentId === a.id
                                ? "bg-white/5 text-cyan-400"
                                : "text-white/60"
                            }`}
                          >
                            <div>
                              <p className="font-medium">{a.subject}</p>
                              <p className="text-[10px] text-white/30">
                                {a.title} · {a.id.slice(0, 8)}
                              </p>
                            </div>
                            {a.is_locked && (
                              <Badge className="text-[9px] border-red-500/30 bg-red-500/10 text-red-400 ml-2">
                                <Lock className="h-2.5 w-2.5 mr-0.5" /> Locked
                              </Badge>
                            )}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Existing hashes for selected assessment */}
                  {lockStatus && lockStatus.ledger_hashes.length > 0 && (
                    <div className="mb-6">
                      <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
                        <Hash className="h-3.5 w-3.5 text-cyan-400" />
                        Stored Digital Seals
                      </h4>
                      <div className="space-y-2">
                        {lockStatus.ledger_hashes.map((h, i) => (
                          <motion.div
                            key={i}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 0.05 * i }}
                            className="p-4 rounded-xl border border-cyan-500/10 bg-cyan-500/5"
                          >
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-xs font-semibold text-cyan-400">
                                {h.filename}
                              </span>
                              <Badge className="text-[9px] border-white/10 bg-white/5 text-white/40">
                                {h.record_count} records · {h.format.toUpperCase()}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-2">
                              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                              <code className="font-mono text-[10px] text-cyan-400/70 break-all select-all">
                                SHA-256: {h.sha256_hash}
                              </code>
                            </div>
                            <p className="text-[10px] text-white/20 mt-1">
                              Generated:{" "}
                              {new Date(h.created_at).toLocaleString("en-IN", {
                                dateStyle: "medium",
                                timeStyle: "short",
                              })}
                            </p>
                          </motion.div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Verify File Upload */}
                  {selectedAssessmentId && (
                    <div className="pt-4 border-t border-white/5">
                      <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
                        <ShieldCheck className="h-3.5 w-3.5 text-amber-400" />
                        Verify File Integrity
                      </h4>
                      <p className="text-[10px] text-white/30 mb-4">
                        Upload a CSV/XLSX file previously exported from AuraGrade to check
                        if it has been modified since export.
                      </p>

                      <input
                        ref={verifyInputRef}
                        type="file"
                        accept=".csv,.xlsx"
                        className="hidden"
                        onChange={(e) => {
                          setVerifyFile(e.target.files?.[0] ?? null);
                          setVerifyResult(null);
                        }}
                      />

                      <div className="flex items-center gap-3">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => verifyInputRef.current?.click()}
                          className="border-white/10 bg-white/5 text-white/60 hover:bg-white/10 text-xs"
                        >
                          <FileText className="mr-1.5 h-3.5 w-3.5" />
                          {verifyFile ? verifyFile.name : "Choose File"}
                        </Button>
                        <Button
                          size="sm"
                          onClick={handleVerifyUpload}
                          disabled={!verifyFile || verifying}
                          className="bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs shadow-lg shadow-cyan-500/20 disabled:opacity-50"
                        >
                          {verifying ? (
                            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
                          )}
                          Verify SHA-256
                        </Button>
                      </div>

                      {/* Verification Result */}
                      <AnimatePresence>
                        {verifyResult && (
                          <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                            className={`mt-4 p-5 rounded-xl border ${
                              verifyResult.status === "AUTHENTIC"
                                ? "border-emerald-500/30 bg-emerald-500/10"
                                : verifyResult.status === "TAMPERED"
                                  ? "border-red-500/30 bg-red-500/10"
                                  : "border-amber-500/30 bg-amber-500/10"
                            }`}
                          >
                            <div className="flex items-start gap-3">
                              {verifyResult.status === "AUTHENTIC" ? (
                                <ShieldCheck className="h-6 w-6 text-emerald-400 shrink-0 mt-0.5" />
                              ) : verifyResult.status === "TAMPERED" ? (
                                <AlertCircle className="h-6 w-6 text-red-400 shrink-0 mt-0.5" />
                              ) : (
                                <AlertTriangle className="h-6 w-6 text-amber-400 shrink-0 mt-0.5" />
                              )}
                              <div>
                                <h5
                                  className={`text-sm font-bold ${
                                    verifyResult.status === "AUTHENTIC"
                                      ? "text-emerald-400"
                                      : verifyResult.status === "TAMPERED"
                                        ? "text-red-400"
                                        : "text-amber-400"
                                  }`}
                                >
                                  {verifyResult.status}
                                </h5>
                                <p className="text-xs text-white/50 mt-1">
                                  {verifyResult.message}
                                </p>
                                <div className="mt-3 flex items-center gap-2">
                                  <Hash className="h-3 w-3 text-cyan-400 shrink-0" />
                                  <code className="font-mono text-[10px] text-cyan-400/70 break-all">
                                    {verifyResult.computed_hash}
                                  </code>
                                </div>
                                {verifyResult.original_filename && (
                                  <p className="text-[10px] text-white/30 mt-2">
                                    Original: {verifyResult.original_filename}
                                    {verifyResult.generated_at &&
                                      ` · ${
                                        new Date(verifyResult.generated_at).toLocaleString("en-IN", {
                                          dateStyle: "medium",
                                          timeStyle: "short",
                                        })
                                      }`}
                                  </p>
                                )}
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>

          {activeTab === "sentinel" && (
            <motion.div
              key="sentinel"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              <SimilaritySentinel authFetch={authFetch} />
            </motion.div>
          )}

          {activeTab === "ledger" && (
            <motion.div
              key="ledger"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              <InstitutionalLedger authFetch={authFetch} assessments={assessments} />
            </motion.div>
          )}

        {/* ========== FOOTER ========== */}
        <footer className="mt-10 flex items-center justify-center gap-2 text-[11px] text-white/15 tracking-wide">
          <Shield className="h-3 w-3" />
          AuraGrade Institutional Layer · RBAC · Tamper-Proof Audit Trail · CoE Portal
        </footer>
      </div>
    </div>
  );
}
