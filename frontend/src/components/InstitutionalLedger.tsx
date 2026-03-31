"use client";

import React, { useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileSpreadsheet,
  Download,
  Hash,
  Shield,
  ShieldAlert,
  Eye,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Users,
  Lock,
  FileText,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Assessment {
  id: string;
  subject: string;
  title: string;
  is_locked?: boolean;
  locked_at?: string;
}

interface PreviewRow {
  reg_no: string;
  name: string;
  marks: number;
  confidence: number;
  status: string;
  sentinel_status: string;
  sentinel_similarity: number | string;
  sentinel_peer: string;
}

interface PreviewData {
  assessment: Assessment | null;
  total_records: number;
  sentinel_flags_count: number;
  preview: PreviewRow[];
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export const InstitutionalLedger: React.FC<{
  authFetch: (url: string, init?: RequestInit) => Promise<Response>;
  assessments: Assessment[];
}> = ({ authFetch, assessments }) => {
  const [selectedId, setSelectedId] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [format, setFormat] = useState<"csv" | "xlsx">("xlsx");
  const [threshold, setThreshold] = useState(90);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadResult, setDownloadResult] = useState<{
    filename: string;
    sha256: string;
    flagCount: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  /* ---------- Fetch preview when assessment selected ---------- */
  const fetchPreview = useCallback(async () => {
    if (!selectedId) return;
    setLoadingPreview(true);
    setError(null);
    setDownloadResult(null);
    try {
      const r = await authFetch(
        `${API_URL}/api/institutional-ledger/${selectedId}/preview?sentinel_threshold=${threshold / 100}`
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
      setPreview(await r.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed");
      setPreview(null);
    } finally {
      setLoadingPreview(false);
    }
  }, [selectedId, threshold, authFetch]);

  useEffect(() => {
    if (selectedId) fetchPreview();
  }, [selectedId, fetchPreview]);

  /* ---------- Download ---------- */
  const handleDownload = useCallback(async () => {
    if (!selectedId) return;
    setDownloading(true);
    setError(null);
    try {
      const r = await authFetch(
        `${API_URL}/api/institutional-ledger/${selectedId}/download?fmt=${format}&sentinel_threshold=${threshold / 100}`
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }

      const sha256 = r.headers.get("X-SHA256-Seal") || "";
      const flagCount = parseInt(r.headers.get("X-Sentinel-Flags") || "0", 10);
      const blob = await r.blob();

      // Extract filename from content-disposition
      const cd = r.headers.get("Content-Disposition") || "";
      const fnMatch = cd.match(/filename="?([^"]+)"?/);
      const filename = fnMatch ? fnMatch[1] : `INST_LEDGER.${format}`;

      // Trigger download
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      setDownloadResult({ filename, sha256, flagCount });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }, [selectedId, format, threshold, authFetch]);

  /* ---------- Helpers ---------- */
  const selectedAssessment = assessments.find((a) => a.id === selectedId);

  return (
    <div className="space-y-6">
      {/* ── Header Card ── */}
      <div className="bg-slate-900/80 border border-white/10 rounded-3xl p-6 relative overflow-hidden">
        <div className="absolute -top-10 -right-10 w-40 h-40 bg-cyan-500/5 rounded-full blur-[80px] pointer-events-none" />

        <div className="flex items-start justify-between mb-6 relative z-10">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 rounded-2xl">
              <FileSpreadsheet className="w-6 h-6 text-cyan-400" />
            </div>
            <div>
              <h3 className="text-xl font-black italic text-white uppercase tracking-tighter">
                Institutional Ledger
              </h3>
              <p className="text-[10px] text-slate-500 font-bold uppercase tracking-[0.2em]">
                Marks · Sentinel Flags · Digital Seal
              </p>
            </div>
          </div>
        </div>

        {/* Assessment selector */}
        <div className="relative mb-4">
          <label className="text-[10px] uppercase tracking-wider text-white/30 mb-2 block font-bold">
            Assessment
          </label>
          <button
            onClick={() => setShowDropdown(!showDropdown)}
            className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-white/10 bg-white/5 text-sm text-white/70 hover:border-white/20 transition-colors"
          >
            <span>
              {selectedAssessment
                ? `${selectedAssessment.subject} — ${selectedAssessment.title}`
                : "Select an assessment…"}
            </span>
            <ChevronDown
              className={`h-4 w-4 text-white/30 transition-transform ${showDropdown ? "rotate-180" : ""}`}
            />
          </button>
          <AnimatePresence>
            {showDropdown && (
              <motion.div
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                className="absolute top-full left-0 right-0 mt-1 bg-slate-900 border border-white/10 rounded-xl overflow-hidden z-50 shadow-2xl max-h-48 overflow-y-auto"
              >
                {assessments.map((a) => (
                  <button
                    key={a.id}
                    onClick={() => {
                      setSelectedId(a.id);
                      setShowDropdown(false);
                    }}
                    className={`w-full text-left px-4 py-2.5 text-xs hover:bg-white/5 transition-colors flex items-center justify-between ${
                      selectedId === a.id
                        ? "bg-cyan-500/10 text-cyan-400"
                        : "text-white/60"
                    }`}
                  >
                    <span>
                      {a.subject} — {a.title}
                    </span>
                    <div className="flex items-center gap-1">
                      {a.is_locked && (
                        <Lock className="h-3 w-3 text-emerald-400" />
                      )}
                    </div>
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Options row */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-white/[0.03] border border-white/[0.06] rounded-xl px-3 py-2">
            <span className="text-[9px] text-white/30 uppercase tracking-wider font-bold">
              Format
            </span>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value as "csv" | "xlsx")}
              className="bg-transparent text-xs text-white/70 font-mono font-bold outline-none cursor-pointer"
            >
              <option value="xlsx" className="bg-slate-900">
                Excel (.xlsx)
              </option>
              <option value="csv" className="bg-slate-900">
                CSV
              </option>
            </select>
          </div>

          <div className="flex items-center gap-2 bg-white/[0.03] border border-white/[0.06] rounded-xl px-3 py-2">
            <span className="text-[9px] text-white/30 uppercase tracking-wider font-bold">
              Sentinel
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
            onClick={handleDownload}
            disabled={!selectedId || downloading}
            className="ml-auto flex items-center gap-2 px-5 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-black text-xs uppercase tracking-wider transition-all disabled:opacity-30 disabled:cursor-not-allowed shadow-lg shadow-cyan-500/20"
          >
            {downloading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            {downloading ? "Generating…" : "Export Ledger"}
          </button>
        </div>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-300">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* ── Download Result ── */}
      <AnimatePresence>
        {downloadResult && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="bg-emerald-500/5 border border-emerald-500/20 rounded-2xl p-5"
          >
            <div className="flex items-center gap-3 mb-3">
              <CheckCircle2 className="h-5 w-5 text-emerald-400" />
              <span className="text-sm font-bold text-emerald-400">
                Ledger Exported Successfully
              </span>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-[9px] text-white/25 uppercase tracking-wider font-bold mb-1">
                  Filename
                </p>
                <p className="text-xs text-white/60 font-mono">
                  {downloadResult.filename}
                </p>
              </div>
              <div>
                <p className="text-[9px] text-white/25 uppercase tracking-wider font-bold mb-1">
                  SHA-256 Seal
                </p>
                <p className="text-xs text-cyan-400/70 font-mono break-all">
                  {downloadResult.sha256.slice(0, 32)}…
                </p>
              </div>
              <div>
                <p className="text-[9px] text-white/25 uppercase tracking-wider font-bold mb-1">
                  Sentinel Flags
                </p>
                <p
                  className={`text-xs font-mono font-bold ${
                    downloadResult.flagCount > 0
                      ? "text-rose-400"
                      : "text-emerald-400"
                  }`}
                >
                  {downloadResult.flagCount > 0
                    ? `${downloadResult.flagCount} flagged`
                    : "0 — All Clear"}
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Loading ── */}
      {loadingPreview && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 text-cyan-400 animate-spin" />
          <span className="text-xs text-white/20 ml-3">
            Running sentinel scan & building preview…
          </span>
        </div>
      )}

      {/* ── Preview Table ── */}
      <AnimatePresence>
        {preview && !loadingPreview && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-slate-900/80 border border-white/10 rounded-2xl overflow-hidden"
          >
            {/* Preview header */}
            <div className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Eye className="h-4 w-4 text-cyan-400" />
                <h4 className="text-sm font-semibold text-white/80">
                  Ledger Preview
                </h4>
                <span className="text-[10px] text-white/20 ml-2">
                  {preview.total_records} records
                </span>
              </div>
              <div className="flex items-center gap-3">
                {preview.sentinel_flags_count > 0 && (
                  <span className="flex items-center gap-1 text-[10px] font-bold text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2 py-1 rounded-lg">
                    <ShieldAlert className="h-3 w-3" />
                    {preview.sentinel_flags_count} Sentinel Flag
                    {preview.sentinel_flags_count !== 1 ? "s" : ""}
                  </span>
                )}
                {preview.assessment?.is_locked && (
                  <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-1 rounded-lg">
                    <Lock className="h-3 w-3" />
                    Locked
                  </span>
                )}
              </div>
            </div>

            {/* Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-white/5 text-white/30">
                    <th className="text-left px-4 py-3 font-bold uppercase tracking-wider text-[9px]">
                      #
                    </th>
                    <th className="text-left px-4 py-3 font-bold uppercase tracking-wider text-[9px]">
                      Reg No
                    </th>
                    <th className="text-left px-4 py-3 font-bold uppercase tracking-wider text-[9px]">
                      Student
                    </th>
                    <th className="text-right px-4 py-3 font-bold uppercase tracking-wider text-[9px]">
                      Marks
                    </th>
                    <th className="text-right px-4 py-3 font-bold uppercase tracking-wider text-[9px]">
                      Conf%
                    </th>
                    <th className="text-center px-4 py-3 font-bold uppercase tracking-wider text-[9px]">
                      Status
                    </th>
                    <th className="text-center px-4 py-3 font-bold uppercase tracking-wider text-[9px]">
                      Sentinel
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {preview.preview.map((row, i) => (
                    <motion.tr
                      key={row.reg_no}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.03 }}
                      className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="px-4 py-3 text-white/20 font-mono">
                        {i + 1}
                      </td>
                      <td className="px-4 py-3 text-white/60 font-mono font-bold">
                        {row.reg_no}
                      </td>
                      <td className="px-4 py-3 text-white/70">{row.name}</td>
                      <td className="px-4 py-3 text-right text-white/80 font-mono font-bold">
                        {row.marks}
                      </td>
                      <td className="px-4 py-3 text-right text-white/40 font-mono">
                        {row.confidence}%
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full text-[9px] font-bold ${
                            row.status === "Approved"
                              ? "bg-emerald-500/15 text-emerald-400"
                              : row.status === "Overridden"
                                ? "bg-cyan-500/15 text-cyan-400"
                                : row.status === "Audited"
                                  ? "bg-violet-500/15 text-violet-400"
                                  : "bg-white/5 text-white/30"
                          }`}
                        >
                          {row.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {row.sentinel_status === "Clear" ? (
                          <span className="text-[9px] text-white/15">—</span>
                        ) : (
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold ${
                              row.sentinel_status === "Critical"
                                ? "bg-rose-500/15 text-rose-400"
                                : "bg-amber-500/15 text-amber-400"
                            }`}
                          >
                            <ShieldAlert className="h-2.5 w-2.5" />
                            {typeof row.sentinel_similarity === "number"
                              ? `${row.sentinel_similarity}%`
                              : row.sentinel_status}
                          </span>
                        )}
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-white/5 flex items-center justify-between">
              <div className="flex items-center gap-2 text-[10px] text-white/15">
                <Shield className="h-3 w-3" />
                Tamper-proof · SHA-256 sealed · Sentinel-scanned
              </div>
              {preview.total_records > 20 && (
                <span className="text-[10px] text-white/20">
                  Showing 20 of {preview.total_records}
                </span>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default InstitutionalLedger;
